#!/usr/bin/env python3
"""OpenLine Bureau — canonical normalized receipt schema.

Evidence first: every normalized record preserves provenance back to its
source. Missing means unknown. Never fabricate.
"""

import json

# ---------------------------------------------------------------------------
# Controlled vocabularies. Adapters map source-specific values into these.
# Values outside these vocabularies are preserved verbatim in `raw` and in
# the `unmapped_*` fields, never silently coerced.
# ---------------------------------------------------------------------------

DECISIONS = frozenset([
    "COMMIT",        # protected consequence allowed and (attempted) effect
    "ALLOWED",       # action permitted by a receiver (effect may be separate)
    "QUARANTINE",    # held for review; consequence did not proceed
    "DENY",          # refused by policy/gate
    "STOPPED",      # halted: outside mandate, revoked authority, etc.
    "CHALLENGE",    # semantic concern raised; consequence not yet decided
    "HOLD",         # consequential hold (distinct from epistemic CHALLENGE)
])

AUTHORITY_STATES = frozenset([
    "MANDATE_ACTIVE",
    "MANDATE_REVOKED",
    "MANDATE_SUPERSEDED",
    "MANDATE_NARROWED",
    "MANDATE_EXPIRED",
    "NO_MANDATE",
    "UNKNOWN",
])

STANDINGS = frozenset([
    "CURRENT",      # record is the latest known standing for its subject
    "SUPERSEDED",   # a newer record replaced this one
    "REVOKED",      # authority withdrawn
    "EXPIRED",      # lapsed by time bound
    "UNRESOLVED",   # standing could not be established from evidence
    "UNKNOWN",
])

EVENT_TYPES = frozenset([
    # consequence lifecycle
    "action_proposed",
    "action_committed",
    "action_refused",        # DENY / effect refused
    "action_quarantined",
    "action_stopped",
    "effect_observed",
    # authority lifecycle
    "mandate_issued",
    "mandate_narrowed",
    "mandate_revoked",
    "mandate_superseded",
    "mandate_expired",
    # violations / anomalies
    "stale_authority_attempt",  # protected action attempted on non-current authority
    "replay_attempt",
    "invalid_ancestry",
    "authority_laundering_attempt",
    # continuity
    "provider_replacement",
    "successor_continuation",   # successor continued from accepted checkpoint
    "continuity_failure",
    # recovery
    "recovery_proposed",
    "recovery_succeeded",
    "recovery_failed",
    # semantic layer
    "semantic_challenge",       # CHALLENGE raised (epistemic)
    "semantic_hold",            # HOLD imposed (consequential)
    "false_hold",               # legitimate action stopped by challenge machinery
    "challenge_reconciled",
    "challenge_unresolved",
    # standing / evidence
    "delayed_standing_failure", # artifact rejected: origin standing changed
    "unresolved_standing",
    "revocation_propagated",    # enforcement confirmed after revocation
    "propagation_lag_measured",
    # apparatus
    "apparatus_incomplete",     # evidence needed for a judgment was missing
])

# Canonical fields. Only receipt_id and provenance are required;
# everything else may be None (= unknown).
CANONICAL_FIELDS = (
    "receipt_id",
    "timestamp",          # ISO-8601 string or None
    "system",             # e.g. "openline-wallet", "receipt-gate"
    "experiment",         # e.g. "APPROVED_JOB_LIVE_001" or None
    "principal",          # the owner on whose behalf authority exists
    "actor",              # the worker/agent that acted
    "action",             # normalized action label
    "target",             # normalized target label
    "authority_state",    # AUTHORITY_STATES or None
    "decision",           # DECISIONS or None
    "event_type",         # EVENT_TYPES or None
    "reason",             # machine or human reason string or None
    "effect_observed",    # True/False/None (None = unknown)
    "standing",           # STANDINGS or None
    "parent_receipts",    # list of receipt_id strings
    # provenance (required)
    "source_repo",
    "source_commit",
    "source_path",
    "raw_ref",            # pointer to raw payload location
    "adapter",            # adapter name that produced this record
    "ingested_at",        # ISO-8601 ingestion time
    # fidelity
    "raw",                # original payload (dict) where permissible
    "unmapped",           # source fields that had no canonical mapping (dict)
)


def make_record(receipt_id, source_repo, source_path, adapter,
                source_commit=None, raw_ref=None, raw=None, **fields):
    """Build a canonical record. Unknown fields raise TypeError (fail loud)."""
    unknown = set(fields) - set(CANONICAL_FIELDS)
    if unknown:
        raise TypeError("unknown canonical fields: %s" % sorted(unknown))
    rec = {f: None for f in CANONICAL_FIELDS}
    rec.update(fields)
    rec["receipt_id"] = receipt_id
    rec["source_repo"] = source_repo
    rec["source_commit"] = source_commit
    rec["source_path"] = source_path
    rec["raw_ref"] = raw_ref
    rec["adapter"] = adapter
    rec["raw"] = raw
    if rec["parent_receipts"] is None:
        rec["parent_receipts"] = []
    return rec


def validate(rec):
    """Return a list of problems (empty = valid). Never raises."""
    problems = []
    if not rec.get("receipt_id"):
        problems.append("missing receipt_id")
    for prov in ("source_repo", "source_path", "adapter"):
        if not rec.get(prov):
            problems.append("missing provenance: %s" % prov)
    if rec.get("decision") is not None and rec["decision"] not in DECISIONS:
        problems.append("decision not in vocabulary: %r" % rec["decision"])
    if rec.get("authority_state") is not None and rec["authority_state"] not in AUTHORITY_STATES:
        problems.append("authority_state not in vocabulary: %r" % rec["authority_state"])
    if rec.get("standing") is not None and rec["standing"] not in STANDINGS:
        problems.append("standing not in vocabulary: %r" % rec["standing"])
    if rec.get("event_type") is not None and rec["event_type"] not in EVENT_TYPES:
        problems.append("event_type not in vocabulary: %r" % rec["event_type"])
    if rec.get("effect_observed") not in (True, False, None):
        problems.append("effect_observed must be true/false/null")
    pr = rec.get("parent_receipts")
    if not isinstance(pr, list) or any(not isinstance(x, str) for x in pr):
        problems.append("parent_receipts must be a list of strings")
    return problems


def to_json(rec):
    return json.dumps(rec, indent=1, sort_keys=True, default=str)
