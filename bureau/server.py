#!/usr/bin/env python3
"""OpenLine Bureau server:  python -m bureau.server [--db bureau.db] [--port 8765]

Stdlib only. Serves the analyst UI and a read-only JSON API.
No auth, no writes, no inference — deterministic software.
"""

import argparse
import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from .store import Store
from . import metrics as M
from .conformance import CLAIMS, evaluate_claims

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui")

TIMELINE_EVENTS = (
    "mandate_issued", "mandate_narrowed", "mandate_revoked",
    "mandate_superseded", "mandate_expired", "stale_authority_attempt",
    "revocation_propagated", "action_proposed", "action_committed",
    "action_refused", "action_stopped",
)

INCIDENT_EVENTS = (
    "action_proposed", "semantic_challenge", "semantic_hold", "false_hold",
    "challenge_reconciled", "challenge_unresolved", "action_quarantined",
    "action_stopped", "action_refused", "mandate_revoked",
    "revocation_propagated", "recovery_proposed", "recovery_succeeded",
    "recovery_failed", "successor_continuation", "continuity_failure",
    "provider_replacement", "apparatus_incomplete",
)


class Handler(BaseHTTPRequestHandler):
    server_version = "Bureau/0.1"

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, default=str))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        store = self.server.store

        def q(name):
            v = qs.get(name)
            return v[0] if v else None

        try:
            if path == "/api/overview":
                window = {"since": q("since"), "until": q("until")}
                ms = M.compute_all(store, since=q("since"), until=q("until"))
                self._json({"window": window, "metrics": ms,
                            "receipt_count": store.count()})
            elif path == "/api/ledger":
                self._json({"records": store.ledger(
                    actor=q("actor"), decision=q("decision"),
                    event_type=q("event_type"), experiment=q("experiment"),
                    system=q("system"), authority_state=q("authority_state"),
                    since=q("since"), until=q("until"),
                    limit=int(q("limit") or 500),
                    offset=int(q("offset") or 0))})
            elif path.startswith("/api/receipt/"):
                rid = urllib.parse.unquote(path[len("/api/receipt/"):])
                rec = store.get(rid)
                if rec is None:
                    self._json({"error": "not found"}, 404)
                    return
                parents = [store.get(p) for p in rec["parent_receipts"]]
                # External receipts carry a claim panel: what the receipt's
                # own evidence supports vs. what remains not established.
                claims = None
                if rec.get("adapter") == "external_receipt" \
                        and isinstance(rec.get("raw"), dict):
                    try:
                        ev = evaluate_claims(rec["raw"])
                        claims = {
                            "supported": [c for c in CLAIMS if ev[c]["supported"]],
                            "not_established": [
                                {"claim": c, "missing": ev[c]["missing"]}
                                for c in CLAIMS if not ev[c]["supported"]],
                        }
                    except Exception:
                        claims = None  # fail soft: panel just doesn't render
                self._json({"record": rec,
                            "parents": [p for p in parents if p],
                            "children": store.children_of(rid),
                            "claims": claims})
            elif path == "/api/timeline":
                recs = []
                for et in TIMELINE_EVENTS:
                    recs.extend(store.ledger(
                        event_type=et, actor=q("actor"),
                        principal=q("principal"), experiment=q("experiment"),
                        since=q("since"), until=q("until"), limit=1000000))
                recs.sort(key=lambda r: (r["timestamp"] is None,
                                          r["timestamp"] or "",
                                          r["receipt_id"]))
                self._json({"events": recs})
            elif path == "/api/incidents":
                recs = []
                for et in INCIDENT_EVENTS:
                    recs.extend(store.ledger(
                        event_type=et, experiment=q("experiment"),
                        since=q("since"), until=q("until"), limit=1000000))
                groups = {}
                for r in recs:
                    key = r["experiment"] or "(no experiment)"
                    groups.setdefault(key, []).append(r)
                seqs = []
                for exp, rs in sorted(groups.items()):
                    rs.sort(key=lambda r: (r["timestamp"] is None,
                                            r["timestamp"] or "",
                                            r["receipt_id"]))
                    seqs.append({"experiment": exp, "events": rs,
                                 "observed": sum(1 for r in rs
                                                 if r["effect_observed"] is not None),
                                 "unresolved": sum(1 for r in rs if r["event_type"] in (
                                     "challenge_unresolved",
                                     "unresolved_standing",
                                     "apparatus_incomplete"))})
                self._json({"sequences": seqs})
            elif path == "/api/coverage":
                self._json({"capabilities": coverage(store)})
            elif path == "/api/facets":
                self._json({c: store.distinct(c) for c in (
                    "system", "experiment", "actor", "principal", "decision",
                    "event_type", "authority_state", "standing", "adapter",
                    "source_repo")})
            elif path == "/" or path == "/index.html":
                self._serve_file("index.html", "text/html")
            elif path.startswith("/ui/"):
                rel = path[len("/ui/"):]
                ctype = ("text/css" if rel.endswith(".css")
                         else "application/javascript" if rel.endswith(".js")
                         else "text/html")
                self._serve_file(rel, ctype)
            else:
                self._json({"error": "not found"}, 404)
        except BrokenPipeError:
            pass
        except Exception as e:  # fail visible, never silent
            self._json({"error": "%s: %s" % (type(e).__name__, e)}, 500)

    def _serve_file(self, rel, ctype):
        full = os.path.normpath(os.path.join(UI_DIR, rel))
        if not full.startswith(os.path.abspath(UI_DIR) + os.sep):
            self._json({"error": "forbidden"}, 403)
            return
        try:
            with open(full, "rb") as f:
                data = f.read()
        except OSError:
            self._json({"error": "not found"}, 404)
            return
        self._send(200, data, ctype)

    def log_message(self, *a):  # quiet
        pass


def coverage(store):
    """What the Bureau can and cannot know. Exactly three epistemic states:

    OBSERVED   — read directly from receipts.
    DERIVED    — computed from two or more observed facts.
    UNKNOWN    — not observable from the Bureau's evidence, by construction.
    """
    total = store.count()

    actionish = store.ledger(limit=1000000)
    with_authority = sum(1 for r in actionish if r["authority_state"])
    with_decision = sum(1 for r in actionish if r["decision"])
    with_effect = sum(1 for r in actionish if r["effect_observed"] is not None)
    with_ts = sum(1 for r in actionish if r["timestamp"])
    rev_pairs = M.compute_all(store)["revocation_propagation_lag"]

    def row(capability, status, evidence_count, note):
        assert status in ("OBSERVED", "DERIVED", "UNKNOWN"), status
        return {"capability": capability, "status": status,
                "evidence_count": evidence_count, "note": note}

    rows = [
        row("CURRENT AUTHORITY AT RECEIVER", "OBSERVED", with_authority,
            "%d of %d records carry an authority_state" % (with_authority, total)),
        row("RECEIVER DECISION", "OBSERVED", with_decision,
            "%d of %d records carry a decision" % (with_decision, total)),
        row("EFFECT CONFIRMATION", "OBSERVED", with_effect,
            "observed where a receipt exists: %d of %d records state whether "
            "the effect was observed; the rest are unknown, not assumed"
            % (with_effect, total)),
        row("PROVENANCE", "OBSERVED", total,
            "every normalized record carries source_repo, source_path, "
            "adapter, and raw_ref"),
        row("TEMPORAL ORDERING", "OBSERVED", with_ts,
            "%d of %d records carry a timestamp" % (with_ts, total)),
        row("AGENT HIDDEN INTENT", "UNKNOWN", 0,
            "no adapter observes intent; CHALLENGE records carry the "
            "guardian's stated reason only"),
        row("ACTIONS THROUGH CREDENTIALS OUTSIDE THE RECEIVER", "UNKNOWN", 0,
            "receipts only cover instrumented consequence boundaries; an "
            "unmonitored path leaves no receipt by construction"),
        row("UNINSTRUMENTED ACTUATOR BEHAVIOR", "UNKNOWN", 0,
            "effect confirmation exists only where receipts were produced; "
            "an actuator the Bureau cannot see is silent here"),
        row("ABSENCE OF UNOBSERVED ACTIONS", "UNKNOWN", 0,
            "absence of a receipt is not evidence of absence of action"),
    ]

    # Revocation propagation lag is derived from two observed timestamps.
    # Where no revocation->enforcement pair exists, it is UNKNOWN from
    # these receipts — never estimated.
    if rev_pairs["measurable"]:
        rows.append(row("REVOCATION PROPAGATION LAG", "DERIVED",
                        rev_pairs["source_event_count"],
                        "derived from two observed timestamps: revocation "
                        "and first confirmed enforcement; %d pair(s) measured"
                        % rev_pairs["source_event_count"]))
    else:
        rows.append(row("REVOCATION PROPAGATION LAG", "UNKNOWN", 0,
                        "not measurable from available receipts: %s"
                        % (rev_pairs["reason_not_measurable"] or "")))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="bureau.db")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args(argv)
    store = Store(args.db)
    srv = HTTPServer((args.host, args.port), Handler)
    srv.store = store
    print("bureau on http://%s:%d/  (db=%s, receipts=%d)"
          % (args.host, args.port, args.db, store.count()))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        store.close()


if __name__ == "__main__":
    main()
