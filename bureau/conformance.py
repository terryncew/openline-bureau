#!/usr/bin/env python3
"""OpenLine Bureau Conformance Kit v0.1 — validator and claim engine.

Answers one question: what can an EXTERNAL receiver (a system that does not
run OpenLine) prove happened, using only a minimal consequence receipt?

Structural conformance (shape, vocabulary, internal consistency) is kept
strictly separate from cryptographic authenticity (signatures, hash
binding). A structurally valid receipt is NOT automatically authenticated;
when signatures are absent the validator says so, and when present they are
preserved and exposed.

Unknown stays unknown: a receipt that proves a decision was DENY but
carries no effect evidence supports RECEIVER_DECISION_OBSERVED and nothing
more. Claims that cannot be evidenced are reported as NOT ESTABLISHED,
never assumed.

No network, no model calls, no external dependencies. Deterministic.
"""

import json
import os

# ---------------------------------------------------------------------------
# Format identity
# ---------------------------------------------------------------------------

RECEIPT_VERSION = "bureau.receipt.v0.1"
RECEIPT_FAMILY_PREFIX = "bureau.receipt."

# Required top-level fields (structural). Everything else is optional:
# a receipt may support only one or two claims.
REQUIRED_FIELDS = ("receipt_version", "receipt_id", "timestamp", "receiver")

# Controlled vocabularies for the core schema. Free-form descriptive fields
# (action.type, reason, system names) are preserved verbatim, never coerced.
DECISION_OUTCOMES = frozenset([
    "COMMIT",      # protected consequence allowed; effect observed separately
    "DENY",        # refused by policy/gate
    "QUARANTINE",  # held for review; consequence did not proceed
    "STOPPED",     # halted: outside mandate, revoked authority, replay, etc.
    "OBSERVED",    # no decision taken; the receiver reports what it saw
])

AUTHORITY_STATUSES = frozenset([
    "ACTIVE",
    "REVOKED",
    "SUPERSEDED",
    "NARROWED",
    "EXPIRED",
    "NO_MANDATE",
    "UNKNOWN",
])

REFUSAL_OUTCOMES = frozenset(["DENY", "QUARANTINE", "STOPPED"])
TERMINAL_AUTHORITY = frozenset(["REVOKED", "SUPERSEDED"])

# Validation levels. These describe the RECEIPT, not the system that made it.
VALID = "VALID"                    # structurally conforms; supports >= 1 claim
CONFORMANT_NO_CLAIMS = "CONFORMANT_NO_CLAIMS"    # structurally conforms; supports 0 claims
INVALID = "INVALID"                # fails a required structural/consistency rule
UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"  # known family, unsupported version
UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"      # claim-check outcome, not a level

# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------

def _parse_ts(value):
    """Parse an ISO-8601 timestamp. Returns datetime or None (never raises)."""
    if not isinstance(value, str) or not value:
        return None
    from datetime import datetime
    text = value.strip()
    # fromisoformat in 3.11+ accepts 'Z'; normalize anyway for safety.
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt


def _get(payload, *path):
    """Walk nested dicts; return None if any hop is missing or not a dict."""
    node = payload
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


# ---------------------------------------------------------------------------
# Claim taxonomy
#
# Each claim lists the exact evidence it requires. The engine returns
# (supported: bool, missing: [str]) where `missing` names the precise
# evidence absent when the claim is not supported. A claim is never
# supported by evidence it does not list here.
# ---------------------------------------------------------------------------

CLAIMS = [
    # --- consequence lifecycle -------------------------------------------
    "ACTION_ATTEMPT_OBSERVED",
    "RECEIVER_DECISION_OBSERVED",
    "EFFECT_OBSERVED",
    "EFFECT_ABSENCE_OBSERVED",
    # --- authority lifecycle ----------------------------------------------
    "CURRENT_AUTHORITY_OBSERVED",
    "REVOCATION_OBSERVED",
    "POST_REVOCATION_ATTEMPT_OBSERVED",
    "REVOCATION_ENFORCEMENT_OBSERVED",
    "SUCCESSOR_AUTHORITY_OBSERVED",
    # --- provenance --------------------------------------------------------
    "PROVENANCE_CHAIN_OBSERVED",
    # --- anomaly ------------------------------------------------------------
    "REPLAY_ATTEMPT_OBSERVED",
    "STALE_ARTIFACT_ATTEMPT_OBSERVED",
    # --- recovery -------------------------------------------------------------
    "RECOVERY_CONTINUATION_OBSERVED",
]

#: Human-readable definition + minimum evidence for each claim (claims.md
#: mirrors this; keep the two in sync).
CLAIM_DEFS = {
    "ACTION_ATTEMPT_OBSERVED": {
        "definition": "The receiver records that a specific action was attempted or proposed.",
        "requires": ["action.type"],
    },
    "RECEIVER_DECISION_OBSERVED": {
        "definition": "The receiver records a decision outcome on the action (not the effect).",
        "requires": ["decision.outcome in vocabulary"],
    },
    "EFFECT_OBSERVED": {
        "definition": "The receiver reports an observed downstream effect (effect.observed=true).",
        "requires": ["effect.observed == true"],
    },
    "EFFECT_ABSENCE_OBSERVED": {
        "definition": ("The receiver asserts no effect occurred (effect.observed=false). "
                       "Receiver-attested: the receipt proves the assertion was made, "
                       "not that absence was independently verified."),
        "requires": ["effect.observed == false"],
    },
    "CURRENT_AUTHORITY_OBSERVED": {
        "definition": "The receipt states the authority standing under which the receiver acted.",
        "requires": ["authority.status in vocabulary"],
    },
    "REVOCATION_OBSERVED": {
        "definition": "The receipt evidences that an authority was revoked (timestamp or status).",
        "requires": ["authority.revoked_at or authority.status == REVOKED"],
    },
    "POST_REVOCATION_ATTEMPT_OBSERVED": {
        "definition": ("An action was attempted after revocation: revocation is evidenced, "
                       "a receiver decision is recorded, and the receipt timestamp is "
                       "at or after the revocation timestamp."),
        "requires": ["REVOCATION_OBSERVED", "decision.outcome",
                     "timestamp >= authority.revoked_at"],
    },
    "REVOCATION_ENFORCEMENT_OBSERVED": {
        "definition": ("Revocation was enforced on a post-revocation attempt: the attempt "
                       "was refused AND the receiver reports no effect. Effect evidence "
                       "is required — a refusal without effect evidence does not prove "
                       "enforcement."),
        "requires": ["POST_REVOCATION_ATTEMPT_OBSERVED",
                     "decision.outcome in {STOPPED, DENY}",
                     "effect.observed == false"],
    },
    "SUCCESSOR_AUTHORITY_OBSERVED": {
        "definition": ("A new active authority is evidenced and explicitly linked to a "
                       "prior authority: either the receipt is a grant event "
                       "(action.type authority_grant/grant_issued) or extensions "
                       "names the superseded authority via successor_of. A bare "
                       "ACTIVE status with parents is not enough — succession must "
                       "be asserted, not inferred."),
        "requires": ["authority.status == ACTIVE", "authority.issued_at",
                     "parents non-empty",
                     "action.type in {authority_grant, grant_issued} "
                     "or extensions.successor_of"],
    },
    "PROVENANCE_CHAIN_OBSERVED": {
        "definition": "The receipt links into a provenance chain: parent receipts plus a named source system.",
        "requires": ["parents non-empty", "provenance.system"],
    },
    "REPLAY_ATTEMPT_OBSERVED": {
        "definition": ("The receiver reports that an action_id already seen was presented "
                       "again and handled as a replay."),
        "requires": ["action.action_id",
                     "decision.outcome in {STOPPED, DENY, QUARANTINE}",
                     "decision.reason indicates replay"],
    },
    "STALE_ARTIFACT_ATTEMPT_OBSERVED": {
        "definition": ("An artifact whose origin authority is no longer current was "
                       "presented and refused. Artifact reference lives in extensions "
                       "so the core stays vendor-neutral."),
        "requires": ["extensions.stale_artifact.artifact_id",
                     "authority.status in {REVOKED, SUPERSEDED}",
                     "decision.outcome in {STOPPED, DENY}"],
    },
    "RECOVERY_CONTINUATION_OBSERVED": {
        "definition": ("A successor authority continued the work: successor authority "
                       "explicitly evidenced (see SUCCESSOR_AUTHORITY_OBSERVED) "
                       "plus a COMMIT decision under it."),
        "requires": ["SUCCESSOR_AUTHORITY_OBSERVED",
                     "decision.outcome == COMMIT"],
    },
}


def _revocation_info(payload):
    """Return (revoked_at_str, revoked: bool)."""
    revoked_at = _get(payload, "authority", "revoked_at")
    status = _get(payload, "authority", "status")
    return revoked_at, bool(revoked_at or status == "REVOKED")


def _decision(payload):
    outcome = _get(payload, "decision", "outcome")
    reason = _get(payload, "decision", "reason") or ""
    return outcome, reason


def _claim_status(name, payload):
    """(supported, missing_list) for one claim. Pure function."""
    outcome, reason = _decision(payload)
    revoked_at, revoked = _revocation_info(payload)
    status = _get(payload, "authority", "status")

    def ok(missing):
        return (not missing), missing

    if name == "ACTION_ATTEMPT_OBSERVED":
        missing = [] if _get(payload, "action", "type") else ["action.type"]
        return ok(missing)
    if name == "RECEIVER_DECISION_OBSERVED":
        missing = [] if outcome in DECISION_OUTCOMES else ["decision.outcome (in vocabulary)"]
        return ok(missing)
    if name == "EFFECT_OBSERVED":
        missing = [] if _get(payload, "effect", "observed") is True else ["effect.observed == true"]
        return ok(missing)
    if name == "EFFECT_ABSENCE_OBSERVED":
        missing = [] if _get(payload, "effect", "observed") is False else ["effect.observed == false"]
        return ok(missing)
    if name == "CURRENT_AUTHORITY_OBSERVED":
        missing = [] if status in AUTHORITY_STATUSES else ["authority.status (in vocabulary)"]
        return ok(missing)
    if name == "REVOCATION_OBSERVED":
        missing = [] if revoked else ["authority.revoked_at or authority.status == REVOKED"]
        return ok(missing)
    if name == "POST_REVOCATION_ATTEMPT_OBSERVED":
        missing = []
        if not revoked:
            missing.append("authority.revoked_at or authority.status == REVOKED")
        if outcome not in DECISION_OUTCOMES:
            missing.append("decision.outcome (in vocabulary)")
        if revoked_at:
            ts, rv = _parse_ts(_get(payload, "timestamp")), _parse_ts(revoked_at)
            if ts is None or rv is None:
                missing.append("parseable timestamp and authority.revoked_at")
            elif ts < rv:
                missing.append("timestamp >= authority.revoked_at (receipt predates revocation)")
        return ok(missing)
    if name == "REVOCATION_ENFORCEMENT_OBSERVED":
        pre_ok, pre_missing = _claim_status("POST_REVOCATION_ATTEMPT_OBSERVED", payload)
        missing = list(pre_missing)
        if outcome not in ("STOPPED", "DENY"):
            missing.append("decision.outcome in {STOPPED, DENY}")
        if _get(payload, "effect", "observed") is not False:
            missing.append("effect.observed == false (refusal alone does not prove no effect)")
        return ok(missing)
    if name == "SUCCESSOR_AUTHORITY_OBSERVED":
        missing = []
        if status != "ACTIVE":
            missing.append("authority.status == ACTIVE")
        if not _get(payload, "authority", "issued_at"):
            missing.append("authority.issued_at")
        parents = payload.get("parents")
        if not (isinstance(parents, list) and parents):
            missing.append("parents (non-empty, linking to prior authority)")
        # Succession must be asserted, not inferred: an ACTIVE authority with
        # parents could be anything; require a grant event or successor_of.
        grant_type = _get(payload, "action", "type") in (
            "authority_grant", "grant_issued")
        if not (grant_type or _get(payload, "extensions", "successor_of")):
            missing.append("action.type in {authority_grant, grant_issued} "
                           "or extensions.successor_of")
        return ok(missing)
    if name == "PROVENANCE_CHAIN_OBSERVED":
        missing = []
        parents = payload.get("parents")
        if not (isinstance(parents, list) and parents):
            missing.append("parents (non-empty)")
        if not _get(payload, "provenance", "system"):
            missing.append("provenance.system")
        return ok(missing)
    if name == "REPLAY_ATTEMPT_OBSERVED":
        missing = []
        if not _get(payload, "action", "action_id"):
            missing.append("action.action_id")
        if outcome not in ("STOPPED", "DENY", "QUARANTINE"):
            missing.append("decision.outcome in {STOPPED, DENY, QUARANTINE}")
        if "REPLAY" not in str(reason).upper():
            missing.append("decision.reason indicating replay")
        return ok(missing)
    if name == "STALE_ARTIFACT_ATTEMPT_OBSERVED":
        missing = []
        if not _get(payload, "extensions", "stale_artifact", "artifact_id"):
            missing.append("extensions.stale_artifact.artifact_id")
        if status not in TERMINAL_AUTHORITY:
            missing.append("authority.status in {REVOKED, SUPERSEDED}")
        if outcome not in ("STOPPED", "DENY"):
            missing.append("decision.outcome in {STOPPED, DENY}")
        return ok(missing)
    if name == "RECOVERY_CONTINUATION_OBSERVED":
        succ_ok, succ_missing = _claim_status("SUCCESSOR_AUTHORITY_OBSERVED", payload)
        missing = list(succ_missing)
        if outcome != "COMMIT":
            missing.append("decision.outcome == COMMIT")
        return ok(missing)
    return False, ["unknown claim: %s" % name]


def evaluate_claims(payload):
    """Evaluate every claim. Returns {claim: {"supported": bool, "missing": [...]}}."""
    return {name: {"supported": sup, "missing": miss}
            for name in CLAIMS
            for sup, miss in [_claim_status(name, payload)]}


def supported_claims(payload):
    """Names of claims the payload supports, in CLAIMS order."""
    return [n for n in CLAIMS if _claim_status(n, payload)[0]]


# ---------------------------------------------------------------------------
# Structural validation
# ---------------------------------------------------------------------------

def validate(payload):
    """Validate one parsed payload.

    Returns dict with:
      status   — VALID / CONFORMANT_NO_CLAIMS / INVALID / UNSUPPORTED_VERSION
      problems — list of strings (structural/consistency failures)
      warnings — list of strings (advisories, never invalidate)
      supported_claims / not_established — claim evaluation
      unknown_fields — top-level fields outside the core schema (preserved)
    """
    result = {
        "status": INVALID, "problems": [], "warnings": [],
        "supported_claims": [], "not_established": [],
        "unknown_fields": [],
        "receipt_version": None, "receipt_id": None,
        "signature_present": False, "hash_present": False,
    }
    problems, warnings = result["problems"], result["warnings"]

    if not isinstance(payload, dict):
        problems.append("receipt must be a JSON object")
        return result

    version = payload.get("receipt_version")
    result["receipt_version"] = version
    result["receipt_id"] = payload.get("receipt_id")

    # Version gate: a version that speaks the family prefix but is not the
    # supported one is UNSUPPORTED_VERSION, not INVALID.
    if version is not None:
        if not isinstance(version, str) or not version.startswith(RECEIPT_FAMILY_PREFIX):
            problems.append("receipt_version must start with %r" % RECEIPT_FAMILY_PREFIX)
        elif version != RECEIPT_VERSION:
            result["status"] = UNSUPPORTED_VERSION
            problems.append("unsupported receipt version %r (supported: %s)"
                            % (version, RECEIPT_VERSION))
            return result
    # No version at all: only a problem if nothing else identifies the receipt.
    if version is None and not payload.get("receipt_id"):
        problems.append("missing required field: receipt_version "
                        "(and no receipt_id to identify the receipt)")

    # Required fields.
    for field in REQUIRED_FIELDS:
        value = payload.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            problems.append("missing required field: %s" % field)
    if result["receipt_id"] is not None and not isinstance(result["receipt_id"], str):
        problems.append("receipt_id must be a string")

    # Timestamp must parse.
    if payload.get("timestamp") is not None and _parse_ts(payload.get("timestamp")) is None:
        problems.append("timestamp is not parseable ISO-8601: %r" % payload.get("timestamp"))

    # Controlled vocabularies: a present-but-unknown value is structural.
    outcome, _reason = _decision(payload)
    if payload.get("decision") is not None and outcome not in DECISION_OUTCOMES:
        problems.append("decision.outcome not in vocabulary: %r (allowed: %s)"
                        % (outcome, sorted(DECISION_OUTCOMES)))
    status = _get(payload, "authority", "status")
    if payload.get("authority") is not None and status is not None \
            and status not in AUTHORITY_STATUSES:
        problems.append("authority.status not in vocabulary: %r (allowed: %s)"
                        % (status, sorted(AUTHORITY_STATUSES)))
    effect_observed = _get(payload, "effect", "observed")
    if payload.get("effect") is not None and effect_observed not in (True, False, None):
        problems.append("effect.observed must be true, false, or null")

    # parents must be a list of strings when present.
    parents = payload.get("parents")
    if parents is not None and (not isinstance(parents, list)
                                or any(not isinstance(x, str) for x in parents)):
        problems.append("parents must be a list of receipt-id strings")

    # extensions must be an object when present (vendor-neutral namespace).
    extensions = payload.get("extensions")
    if extensions is not None and not isinstance(extensions, dict):
        problems.append("extensions must be a JSON object")

    # Internal consistency: temporal contradictions invalidate.
    issued_at = _get(payload, "authority", "issued_at")
    revoked_at = _get(payload, "authority", "revoked_at")
    if issued_at and revoked_at:
        i, r = _parse_ts(issued_at), _parse_ts(revoked_at)
        if i is not None and r is not None and r < i:
            problems.append("internally inconsistent: authority.revoked_at "
                            "precedes authority.issued_at")
    ts = _parse_ts(payload.get("timestamp"))
    if ts is not None and issued_at:
        i = _parse_ts(issued_at)
        if i is not None and status == "ACTIVE" and ts < i:
            problems.append("internally inconsistent: receipt timestamp precedes "
                            "authority.issued_at while authority.status is ACTIVE")
    effect_at = _get(payload, "effect", "observed_at")
    if effect_at:
        e = _parse_ts(effect_at)
        if e is None:
            warnings.append("effect.observed_at is not parseable ISO-8601")
        elif ts is not None and e < ts:
            warnings.append("effect.observed_at precedes the receipt timestamp")

    # --- authenticity separation -------------------------------------------
    provenance = payload.get("provenance") or {}
    result["signature_present"] = bool(provenance.get("signature"))
    result["hash_present"] = bool(provenance.get("hash"))
    if not provenance:
        warnings.append("no provenance section: source system is self-asserted "
                        "only by the 'receiver' field")
    elif not provenance.get("system"):
        warnings.append("provenance.system missing: source system unattested")
    if not result["signature_present"]:
        warnings.append("no signature: structural conformance only — "
                        "this receipt is NOT cryptographically authenticated")
    if not result["hash_present"]:
        warnings.append("no hash binding: payload integrity is not bound to an identifier")

    # Epistemic warnings: things the receipt does NOT prove.
    if outcome in DECISION_OUTCOMES and effect_observed is None:
        warnings.append("decision recorded without effect evidence: "
                        "the outcome of the consequence is unknown, not assumed")
    if _revocation_info(payload)[1] and outcome in ("STOPPED", "DENY") \
            and effect_observed is not False:
        warnings.append("revocation timestamp is receiver-external and unsigned; "
                        "propagation is not proven by the revocation record alone")

    # Unknown top-level fields are preserved, never rejected.
    known = {"receipt_version", "receipt_id", "timestamp", "receiver",
             "principal", "actor", "action", "authority", "decision",
             "effect", "parents", "provenance", "extensions"}
    result["unknown_fields"] = sorted(k for k in payload if k not in known)
    if result["unknown_fields"]:
        warnings.append("unknown top-level fields preserved (not validated): %s"
                        % ", ".join(result["unknown_fields"]))

    if problems:
        result["status"] = INVALID
        return result

    claims = evaluate_claims(payload)
    result["supported_claims"] = [n for n in CLAIMS if claims[n]["supported"]]
    result["not_established"] = [n for n in CLAIMS if not claims[n]["supported"]]
    result["status"] = VALID if result["supported_claims"] else CONFORMANT_NO_CLAIMS
    return result


def check_claim(payload, claim):
    """Explicit claim query. Returns (verdict, missing_list).

    verdict is "SUPPORTED", "NOT_SUPPORTED", or "INVALID" (receipt-level
    structural failure). UNSUPPORTED_CLAIM is reported when the receipt is
    fine but the claim is not supported; callers map that to the taxonomy.
    """
    if claim not in CLAIMS:
        return "UNSUPPORTED_CLAIM", ["unknown claim name: %s (known: %s)"
                                    % (claim, ", ".join(CLAIMS))]
    result = validate(payload)
    if result["status"] in (INVALID, UNSUPPORTED_VERSION):
        return "INVALID", result["problems"]
    supported, missing = _claim_status(claim, payload)
    if supported:
        return "SUPPORTED", []
    return "UNSUPPORTED_CLAIM", missing


# ---------------------------------------------------------------------------
# Conformance report over a file or directory (read-only)
# ---------------------------------------------------------------------------

def _iter_json_files(path):
    if os.path.isdir(path):
        for root, _dirs, files in os.walk(path):
            for fn in sorted(files):
                if fn.endswith(".json"):
                    yield os.path.join(root, fn)
    else:
        yield path


def _file_signature(path):
    """(mtime_ns, size) snapshot used to prove sources were not modified."""
    st = os.stat(path)
    return (st.st_mtime_ns, st.st_size)


def conformance_report(path):
    """Validate a file or directory. Returns a JSON-serializable report dict.

    Sources are opened read-only; the report includes a read-only
    verification (mtime/size snapshots before and after the scan).
    """
    files = list(_iter_json_files(path))
    before = {f: _file_signature(f) for f in files if os.path.isfile(f)}

    per_file = []
    claim_counts = {c: 0 for c in CLAIMS}
    unreadable = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            unreadable.append({"file": f,
                               "error": "%s: %s" % (type(e).__name__, e)})
            per_file.append({"file": f, "status": "UNREADABLE",
                             "receipt_id": None, "supported_claims": []})
            continue
        r = validate(payload)
        for c in r["supported_claims"]:
            claim_counts[c] += 1
        per_file.append({
            "file": f, "status": r["status"], "receipt_id": r["receipt_id"],
            "problems": r["problems"], "warnings": r["warnings"],
            "supported_claims": r["supported_claims"],
            "not_established": r["not_established"],
            "signature_present": r["signature_present"],
            "hash_present": r["hash_present"],
        })

    after = {f: _file_signature(f) for f in files if os.path.isfile(f)}
    modified = sorted(f for f in before if before.get(f) != after.get(f))

    counts = {"VALID": 0, "CONFORMANT_NO_CLAIMS": 0, "INVALID": 0,
              "UNSUPPORTED_VERSION": 0, "UNREADABLE": 0}
    for pf in per_file:
        counts[pf["status"]] = counts.get(pf["status"], 0) + 1

    # Claims with zero supporting receipts are not measurable from this corpus.
    not_measurable = [
        {"claim": c, "reason": "no receipt in this corpus supports it"}
        for c in CLAIMS if claim_counts[c] == 0
    ]
    # Standing hard limits: these need evidence no single receipt corpus
    # can provide on its own.
    not_measurable.append({
        "claim": "revocation propagation lag (metric)",
        "reason": "needs paired revocation->enforcement timestamps from the "
                  "same receiver lineage; a single receipt cannot measure lag",
    })
    not_measurable.append({
        "claim": "false hold rate (metric)",
        "reason": "needs independent legitimacy ground truth; receipts record "
                  "decisions, not whether the decision was correct",
    })

    return {
        "path": os.path.abspath(path),
        "files_scanned": len(files),
        "counts": counts,
        "claims_evidenced": {c: n for c, n in claim_counts.items() if n > 0},
        "claims_not_measurable": not_measurable,
        "per_file": per_file,
        "unreadable": unreadable,
        "source_files_modified": len(modified),
        "modified_files": modified,
    }


def main(argv=None):
    """CLI: python3 -m bureau.conformance <path> [--json]"""
    import argparse
    ap = argparse.ArgumentParser(
        description="Validate external receipts (bureau.receipt.v0.1) "
                    "in a file or directory. Read-only.")
    ap.add_argument("path", help="JSON receipt file or directory of receipts")
    ap.add_argument("--json", action="store_true",
                    help="machine-readable JSON report")
    args = ap.parse_args(argv)

    report = conformance_report(args.path)
    if args.json:
        print(json.dumps(report, indent=1, sort_keys=True))
        return 0

    c = report["counts"]
    print("BUREAU CONFORMANCE REPORT")
    print()
    print("  path:                      %s" % report["path"])
    print("  files scanned:             %d" % report["files_scanned"])
    print("  valid:                     %d" % c["VALID"])
    print("  conformant, no claims:      %d" % c["CONFORMANT_NO_CLAIMS"])
    print("  invalid:                   %d" % c["INVALID"])
    print("  unsupported version:       %d" % c["UNSUPPORTED_VERSION"])
    print("  unreadable:                %d" % c["UNREADABLE"])
    print()
    print("CLAIMS EVIDENCED")
    if report["claims_evidenced"]:
        for claim, n in sorted(report["claims_evidenced"].items()):
            print("  %-38s %d receipt(s)" % (claim, n))
    else:
        print("  none")
    print()
    print("CLAIMS NOT MEASURABLE")
    for item in report["claims_not_measurable"]:
        print("  - %s: %s" % (item["claim"], item["reason"]))
    print()
    print("PER FILE")
    for pf in report["per_file"]:
        rid = pf["receipt_id"] or "(no id)"
        print("  [%s] %s  %s" % (pf["status"], rid,
                                 os.path.basename(pf["file"])))
        for p in pf.get("problems", []):
            print("      problem: %s" % p)
    print()
    print("  source files modified: %d" % report["source_files_modified"])
    return 0 if not report["modified_files"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
