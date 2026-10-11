"""OPENLINE-AUTONOMY-001 tests: the controller loop's safety properties.

Each test runs the real coordinator against a scratch clone of the
repository, with scripted workers standing in for agent workers. What is
under test is the LOOP (select/assign/build/evaluate/decide/record),
not worker intelligence.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP))
sys.path.insert(0, str(EXP.parents[2]))

os.environ["AUTONOMY_TARGET_REPO"] = str(EXP.parents[1])

from coordinator import Controller  # noqa: E402
from bureau.conformance import validate  # noqa: E402


def _queue(*ids):
    all_tasks = {t["id"]: t
                 for t in json.loads((EXP / "queue" / "tasks.json")
                                    .read_text())["queue"]}
    return {i: all_tasks[i] for i in ids}


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state"

    def tearDown(self):
        self.tmp.cleanup()

    def ctl(self, worker="worker-alpha", queue_ids=None):
        c = Controller(self.state, worker)
        if queue_ids is not None:
            c.queue = _queue(*queue_ids)
        return c

    def receipts(self, c):
        out = []
        for p in (self.state / "receipts").glob("*.json"):
            out.append(json.loads(p.read_text()))
        return out

    def scratch_branches(self):
        r = subprocess.run(["git", "branch", "--list",
                            "autonomy-001/accepted/*"],
                           cwd=self.state / "scratch",
                           capture_output=True, text=True)
        return [b.strip() for b in r.stdout.splitlines() if b.strip()]


class AcceptTests(_Base):
    def test_docs_only_accepted(self):
        c = self.ctl(queue_ids=["readme-export-docs"])
        self.assertEqual(c.run_once(), "accepted")
        self.assertEqual(c.state["tasks"]["readme-export-docs"]["status"],
                         "accepted")
        self.assertIn("autonomy-001/accepted/readme-export-docs",
                      self.scratch_branches())

    def test_ui_copy_accepted(self):
        c = self.ctl(queue_ids=["ui-empty-records"])
        self.assertEqual(c.run_once(), "accepted")


class RejectHoldTests(_Base):
    def test_bug_injection_rejected(self):
        c = self.ctl(queue_ids=["bug-injection"])
        self.assertEqual(c.run_once(), "rejected")
        self.assertEqual(c.state["tasks"]["bug-injection"]["status"],
                         "rejected")
        self.assertNotIn("autonomy-001/accepted/bug-injection",
                         self.scratch_branches())

    def test_registry_change_quarantined_before_write(self):
        c = self.ctl(queue_ids=["registry-add-claim"])
        self.assertEqual(c.run_once(), "done")
        self.assertEqual(c.state["tasks"]["registry-add-claim"]["status"],
                         "quarantined")
        self.assertNotIn("autonomy-001/accepted/registry-add-claim",
                         self.scratch_branches())

    def test_rules_rewrite_quarantined(self):
        c = self.ctl(queue_ids=["rules-rewrite"])
        c.run_once()
        self.assertEqual(c.state["tasks"]["rules-rewrite"]["status"],
                         "quarantined")
        recs = [r for r in self.receipts(c)
                if r["action"]["action_id"] == "rules-rewrite"]
        self.assertTrue(any("QUARANTINED" in r["decision"]["reason"]
                            for r in recs))


class AuthorityTests(_Base):
    def test_revoked_mission_starts_nothing(self):
        import yaml
        from unittest.mock import patch

        mission_path = Path(self.tmp.name) / "mission.yaml"
        doc = yaml.safe_load((EXP / "mission.yaml").read_text())
        doc["revoked"] = True
        mission_path.write_text(yaml.safe_dump(doc))
        with patch("coordinator.MISSION_PATH", mission_path):
            c = self.ctl(queue_ids=["readme-export-docs"])
            self.assertEqual(c.run_once(), "revoked")
            self.assertEqual(c.state["tasks"], {})

    def test_receipts_conform(self):
        c = self.ctl(queue_ids=["readme-export-docs", "bug-injection"])
        c.run_once()
        c2 = Controller(self.state, "worker-alpha")
        c2.queue = _queue("bug-injection")
        c2.run_once()
        for p in (self.state / "receipts").glob("*.json"):
            rec = json.loads(p.read_text())
            rec.pop("_conformance", None)
            result = validate(rec)
            self.assertIn(result["status"], ("VALID", "CONFORMANT_NO_CLAIMS"),
                          result["problems"])


class ContinuityTests(_Base):
    def test_worker_swap_preserves_mission_and_history(self):
        c1 = self.ctl(worker="worker-alpha",
                      queue_ids=["readme-export-docs"])
        c1.run_once()
        c2 = Controller(self.state, "worker-beta")
        c2.queue = _queue("ui-empty-records")
        c2.run_once()
        self.assertEqual(
            c2.state["mission_digest"], c1.state["mission_digest"])
        workers = {r["actor"] for r in self.receipts(c2)
                   if r["actor"].startswith("worker:")}
        self.assertIn("worker:worker-alpha", workers)
        self.assertIn("worker:worker-beta", workers)
        self.assertEqual(c2.state["tasks"]["readme-export-docs"]["status"],
                         "accepted")
        self.assertEqual(c2.state["tasks"]["ui-empty-records"]["status"],
                         "accepted")

    def test_restart_resumes_after_build(self):
        from coordinator import _StopAfterPhase
        c1 = Controller(self.state, "worker-alpha",
                        stop_after_phase="build")
        c1.queue = _queue("readme-export-docs")
        with self.assertRaises(_StopAfterPhase):
            c1.run_once()  # halts after build; state preserved
        self.assertTrue((self.state / "state.json").exists())
        c2 = Controller(self.state, "worker-alpha")
        c2.queue = _queue("readme-export-docs")
        # Recovery holds the interrupted task without repeating the worker.
        self.assertEqual(c2.run_once(), "held")

    def test_budgets_enforced(self):
        c = self.ctl(queue_ids=["readme-export-docs"])
        c.mission["budgets"]["max_cycles"] = 0
        self.assertEqual(c.run_once(), "budget")


if __name__ == "__main__":
    unittest.main()
