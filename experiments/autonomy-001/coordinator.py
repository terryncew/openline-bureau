#!/usr/bin/env python3
"""OPENLINE-AUTONOMY-001 coordinator: a thin mission loop around proven components.

One `--once` invocation runs a single observe->decide cycle and exits;
cron (or a human) wakes it again. All durable state lives in state.json
(atomic writes); receipts go to state/receipts/ as bureau.receipt.v0.1.

The coordinator never implements agent reasoning, never evaluates with a
model, and never merges to main. Its most consequential act — accepting a
change onto an isolated branch — happens only for preauthorized change
classes after independent evaluation passes, and is itself recorded.

Phases per task: SELECT -> ASSIGN -> BUILD -> EVALUATE -> DECIDE -> RECORD.
Revocation (mission.yaml `revoked: true`) is checked at every phase
boundary: the loop finishes the current phase safely and starts no new work.
"""

from __future__ import annotations

import argparse
import fcntl
from dataclasses import asdict
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import evaluator as EV
import receipts as RC
import workers as W
import yaml
import integrations as IN

MISSION_PATH = HERE / "mission.yaml"
POLICY_PATH = HERE / "policy" / "authorized.json"
QUEUE_PATH = HERE / "queue" / "tasks.json"

PHASES = ("select", "assign", "build", "evaluate", "decide", "record")


def sh(*args, cwd=None, check=True):
    if args and args[0] == "git":
        args = ("git", "-c", "core.fsync=all", "-c", "core.hooksPath=/dev/null", *args[1:])
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          check=check)


def atomic_write(path: Path, obj):
    IN.durable_write(path, obj)

def load_mission():
    mission = yaml.safe_load(MISSION_PATH.read_text())
    standing = dict(mission)
    standing.pop("revoked", None)
    digest = hashlib.sha256(IN.olp_canonical_json(standing)).hexdigest()
    return mission, digest


def load_policy():
    return json.loads(POLICY_PATH.read_text())


def load_queue():
    return json.loads(QUEUE_PATH.read_text())["queue"]


def revoke_state(state_dir):
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    with (state_dir / "effect.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        IN.durable_write(state_dir / "REVOKED", {"revoked": True})


class Controller:
    def __init__(self, state_dir: Path, worker_id: str,
                 stop_after_phase: str | None = None, provider: str | None = None):
        state_dir = Path(state_dir).resolve()
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = state_dir / "state.json"
        self.receipts_dir = state_dir / "receipts"
        self.scratch = state_dir / "scratch"
        self.worker_id = worker_id
        self.provider = provider
        self.stop_after_phase = stop_after_phase
        self.mission, self.mission_digest = load_mission()
        self.policy = load_policy()
        self.policy_digest = hashlib.sha256(IN.olp_canonical_json(self.policy)).hexdigest()
        self.queue = {t["id"]: t for t in load_queue()}
        self.queue_digest = hashlib.sha256(QUEUE_PATH.read_bytes()).hexdigest()
        self.run_id = uuid.uuid4().hex[:8]
        self.state = self._load_or_init()
        self.run_id = self.state["run_id"]
        self.key = IN.signing_key(state_dir)

    # -- state ---------------------------------------------------------
    def _load_or_init(self):
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text())
            if (state.get("mission_digest") != self.mission_digest or
                    state.get("policy_digest") != self.policy_digest or
                    state.get("queue_digest") != self.queue_digest):
                raise SystemExit(
                    "mission.yaml changed mid-run: halting for owner review")
            self._verify_history(state)
            return state
        return {"run_id": self.run_id, "mission_digest": self.mission_digest,
                "policy_digest": self.policy_digest, "queue_digest": self.queue_digest,
                "tasks": {}, "current": None, "cycles_completed": 0,
                "receipts": []}

    def _verify_history(self, state):
        key = IN.load_private_key(self.state_dir / "keys" / "receiver.key")
        trusted = IN.public_key_hex(key)
        rows = {}
        for path in self.receipts_dir.glob("*.json"):
            rec = json.loads(path.read_text())
            if not IN.verify_olp_signature(rec)[0] or rec["signature"]["public_key"] != trusted:
                raise RuntimeError("receipt signature invalid: " + path.name)
            rows[rec["receipt_id"]] = rec
        head = None
        for rid in state["receipts"]:
            rec = rows.pop(rid)
            if rec["extensions"]["autonomy"]["previous_receipt_hash"] != head:
                raise RuntimeError("receipt chain mismatch")
            head = rec["payload_hash"]
        if head != state.get("receipt_head"):
            raise RuntimeError("receipt head mismatch")
        while rows:
            next_rows = [r for r in rows.values() if
                r["extensions"]["autonomy"]["previous_receipt_hash"] == head]
            if len(next_rows) != 1:
                raise RuntimeError("orphan receipt chain ambiguous")
            rec = next_rows[0]
            state["receipts"].append(rec["receipt_id"])
            head = rec["payload_hash"]
            rows.pop(rec["receipt_id"])
        state["receipt_head"] = head

    def _save(self):
        atomic_write(self.state_path, self.state)

    def _receipt(self, kind, task_id, worker_id, decision, reason,
                 evidence=None):
        rec = RC.make_receipt(kind, task_id, worker_id, decision, reason,
                              self.run_id, evidence)
        rec["authority"]["status"] = "REVOKED" if self._revoked() else "ACTIVE"
        rec["effect"]["observed"] = (kind == "accept" or (kind == "recovery" and
            evidence and evidence.get("status") == "accepted")) and decision == "COMMIT"
        rec["extensions"]["autonomy"].update(signed=True,
            signature_note="Local receiver key; no independent external attestation")
        rec["extensions"]["autonomy"]["previous_receipt_hash"] = self.state.get("receipt_head")
        rec = IN.sign_olp_body(rec, self.key)
        path = RC.store_receipt(self.receipts_dir, rec)
        self.state["receipt_head"] = rec["payload_hash"]
        self.state["receipts"].append(rec["receipt_id"])
        self._save()
        return rec, path

    def _revoked(self):
        # Re-read the file every time: the owner can revoke at any moment.
        if yaml.safe_load(MISSION_PATH.read_text()).get("revoked", False):
            if not (self.state_dir / "REVOKED").exists():
                IN.durable_write(self.state_dir / "REVOKED", {"revoked": True})
        return (self.state_dir / "REVOKED").exists()

    def _check_stop(self, phase):
        if self.stop_after_phase == phase:
            print(f"[demo hook] stopping after phase: {phase}")
            raise _StopAfterPhase(phase)

    # -- target setup ---------------------------------------------------
    def _ensure_scratch(self):
        if not (self.scratch / ".git").exists():
            target_repo = os.environ.get(
                "AUTONOMY_TARGET_REPO",
                str(HERE.parents[1]))  # the bureau checkout by default
            sh("git", "clone", "-q", target_repo, str(self.scratch))
        baseline = self.mission["target"]["baseline_commit"]
        sh("git", "-C", str(self.scratch), "fetch", "-q", "origin",
           check=False)
        return baseline

    def _worktree(self, task_id, baseline):
        wt = self.state_dir / "wt" / task_id
        if wt.exists():
            sh("git", "-C", str(self.scratch), "worktree", "remove",
               "--force", str(wt), check=False)
            shutil.rmtree(wt, ignore_errors=True)
        sh("git", "-C", str(self.scratch), "worktree", "add", "--detach",
           str(wt), baseline)
        return wt

    # -- the loop --------------------------------------------------------
    def run_once(self):
        # One controller owns selection through consequence and recovery.
        with (self.state_dir / "controller.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.state = self._load_or_init()
            if self.state["current"]:
                return self._recover()
            return self._run_once_locked()

    def revoke(self):
        # Revocation remains usable even when unrelated state is damaged.
        revoke_state(self.state_dir)

    def _recover(self):
        current = self.state["current"]
        tid = current["task_id"]
        intent = current.get("accept_intent")
        status = "held"
        # Never re-run an interrupted untrusted worker or re-spend permission.
        if intent:
            permission = json.loads((self.state_dir / "gate" / tid / "permission.json").read_text())
            from olp_gate.gateway import verify_decision_receipt
            if (not verify_decision_receipt(permission, [IN.public_key_hex(self.key)])["valid"] or
                    permission["payload_hash"] != intent["permission_hash"]):
                raise RuntimeError("recovery permission invalid")
            evidence_path = self.state_dir / "gate" / tid / "evidence.json"
            evidence = json.loads(evidence_path.read_text())
            authorization = permission["commit_authorization"]
            if (authorization["target"] != intent["ref"] or
                    authorization["settings_hash"] != IN.settings_hash({
                        "commit": intent["commit"], "expected_old": "0" * 40}) or
                    IN.sha256_hex(evidence_path.read_bytes()) not in authorization["evidence_hashes"] or
                    evidence["commit"] != intent["commit"]):
                raise RuntimeError("recovery effect binding invalid")
            ref = sh("git", "-C", str(self.scratch), "rev-parse", "--verify",
                     intent["ref"], check=False)
            if ref.returncode == 0 and ref.stdout.strip() == intent["commit"]:
                ledger_path = self.state_dir / "gate-ledger.json"
                if not ledger_path.exists():
                    raise RuntimeError("unattributed ref update: Gate consumption missing")
                journal = IN.VerifiedCommitLedger(ledger_path).read_state()
                attempts = [a for a in journal["attempts"] if
                    a.get("decision_payload_hash") == permission["payload_hash"] and
                    a.get("result") == "AUTHORIZED" and
                    a.get("attempt_action_hash") == authorization["action_hash"] and
                    a.get("execution_status") in ("started", "completed", "failed")]
                if len(attempts) != 1:
                    raise RuntimeError("unattributed ref update: Gate execution missing")
                status = "accepted"
                self.state["tasks"][tid] = {"status": status, "branch": intent["branch"]}
            elif ref.returncode == 0:
                raise RuntimeError("acceptance ref diverged: owner review required")
        self._receipt("recovery", tid, current["worker_id"],
                      "COMMIT" if status == "accepted" else "QUARANTINE",
                      "RECOVERY: effect reconciled" if status == "accepted" else
                      "INTERRUPTED: held without retry", {"intent": intent, "status": status})
        self.state["tasks"][tid] = {**self.state["tasks"].get(tid, {}), "status": status}
        return self._finish_task(tid, self.state_dir / "wt" / tid, status)

    def _fresh_authority(self):
        mission, digest = load_mission()
        return (not self._revoked() and digest == self.mission_digest and
                hashlib.sha256(IN.olp_canonical_json(load_policy())).hexdigest() == self.policy_digest and
                hashlib.sha256(QUEUE_PATH.read_bytes()).hexdigest() == self.queue_digest)

    def _run_once_locked(self):
        if not self._fresh_authority():
            self._receipt("mission", None, None, "DENY",
                          "REVOKED_STOP: owner revoked the mission; "
                          "no new work started")
            print("mission revoked: no work started")
            return "revoked"

        task = self._select()
        if task is None:
            print("queue empty: idle")
            return "idle"
        if self.state["cycles_completed"] >= \
                self.mission["budgets"]["max_cycles"]:
            print("budget exhausted: max_cycles reached")
            return "budget"

        if len(self.state["tasks"]) >= self.mission["budgets"]["max_tasks"]:
            return "budget"
        tid = task["id"]
        import re
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", tid):
            raise ValueError("unsafe task identifier")
        self.state["current"] = {"task_id": tid, "phase": "select",
                                 "worker_id": self.worker_id}
        self._save()
        self._check_stop("select")

        # ASSIGN
        worker = (W.AirlockWorker(self.worker_id, IN.resolve_provider({}, self.provider))
                  if self.provider else W.ScriptedWorker(self.worker_id))
        self.state["current"]["phase"] = "assign"
        self._save()
        self._receipt("assign", tid, self.worker_id, "COMMIT",
                      f"task assigned to {self.worker_id}",
                      {"queue_priority": task["priority"]})
        self._check_stop("assign")
        if not self._fresh_authority():
            return self._recover()

        # BUILD (isolated worktree at pinned baseline)
        baseline = self._ensure_scratch()
        wt = self._worktree(tid, baseline)
        self.state["current"]["phase"] = "build"
        self._save()
        scope = self.mission["target"]["scope_paths"]
        protected = self.mission["boundaries"]["protected_paths"]
        build = worker.build(task, wt, scope, protected)
        self.state["current"]["build"] = asdict(build)
        self._save()
        self._check_stop("build")
        if not self._fresh_authority():
            return self._recover()

        if not build.ok:
            self._quarantine_or_reject(task, build, wt)
            return self._finish_task(tid, wt)

        # Non-preauthorized proposals cannot execute code or land a ref.
        if task["change_class"] not in {c["id"] for c in self.policy["auto_accept_classes"]}:
            self._receipt("decide", tid, self.worker_id, "QUARANTINE",
                          "HELD: change class/path not preauthorized")
            self.state["tasks"][tid] = {"status": "held"}
            return self._finish_task(tid, wt, "held")

        # EVALUATE (independent: protected tests restored, holdout injected)
        self.state["current"]["phase"] = "evaluate"
        self._save()
        hold = EV.prepare_holdout(wt, HERE / "holdout")
        try:
            ev = EV.evaluate(
                task, wt, wt, ".holdout_tmp",
                HERE.parent / "review-desk-001",
                self.mission["budgets"])
        finally:
            EV.cleanup_holdout(wt)
        self._check_stop("evaluate")

        # DECIDE
        self.state["current"]["phase"] = "decide"
        self._save()
        if not self._fresh_authority():
            self._receipt("decide", tid, self.worker_id, "DENY",
                          "REVOKED_STOP: revoked before decision; "
                          "change discarded")
            self._finish_task(tid, wt, status="held")
            return "revoked"
        outcome = self._decide(task, build, ev, wt)
        self._check_stop("decide")

        # RECORD happens inside _decide via _receipt calls.
        return self._finish_task(tid, wt, status=outcome)

    def _select(self):
        pending = [t for tid, t in self.queue.items()
                   if self.state["tasks"].get(tid, {}).get("status")
                   in (None, "pending")]
        if not pending:
            return None
        pending.sort(key=lambda t: t["priority"])
        return pending[0]

    def _quarantine_or_reject(self, task, build, wt):
        tid = task["id"]
        if build.violation == "RULE_MODIFICATION_ATTEMPT":
            self._receipt(
                "build", tid, self.worker_id, "DENY",
                "QUARANTINED: worker attempted to modify governing rules",
                {"violation": build.violation, "notes": build.notes})
            self.state["tasks"][tid] = {"status": "quarantined"}
            print(f"task {tid}: QUARANTINED (rules modification attempt)")
        else:
            self._receipt("build", tid, self.worker_id, "DENY",
                          f"REJECTED at build: {build.notes}",
                          {"violation": build.violation})
            self.state["tasks"][tid] = {"status": "rejected"}
            print(f"task {tid}: rejected at build: {build.notes}")

    def _decide(self, task, build, ev, wt):
        tid = task["id"]
        evidence = {
            "improvement": "NOT_ESTABLISHED: tests are regression evidence only",
            "protected_tests": ev.protected_tests,
            "holdout": ev.holdout,
            "invariants": {k: v for k, v in ev.invariants.items()
                            if k != "diff_stat"},
            "files_changed": build.files_changed,
        }
        if not ev.passed:
            self._receipt("evaluate", tid, self.worker_id, "DENY",
                          "REJECTED: independent evaluation failed",
                          evidence)
            self.state["tasks"][tid] = {"status": "rejected"}
            print(f"task {tid}: REJECTED by evaluation")
            return "rejected"

        build.files_changed = ev.invariants["files"]
        build.lines_changed = ev.invariants["lines_changed"]
        if self._policy_allows(task, build):
            branch = f"autonomy-001/accepted/{tid}"
            self._accept_to_branch(wt, branch, task, evidence)
            self._receipt("accept", tid, self.worker_id, "COMMIT",
                          f"ACCEPTED onto isolated branch {branch} "
                          f"(preauthorized class {task['change_class']})",
                          evidence)
            self.state["tasks"][tid] = {"status": "accepted",
                                        "branch": branch}
            print(f"task {tid}: ACCEPTED -> {branch}")
            return "accepted"

        self._receipt("decide", tid, self.worker_id, "QUARANTINE",
                      f"HELD for human: change class "
                      f"'{task['change_class']}' is not preauthorized",
                      evidence)
        self.state["tasks"][tid] = {"status": "held"}
        print(f"task {tid}: HELD for human (not preauthorized)")
        return "held"

    def _policy_allows(self, task, build) -> bool:
        cls = next((c for c in self.policy["auto_accept_classes"]
                    if c["id"] == task["change_class"]), None)
        if cls is None:
            return False
        import re
        for f in build.files_changed:
            if any(re.search(pat, f)
                   for pat in self.policy["never_auto"]):
                return False
            if not re.search(cls["path_pattern"], f):
                return False
        if build.lines_changed > cls["max_lines"]:
            return False
        return True

    def _accept_to_branch(self, wt, branch, task, evidence):
        # Prepare an immutable evaluated commit before granting exact ref authority.
        sh("git", "-C", str(wt), "-c", "core.hooksPath=/dev/null", "add", "-A")
        sh("git", "-C", str(wt), "-c", "core.hooksPath=/dev/null",
           "-c", "user.name=autonomy-001", "-c", "user.email=autonomy-001@local",
           "commit", "-qm", f"autonomy-001: accept {task['id']}")
        commit = sh("git", "-C", str(wt), "rev-parse", "HEAD").stdout.strip()
        ref = "refs/heads/" + branch
        operation = uuid.uuid4().hex
        evidence = {**evidence, "task_id": task["id"], "operation_id": operation,
                    "eligible": True, "commit": commit, "policy": self.policy_digest,
                    "mission": self.mission_digest}
        receipt, action, code = IN.issue_permission(self.state_dir,
            {"tool": "git.update-ref", "target": ref,
             "settings": {"commit": commit, "expected_old": "0" * 40}},
            evidence, self.mission_digest)
        self.state["current"]["accept_intent"] = {
            "ref": ref, "branch": branch, "commit": commit,
            "permission_hash": receipt["payload_hash"]}
        self._save()
        self._check_stop("permission")
        def execute():
            # Supported revoke() shares this serialization point. A committed
            # revoke always blocks later updates, including compiled permission.
            fd = os.open(self.state_dir, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)  # make Receipt Gate consumption journal replacement durable
            finally:
                os.close(fd)
            with (self.state_dir / "effect.lock").open("a+") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if not self._fresh_authority():
                    raise RuntimeError("authority revoked before ref update")
                sh("git", "-C", str(self.scratch), "update-ref", ref, commit, "0" * 40)
                self._check_stop("effect")
                return {"ref": ref, "commit": commit}
        result = IN.VerifiedCommitLedger(self.state_dir / "gate-ledger.json").execute_once(
            receipt, action, one_use_code=code,
            trusted_gate_keys=[IN.public_key_hex(self.key)], executor=execute,
            preflight=lambda: {"allowed": self._fresh_authority(),
                "reason_codes": [] if self._fresh_authority() else ["authority_revoked"],
                "evidence": {"mission": self.mission_digest, "policy": self.policy_digest}},
            replay_scope_hash=hashlib.sha256(task["id"].encode()).hexdigest())
        if not result["authorized"]:
            raise RuntimeError("Receiver denied effect: " + repr(result["reason_codes"]))
        IN.durable_write(self.state_dir / "gate" / task["id"] / "execution.json", result)

    def _finish_task(self, tid, wt, status=None):
        sh("git", "-C", str(self.scratch), "worktree", "remove",
           "--force", str(wt), check=False)
        self.state["current"] = None
        self.state["cycles_completed"] += 1
        if status and tid in self.state["tasks"]:
            self.state["tasks"][tid]["status"] = status
        self._save()
        # Refresh the owner dashboard snapshot.
        try:
            import dashboard as D
            D.render(self.state_dir, self.mission, self.queue, self.state)
        except Exception as exc:  # dashboard must never break the loop
            print(f"dashboard render failed (non-fatal): {exc}")
        return status or "done"


class _StopAfterPhase(Exception):
    def __init__(self, phase):
        self.phase = phase


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--revoke", action="store_true", help="durable stop serialized against branch updates")
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--provider", default=None, help="Airlock provider; offline sandbox only")
    ap.add_argument("--worker", default="worker-alpha")
    ap.add_argument("--state-dir", default=str(HERE / "state"))
    ap.add_argument("--stop-after-phase", default=None,
                    help="demo/test hook: halt after named phase")
    args = ap.parse_args()
    state_dir = Path(args.state_dir)
    if args.revoke:
        revoke_state(state_dir)
        return
    for _ in range(args.cycles):
        ctl = Controller(state_dir, args.worker,
                         stop_after_phase=args.stop_after_phase, provider=args.provider)
        try:
            outcome = ctl.run_once()
        except _StopAfterPhase as stop:
            print(f"halted after phase '{stop.phase}' (state preserved)")
            return
        if outcome in ("idle", "budget", "revoked"):
            break


if __name__ == "__main__":
    main()
