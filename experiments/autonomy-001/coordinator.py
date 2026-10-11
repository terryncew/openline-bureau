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

MISSION_PATH = HERE / "mission.yaml"
POLICY_PATH = HERE / "policy" / "authorized.json"
QUEUE_PATH = HERE / "queue" / "tasks.json"

PHASES = ("select", "assign", "build", "evaluate", "decide", "record")


def sh(*args, cwd=None, check=True):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          check=check)


def atomic_write(path: Path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    os.replace(tmp, path)


def load_mission():
    mission = yaml.safe_load(MISSION_PATH.read_text())
    digest = hashlib.sha256(MISSION_PATH.read_bytes()).hexdigest()
    return mission, digest


def load_policy():
    return json.loads(POLICY_PATH.read_text())


def load_queue():
    return json.loads(QUEUE_PATH.read_text())["queue"]


class Controller:
    def __init__(self, state_dir: Path, worker_id: str,
                 stop_after_phase: str | None = None):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = state_dir / "state.json"
        self.receipts_dir = state_dir / "receipts"
        self.scratch = state_dir / "scratch"
        self.worker_id = worker_id
        self.stop_after_phase = stop_after_phase
        self.mission, self.mission_digest = load_mission()
        self.policy = load_policy()
        self.queue = {t["id"]: t for t in load_queue()}
        self.run_id = uuid.uuid4().hex[:8]
        self.state = self._load_or_init()

    # -- state ---------------------------------------------------------
    def _load_or_init(self):
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text())
            if state.get("mission_digest") != self.mission_digest:
                raise SystemExit(
                    "mission.yaml changed mid-run: halting for owner review")
            return state
        return {"run_id": self.run_id, "mission_digest": self.mission_digest,
                "tasks": {}, "current": None, "cycles_completed": 0,
                "receipts": []}

    def _save(self):
        atomic_write(self.state_path, self.state)

    def _receipt(self, kind, task_id, worker_id, decision, reason,
                 evidence=None):
        rec = RC.make_receipt(kind, task_id, worker_id, decision, reason,
                              self.run_id, evidence)
        path = RC.store_receipt(self.receipts_dir, rec)
        self.state["receipts"].append(rec["receipt_id"])
        self._save()
        return rec, path

    def _revoked(self):
        # Re-read the file every time: the owner can revoke at any moment.
        return yaml.safe_load(MISSION_PATH.read_text()).get("revoked", False)

    def _check_stop(self, phase):
        if self.stop_after_phase == phase:
            print(f"[demo hook] stopping after phase: {phase}")
            raise _StopAfterPhase(phase)

    # -- target setup ---------------------------------------------------
    def _ensure_scratch(self):
        if not (self.scratch / ".git").exists():
            target_repo = os.environ.get(
                "AUTONOMY_TARGET_REPO",
                str(HERE.parents[2]))  # the bureau checkout by default
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
        if self._revoked():
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

        tid = task["id"]
        self.state["current"] = {"task_id": tid, "phase": "select",
                                 "worker_id": self.worker_id}
        self._save()
        self._check_stop("select")

        # ASSIGN
        worker = W.ScriptedWorker(self.worker_id)
        self.state["current"]["phase"] = "assign"
        self._save()
        self._receipt("assign", tid, self.worker_id, "COMMIT",
                      f"task assigned to {self.worker_id}",
                      {"queue_priority": task["priority"]})
        self._check_stop("assign")

        # BUILD (isolated worktree at pinned baseline)
        baseline = self._ensure_scratch()
        wt = self._worktree(tid, baseline)
        self.state["current"]["phase"] = "build"
        self._save()
        scope = self.mission["target"]["scope_paths"]
        protected = self.mission["boundaries"]["protected_paths"]
        build = worker.build(task, wt, scope, protected)
        self._check_stop("build")

        if not build.ok:
            self._quarantine_or_reject(task, build, wt)
            return self._finish_task(tid, wt)

        # EVALUATE (independent: protected tests restored, holdout injected)
        self.state["current"]["phase"] = "evaluate"
        self._save()
        hold = EV.prepare_holdout(wt, HERE / "holdout")
        try:
            ev = EV.evaluate(
                task, wt, Path(self.scratch), ".holdout_tmp",
                HERE.parent / "review-desk-001",
                self.mission["budgets"])
        finally:
            EV.cleanup_holdout(wt)
        self._check_stop("evaluate")

        # DECIDE
        self.state["current"]["phase"] = "decide"
        self._save()
        if self._revoked():
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

        if self._policy_allows(task, build):
            branch = f"autonomy-001/accepted/{tid}"
            self._accept_to_branch(wt, branch, task)
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

    def _accept_to_branch(self, wt, branch, task):
        # Apply the evaluated worktree diff onto a fresh isolated branch.
        # Main is never touched; the paused baseline branch is never touched.
        sh("git", "-C", str(self.scratch), "branch", "-D", branch,
           check=False)
        baseline = self.mission["target"]["baseline_commit"]
        accept_wt = self.state_dir / "wt" / f"accept-{task['id']}"
        if accept_wt.exists():
            shutil.rmtree(accept_wt, ignore_errors=True)
        sh("git", "-C", str(self.scratch), "worktree", "add", "-b",
           branch, str(accept_wt), baseline)
        patch = sh("git", "-C", str(wt), "diff").stdout
        proc = subprocess.run(["git", "apply"], input=patch, cwd=accept_wt,
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"patch apply failed: {proc.stderr[:300]}")
        sh("git", "-C", str(accept_wt), "add", "-A")
        sh("git", "-C", str(accept_wt), "-c", "user.name=autonomy-001",
           "-c", "user.email=autonomy-001@local",
           "commit", "-qm",
           f"autonomy-001: accept {task['id']} ({task['change_class']})")
        sh("git", "-C", str(self.scratch), "worktree", "remove",
           "--force", str(accept_wt), check=False)

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
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--worker", default="worker-alpha")
    ap.add_argument("--state-dir", default=str(HERE / "state"))
    ap.add_argument("--stop-after-phase", default=None,
                    help="demo/test hook: halt after named phase")
    args = ap.parse_args()
    state_dir = Path(args.state_dir)
    for _ in range(args.cycles):
        ctl = Controller(state_dir, args.worker,
                         stop_after_phase=args.stop_after_phase)
        try:
            outcome = ctl.run_once()
        except _StopAfterPhase as stop:
            print(f"halted after phase '{stop.phase}' (state preserved)")
            return
        if outcome in ("idle", "budget", "revoked"):
            break


if __name__ == "__main__":
    main()
