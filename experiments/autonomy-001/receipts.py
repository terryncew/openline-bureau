"""OPENLINE-AUTONOMY-001 receipts: Bureau-compatible decision records.

Every consequential controller decision becomes a bureau.receipt.v0.1
record, validated by bureau/conformance.py before it is stored. The
receipts are evidence of what the controller decided and why — they do
not prove the underlying work was correct; the evaluation results
attached to each receipt are the evidence for that.

Receipts are unsigned in Phase 1 (no signing key configured): structure
is validated, authenticity is out of scope and stated as such.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from bureau.conformance import validate  # noqa: E402


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_receipt(kind: str, task_id: str | None, worker_id: str | None,
                 decision: str, reason: str, run_id: str,
                 evidence: dict | None = None) -> dict:
    """Build and validate a controller decision receipt."""
    receipt = {
        "receipt_version": "bureau.receipt.v0.1",
        "receipt_id": f"autonomy-001-{uuid.uuid4().hex[:12]}",
        "timestamp": utcnow(),
        "receiver": "autonomy-001-coordinator",
        "principal": "owner:Terrynce White",
        "actor": f"worker:{worker_id}" if worker_id else "coordinator",
        "action": {
            "type": kind,
            "target": "experiments/review-desk-001",
            "action_id": task_id or f"run-{run_id}",
        },
        "authority": {"status": "ACTIVE"},
        "decision": {"outcome": decision, "reason": reason},
        "effect": {"effect_id": f"autonomy-001:{kind}:{task_id or run_id}",
                   "observed": decision in ("COMMIT", "DENY")},
        "provenance": {"system": "openline-autonomy-001",
                       "source_ref": f"run/{run_id}"},
        "extensions": {
            "autonomy": {
                "run_id": run_id,
                "kind": kind,
                "task_id": task_id,
                "worker_id": worker_id,
                "evidence": evidence or {},
                "signed": False,
                "signature_note": "Phase 1 receipts are unsigned; "
                                  "structure validated, authenticity "
                                  "not established.",
            }
        },
    }
    result = validate(receipt)
    if result["status"] not in ("VALID", "CONFORMANT_NO_CLAIMS"):
        raise ValueError(f"receipt failed conformance: {result['problems']}")
    receipt["_conformance"] = result["status"]
    return receipt


def store_receipt(receipts_dir: Path, receipt: dict) -> Path:
    receipts_dir.mkdir(parents=True, exist_ok=True)
    path = receipts_dir / f"{receipt['receipt_id']}.json"
    path.write_text(json.dumps(receipt, indent=2))
    return path
