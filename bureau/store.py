#!/usr/bin/env python3
"""OpenLine Bureau — normalized SQLite store.

- receipt_id is the dedup key: re-ingesting the same receipt is a no-op
  (counted, not duplicated).
- Sources are never mutated; the store only holds normalized copies plus
  provenance pointers.
"""

import json
import sqlite3
from datetime import datetime, timezone

from .schema import validate

_TABLE = """
CREATE TABLE IF NOT EXISTS receipts (
    receipt_id      TEXT PRIMARY KEY,
    timestamp       TEXT,
    system          TEXT,
    experiment      TEXT,
    principal       TEXT,
    actor           TEXT,
    action          TEXT,
    target          TEXT,
    authority_state TEXT,
    decision        TEXT,
    event_type      TEXT,
    reason          TEXT,
    effect_observed INTEGER,          -- 1 / 0 / NULL
    standing        TEXT,
    parent_receipts TEXT,             -- JSON list
    source_repo     TEXT NOT NULL,
    source_commit   TEXT,
    source_path     TEXT NOT NULL,
    raw_ref         TEXT,
    adapter         TEXT NOT NULL,
    ingested_at     TEXT NOT NULL,
    raw             TEXT,             -- JSON or NULL
    unmapped        TEXT              -- JSON or NULL
);
CREATE INDEX IF NOT EXISTS idx_ts        ON receipts(timestamp);
CREATE INDEX IF NOT EXISTS idx_system    ON receipts(system);
CREATE INDEX IF NOT EXISTS idx_actor     ON receipts(actor);
CREATE INDEX IF NOT EXISTS idx_decision  ON receipts(decision);
CREATE INDEX IF NOT EXISTS idx_event     ON receipts(event_type);
CREATE INDEX IF NOT EXISTS idx_experiment ON receipts(experiment);
"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path):
        self.path = path
        # check_same_thread=False: the Bureau server creates the Store in
        # the main thread and serves requests from the server thread.
        # Requests are handled sequentially, so no concurrent access occurs.
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_TABLE)

    def close(self):
        self.db.close()

    # -- ingest -----------------------------------------------------------
    def insert(self, rec):
        """Insert one validated record. Returns 'inserted' or 'duplicate'."""
        problems = validate(rec)
        if problems:
            raise ValueError("invalid record %r: %s"
                             % (rec.get("receipt_id"), "; ".join(problems)))
        rec = dict(rec)
        if not rec.get("ingested_at"):
            rec["ingested_at"] = _now()
        row = (
            rec["receipt_id"], rec["timestamp"], rec["system"], rec["experiment"],
            rec["principal"], rec["actor"], rec["action"], rec["target"],
            rec["authority_state"], rec["decision"], rec["event_type"],
            rec["reason"],
            None if rec["effect_observed"] is None else int(bool(rec["effect_observed"])),
            rec["standing"],
            json.dumps(rec["parent_receipts"] or []),
            rec["source_repo"], rec["source_commit"], rec["source_path"],
            rec["raw_ref"], rec["adapter"], rec["ingested_at"],
            json.dumps(rec["raw"], default=str) if rec["raw"] is not None else None,
            json.dumps(rec.get("unmapped") or {}, default=str),
        )
        try:
            self.db.execute(
                "INSERT INTO receipts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
            self.db.commit()
            return "inserted"
        except sqlite3.IntegrityError:
            return "duplicate"

    def ingest_many(self, records):
        stats = {"inserted": 0, "duplicate": 0, "invalid": 0, "errors": []}
        for rec in records:
            try:
                stats[self.insert(rec)] += 1
            except ValueError as e:
                stats["invalid"] += 1
                stats["errors"].append(str(e))
        return stats

    # -- reads ------------------------------------------------------------
    def _row_to_dict(self, r):
        d = dict(r)
        d["effect_observed"] = (None if d["effect_observed"] is None
                                else bool(d["effect_observed"]))
        d["parent_receipts"] = json.loads(d["parent_receipts"] or "[]")
        d["raw"] = json.loads(d["raw"]) if d["raw"] else None
        d["unmapped"] = json.loads(d["unmapped"] or "{}")
        return d

    def get(self, receipt_id):
        r = self.db.execute("SELECT * FROM receipts WHERE receipt_id = ?",
                            (receipt_id,)).fetchone()
        return self._row_to_dict(r) if r else None

    def count(self):
        return self.db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]

    def ledger(self, actor=None, principal=None, decision=None, event_type=None,
               experiment=None, system=None, authority_state=None,
               since=None, until=None, limit=500, offset=0):
        """Chronological ledger with optional filters. NULL timestamps sort last."""
        clauses, params = [], []
        for col, val in (("actor", actor), ("principal", principal),
                         ("decision", decision),
                         ("event_type", event_type),
                         ("experiment", experiment), ("system", system),
                         ("authority_state", authority_state)):
            if val is not None:
                clauses.append("%s = ?" % col)
                params.append(val)
        if since is not None:
            clauses.append("timestamp >= ?")
            params.append(since)
        if until is not None:
            clauses.append("timestamp <= ?")
            params.append(until)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        q = ("SELECT * FROM receipts %s ORDER BY "
             "(timestamp IS NULL), timestamp, receipt_id LIMIT ? OFFSET ?"
             % where)
        rows = self.db.execute(q, params + [limit, offset]).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def children_of(self, receipt_id):
        """Receipts that name receipt_id as a parent (forward ancestry)."""
        out = []
        for r in self.db.execute("SELECT * FROM receipts").fetchall():
            d = self._row_to_dict(r)
            if receipt_id in d["parent_receipts"]:
                out.append(d)
        return out

    def distinct(self, column):
        if column not in ("system", "experiment", "actor", "principal",
                          "decision", "event_type", "authority_state",
                          "standing", "adapter", "source_repo"):
            raise ValueError("not a facetable column: %r" % column)
        return [r[0] for r in
                self.db.execute("SELECT DISTINCT %s FROM receipts "
                                "WHERE %s IS NOT NULL ORDER BY 1" % (column, column))]
