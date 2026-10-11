#!/usr/bin/env python3
"""REVIEW-DESK-001 server:  python server.py [--port 8771]

Local-first review desk. Serves the browser interface and a small JSON API.
Binds to 127.0.0.1 only. Review records and challenge records are written
as JSON files under experiments/review-desk-001/records/ (gitignored).

Nothing is published automatically: approving a draft records a local
human decision; there is no send/post path in this experiment.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from review import (  # noqa: E402  (local module, same directory)
    create_challenge, export_record, load_registry, review, utcnow,
)

HERE = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(HERE, "ui")
RECORDS_DIR = os.path.join(HERE, "records")

MIME = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
        ".json": "application/json"}


class Handler(BaseHTTPRequestHandler):
    server_version = "ReviewDesk/0.1"

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, indent=2))

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _record_path(self, kind, rid):
        os.makedirs(RECORDS_DIR, exist_ok=True)
        return os.path.join(RECORDS_DIR, f"{kind}-{rid}.json")

    # -- routes ---------------------------------------------------------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            return self._send(200, open(
                os.path.join(UI_DIR, "index.html"), "rb").read(),
                "text/html")
        if parsed.path.startswith("/ui/"):
            name = os.path.basename(parsed.path)
            if ".." in name or name not in ("app.js", "style.css"):
                return self._send(404, "not found", "text/plain")
            path = os.path.join(UI_DIR, name)
            if not os.path.exists(path):
                return self._send(404, "not found", "text/plain")
            ext = os.path.splitext(name)[1]
            return self._send(200, open(path, "rb").read(),
                              MIME.get(ext, "text/plain"))
        if parsed.path == "/api/registry":
            return self._json(200, load_registry())
        if parsed.path == "/api/records":
            records = []
            if os.path.isdir(RECORDS_DIR):
                for name in sorted(os.listdir(RECORDS_DIR)):
                    if name.endswith(".json"):
                        records.append(json.loads(open(
                            os.path.join(RECORDS_DIR, name)).read()))
            return self._json(200, {"records": records})
        if parsed.path == "/api/export":
            reviews, challenges = [], []
            if os.path.isdir(RECORDS_DIR):
                for name in sorted(os.listdir(RECORDS_DIR)):
                    doc = json.loads(open(
                        os.path.join(RECORDS_DIR, name)).read())
                    (reviews if name.startswith("rev-")
                     else challenges).append(doc)
            out = [export_record(r, [c for c in challenges
                                     if c.get("source_review_id")
                                     == r["review_id"]])
                   for r in reviews if r.get("review_id")]
            return self._json(200, {"exports": out})
        return self._send(404, "not found", "text/plain")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            body = self._read_json()
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"error": "invalid JSON body"})

        if parsed.path == "/api/review":
            comment = body.get("comment", "")
            if not isinstance(comment, str) or not comment.strip():
                return self._json(400, {"error": "comment is required"})
            rec = review(comment)
            path = self._record_path("rev", rec["review_id"])
            open(path, "w").write(json.dumps(rec, indent=2))
            return self._json(200, rec)

        if parsed.path == "/api/challenge":
            claim = body.get("claim", "")
            falsifier = body.get("proposed_falsifier", "")
            if not claim.strip() or not falsifier.strip():
                return self._json(
                    400, {"error": "claim and proposed_falsifier required"})
            rec = create_challenge(claim, falsifier,
                                   body.get("source_review_id"),
                                   body.get("evidence_refs"))
            path = self._record_path("chg", rec["challenge_id"])
            open(path, "w").write(json.dumps(rec, indent=2))
            return self._json(200, rec)

        if parsed.path == "/api/approve":
            rid = body.get("review_id", "")
            path = self._record_path("rev", rid)
            if not os.path.exists(path):
                return self._json(404, {"error": "review not found"})
            rec = json.loads(open(path).read())
            rec["human_approval"] = {
                "decision": body.get("decision", "approved"),
                "note": body.get("note", ""),
                "approved_at": utcnow(),
                "approved_draft": rec["draft"]["draft"],
            }
            open(path, "w").write(json.dumps(rec, indent=2))
            return self._json(200, rec)

        return self._send(404, "not found", "text/plain")

    def log_message(self, *args):  # keep local console quiet-ish
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8771)
    args = ap.parse_args()
    server = HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"review-desk on http://127.0.0.1:{args.port} "
          f"(local only; records -> {RECORDS_DIR})")
    server.serve_forever()


if __name__ == "__main__":
    main()
