#!/usr/bin/env python3
"""OpenLine Bureau ingest:  python -m bureau.ingest <path> [--db bureau.db]

<path> may be a JSON file or a directory (recursed). Sources are read
read-only and never mutated. Unsupported payloads fail visibly as
UNSUPPORTED_RECEIPT_FORMAT — they are listed, never silently ignored.
"""

import argparse
import json
import os
import sys

from .adapters import adapt, UnsupportedReceiptFormat, detect
from .store import Store


def _provenance(path, args):
    return {
        "source_repo": args.source_repo or "local",
        "source_commit": args.source_commit,
        "source_path": os.path.abspath(path),
        "raw_ref": os.path.abspath(path),
    }


def ingest_path(path, store, args, stats):
    stats["files_seen"] += 1
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        stats["unreadable"].append((path, "%s: %s" % (type(e).__name__, e)))
        return
    adapter_name = detect(payload)
    if adapter_name is None:
        stats["unsupported"].append(path)
        return
    stats["adapters_used"].add(adapter_name)
    try:
        records = adapt(payload, _provenance(path, args))
    except UnsupportedReceiptFormat as e:
        stats["unsupported"].append("%s (%s)" % (path, e) if str(e) else path)
        return
    except Exception as e:  # adapter bug: fail loud per file
        stats["adapter_errors"].append((path, "%s: %s" % (type(e).__name__, e)))
        return
    # stamp experiment/system overrides when provided
    for r in records:
        if args.experiment and not r.get("experiment"):
            r["experiment"] = args.experiment
        if args.system and not r.get("system"):
            r["system"] = args.system
    s = store.ingest_many(records)
    stats["inserted"] += s["inserted"]
    stats["duplicate"] += s["duplicate"]
    stats["invalid"] += s["invalid"]
    stats["errors"].extend(s["errors"])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ingest receipts into the Bureau store.")
    ap.add_argument("path", help="JSON file or directory to ingest (read-only)")
    ap.add_argument("--db", default="bureau.db", help="SQLite store path")
    ap.add_argument("--source-repo", default=None)
    ap.add_argument("--source-commit", default=None)
    ap.add_argument("--experiment", default=None,
                    help="label attached when the payload carries none")
    ap.add_argument("--system", default=None,
                    help="label attached when the payload carries none")
    args = ap.parse_args(argv)

    store = Store(args.db)
    stats = {"files_seen": 0, "inserted": 0, "duplicate": 0, "invalid": 0,
             "unsupported": [], "unreadable": [], "adapter_errors": [],
             "errors": [], "adapters_used": set()}

    if os.path.isdir(args.path):
        for root, _dirs, files in os.walk(args.path):
            for fn in sorted(files):
                if fn.endswith(".json"):
                    ingest_path(os.path.join(root, fn), store, args, stats)
    else:
        ingest_path(args.path, store, args, stats)

    store.close()
    # Machine-readable line (kept stable for tooling).
    print("files_seen=%d inserted=%d duplicate=%d invalid=%d adapters=%s"
          % (stats["files_seen"], stats["inserted"], stats["duplicate"],
             stats["invalid"], sorted(stats["adapters_used"])))
    # Human-readable summary. Sources are opened read-only and never
    # written; "source files modified" is a standing guarantee, not a guess.
    print("---")
    print("Bureau ingest summary")
    print("  receipts ingested:    %d" % stats["inserted"])
    print("  duplicates skipped:   %d" % stats["duplicate"])
    print("  unsupported formats:  %d" % len(stats["unsupported"]))
    print("  unreadable files:     %d" % len(stats["unreadable"]))
    print("  invalid records:      %d" % stats["invalid"])
    print("  adapters used:        %s"
          % (", ".join(sorted(stats["adapters_used"])) or "none"))
    print("  source files modified: 0")
    for p in stats["unsupported"]:
        print("UNSUPPORTED_RECEIPT_FORMAT: %s" % p)
    for p, e in stats["unreadable"]:
        print("UNREADABLE: %s (%s)" % (p, e))
    for p, e in stats["adapter_errors"]:
        print("ADAPTER_ERROR: %s (%s)" % (p, e))
    for e in stats["errors"]:
        print("RECORD_ERROR: %s" % e)
    return 0 if not (stats["unreadable"] or stats["adapter_errors"]
                     or stats["errors"]) else 1


if __name__ == "__main__":
    sys.exit(main())
