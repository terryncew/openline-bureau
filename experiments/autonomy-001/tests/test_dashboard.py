"""Snapshot rendering must not execute text supplied by an untrusted worker."""

import json
import sys
import tempfile
import unittest
from html import escape
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard import render  # noqa: E402


class _Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class DashboardTests(unittest.TestCase):
    def test_untrusted_snapshot_values_are_inert_text(self):
        script = "<script>alert('mission')</script>"
        markup = '<img src="x" onerror="alert(1)">'
        attr = "pending' onmouseover='alert(1)"
        queue = {markup: {"title": script, "change_class": markup}}
        state = {
            "tasks": {markup: {"status": attr}},
            "current": {"task_id": markup, "phase": script, "worker_id": attr},
            "cycles_completed": markup,
        }
        mission = {"mission": script, "revoked": markup}
        receipt = {
            "receipt_id": markup,
            "extensions": {"autonomy": {"kind": script}},
            "decision": {"outcome": script, "reason": "BUILD_FAIL: " + markup},
            "timestamp": markup,
        }
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            (state_dir / "receipts").mkdir()
            (state_dir / "receipts" / "failure.json").write_text(json.dumps(receipt))
            render(state_dir, mission, queue, state)
            output = (state_dir / "dashboard.html").read_text()

        self.assertIn(escape("BUILD_FAIL: " + markup, quote=True), output)
        self.assertIn(escape(script, quote=True), output)
        self.assertIn(escape(attr, quote=True), output)
        parser = _Elements()
        parser.feed(output)
        self.assertFalse(any(tag in {"script", "img"} for tag, _ in parser.elements))
        self.assertFalse(any(name.startswith("on")
                             for _, attrs in parser.elements for name in attrs))
        self.assertIn(("td", {"class": ""}), parser.elements)

    def test_dashboard_documents_serialized_revocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            render(state_dir, {"mission": "test", "revoked": False}, {},
                   {"tasks": {}, "current": None, "cycles_completed": 0})
            output = (state_dir / "dashboard.html").read_text()
        self.assertIn("coordinator.py --state-dir &lt;state-dir&gt; --revoke", output)
        self.assertNotIn("edit mission.yaml", output)


if __name__ == "__main__":
    unittest.main()
