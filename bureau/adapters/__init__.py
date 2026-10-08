#!/usr/bin/env python3
"""OpenLine Bureau — source adapters.

Each adapter: detect(payload) -> bool, adapt(payload, provenance) -> [record].
Adapters never mutate sources. Unmapped source fields land in `unmapped`.
Unsupported payloads raise UnsupportedReceiptFormat (fail visible).
"""

import hashlib
import json

from ..conformance import RECEIPT_VERSION, validate as conformance_validate
from ..schema import make_record


class UnsupportedReceiptFormat(Exception):
    pass


def _rid(*parts):
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:24]
    return h


# ---------------------------------------------------------------------------
# openline.wallet.effect_receipt.v1  (consequence actually attempted/observed)
# ---------------------------------------------------------------------------
def detect_wallet_effect_receipt(p):
    return isinstance(p, dict) and str(p.get("schema", "")).startswith(
        "openline.wallet.effect_receipt")


def adapt_wallet_effect_receipt(p, prov):
    reasons = p.get("reason_codes") or []
    reason = ",".join(reasons) if reasons else None
    decision = p.get("decision")
    # A STOPPED/DENIED effect on revoked authority is a stale-authority attempt
    # that the boundary refused; an ALLOWED/COMMIT on revoked authority would
    # be a containment failure (recorded as observed, not inferred).
    revoked = any("REVOKED" in r for r in reasons)
    if decision in ("STOPPED", "DENIED", "DENY"):
        event_type = ("stale_authority_attempt" if revoked
                      else "action_refused")
        authority_state = "MANDATE_REVOKED" if revoked else None
    elif decision in ("COMMITTED", "COMMIT", "ALLOWED"):
        event_type = "action_committed"
        authority_state = "MANDATE_REVOKED" if revoked else "MANDATE_ACTIVE"
    else:
        event_type = None
        authority_state = "MANDATE_REVOKED" if revoked else None
    rid = p.get("effect_id") or _rid("wallet-effect",
                                     p.get("payload_hash"), p.get("completed_at"))
    parents = [h for h in (p.get("admission_receipt_hash"),
                           p.get("frontier_receipt_hash")) if h]
    unmapped = {k: v for k, v in p.items() if k not in {
        "schema", "action", "completed_at", "decision", "effect_applied",
        "effect_id", "mandate_id", "principal_id", "subject_id",
        "reason_codes", "admission_receipt_hash", "frontier_receipt_hash",
        "gate_id"}}
    rec = make_record(
        receipt_id="weff-" + rid,
        timestamp=p.get("completed_at"),
        system="openline-wallet",
        principal=p.get("principal_id"),
        actor=p.get("subject_id"),
        action=p.get("action"),
        target=p.get("gate_id"),
        authority_state=authority_state,
        decision={"STOPPED": "STOPPED", "DENIED": "DENY", "DENY": "DENY",
                  "COMMITTED": "COMMIT", "COMMIT": "COMMIT",
                  "ALLOWED": "ALLOWED"}.get(decision),
        event_type=event_type,
        reason=reason,
        effect_observed=p.get("effect_applied"),
        standing="REVOKED" if revoked else None,
        parent_receipts=["admission-" + h[:24] for h in parents],
        adapter="wallet_effect_receipt",
        raw=p, unmapped=unmapped, **prov)
    return [rec]


# ---------------------------------------------------------------------------
# openline.gate.action_receipt.v1  (receiver decision before consequence)
# ---------------------------------------------------------------------------
def detect_gate_action_receipt(p):
    return isinstance(p, dict) and str(p.get("schema", "")).startswith(
        "openline.gate.action_receipt")


def adapt_gate_action_receipt(p, prov):
    reasons = p.get("reason_codes") or []
    reason = ",".join(reasons) if reasons else None
    decision = p.get("decision")
    revoked = any("REVOKED" in r for r in reasons)
    if decision == "ALLOWED":
        event_type = "action_proposed"
        dec = "ALLOWED"
    elif decision in ("STOPPED", "DENIED", "DENY"):
        event_type = ("stale_authority_attempt" if revoked
                      else "action_refused")
        dec = "STOPPED" if decision == "STOPPED" else "DENY"
    else:
        event_type, dec = None, None
    rid = _rid("gate-action", p.get("payload_hash"),
               p.get("presentation_hash"), p.get("decided_at"))
    unmapped = {k: v for k, v in p.items() if k not in {
        "schema", "action", "decided_at", "decision", "decision_authority",
        "gate_id", "mandate_id", "principal_id", "subject_id",
        "reason_codes", "payload_hash", "presentation_hash"}}
    rec = make_record(
        receipt_id="gact-" + rid,
        timestamp=p.get("decided_at"),
        system="openline-receipt-gate",
        principal=p.get("principal_id"),
        actor=p.get("subject_id"),
        action=p.get("action"),
        target=p.get("gate_id"),
        authority_state="MANDATE_REVOKED" if revoked else "MANDATE_ACTIVE",
        decision=dec,
        event_type=event_type,
        reason=reason,
        effect_observed=None,  # gate decides before consequence; effect separate
        standing="REVOKED" if revoked else None,
        parent_receipts=[],
        adapter="gate_action_receipt",
        raw=p, unmapped=unmapped, **prov)
    return [rec]


# ---------------------------------------------------------------------------
# wallet closure-set trace events  (authority lifecycle over time)
# ---------------------------------------------------------------------------
_TRACE_EVENT_MAP = {
    "grant_admitted": ("mandate_issued", "MANDATE_ACTIVE", None),
    "grant_reissued": ("mandate_issued", "MANDATE_ACTIVE", None),
    "mandate_narrowed": ("mandate_narrowed", "MANDATE_NARROWED", None),
    "revocation_signed": ("mandate_revoked", "MANDATE_REVOKED", "REVOKED"),
    "revocation_admitted": ("mandate_revoked", "MANDATE_REVOKED", "REVOKED"),
    "two_receivers_admitted_revocation": ("revocation_propagated",
                                          "MANDATE_REVOKED", "REVOKED"),
    "set_closure_verified": ("revocation_propagated",
                             "MANDATE_REVOKED", "REVOKED"),
    "third_receiver_closed": ("revocation_propagated",
                              "MANDATE_REVOKED", "REVOKED"),
    "prior_effect_committed": ("action_committed", "MANDATE_ACTIVE", None),
    "inflight_effect_completed_before_closure": ("effect_observed",
                                                 "MANDATE_REVOKED", None),
    "inflight_effect_held_at_ledger": ("action_quarantined",
                                       "MANDATE_REVOKED", None),
}


def detect_wallet_trace(p):
    return (isinstance(p, list) and p
            and all(isinstance(e, dict) and "event" in e for e in p))


def adapt_wallet_trace(p, prov):
    recs = []
    for i, e in enumerate(p):
        name = e.get("event")
        mapped = _TRACE_EVENT_MAP.get(name)
        event_type, authority_state, standing = mapped if mapped else (None, None, None)
        rid = _rid("wtrace", prov.get("source_path"), name,
                   e.get("observed_at"), e.get("sequence", i))
        unmapped = {k: v for k, v in e.items()
                    if k not in {"event", "observed_at", "sequence"}}
        recs.append(make_record(
            receipt_id="wtrc-" + rid,
            timestamp=e.get("observed_at"),
            system="openline-wallet",
            principal=None,
            actor=e.get("gate_id"),
            action=name,
            target=None,
            authority_state=authority_state,
            decision=None,
            event_type=event_type,
            reason=e.get("closure_status"),
            effect_observed=True if name in (
                "prior_effect_committed",
                "inflight_effect_completed_before_closure") else None,
            standing=standing,
            parent_receipts=[],
            adapter="wallet_trace",
            raw=e, unmapped=unmapped, **prov))
    return recs


# ---------------------------------------------------------------------------
# openline.bureau.experiment_record.v1  (frozen experiment evidence, curated)
#
# Lets frozen experiment outcomes (sentry decisions, containment verdicts,
# incident replays, handoffs) enter the Bureau as first-class evidence
# without reinterpreting the frozen record. Curated by hand from RESULT.md /
# TERMINAL files; the evidence_ref field points back at the frozen source.
# ---------------------------------------------------------------------------
def detect_experiment_record(p):
    return isinstance(p, dict) and p.get("format") == \
        "openline.bureau.experiment_record.v1"


def adapt_experiment_record(p, prov):
    recs = []
    exp = p.get("experiment")
    system = p.get("system")
    for c in p.get("cases", []):
        cid = c.get("case_id", "case")
        base = dict(
            system=system, experiment=exp,
            principal=c.get("principal"), actor=c.get("actor"),
            adapter="experiment_record", raw=c,
            unmapped={"evidence_ref": c.get("evidence_ref"),
                      "terminal": p.get("terminal")},
            **prov)
        # semantic judgment, if recorded
        if c.get("semantic_decision"):
            sem = c["semantic_decision"]
            recs.append(make_record(
                receipt_id="exp-%s-%s-sem" % (exp, cid),
                timestamp=None,
                action="step-%s" % c.get("semantic_warning_step"),
                decision={"CHALLENGE": "CHALLENGE", "HOLD": "HOLD"}.get(sem),
                event_type={"CHALLENGE": "semantic_challenge",
                            "HOLD": "semantic_hold"}.get(sem),
                reason=c.get("semantic_reason"),
                effect_observed=None,
                **base))
        # deterministic intervention, if recorded
        if c.get("deterministic_decision"):
            det = c["deterministic_decision"]
            recs.append(make_record(
                receipt_id="exp-%s-%s-det" % (exp, cid),
                timestamp=None,
                action="step-%s" % c.get("deterministic_step"),
                decision={"DENY": "DENY", "QUARANTINE": "QUARANTINE",
                          "STOPPED": "STOPPED", "COMMIT": "COMMIT"}.get(det),
                event_type={"DENY": "action_refused",
                            "QUARANTINE": "action_quarantined",
                            "STOPPED": "action_stopped",
                            "COMMIT": "action_committed"}.get(det),
                reason=c.get("deterministic_reason"),
                effect_observed=(det == "COMMIT"),
                **base))
        # quality annotations (observed, not inferred)
        if c.get("false_hold"):
            recs.append(make_record(
                receipt_id="exp-%s-%s-fh" % (exp, cid),
                event_type="false_hold",
                reason="legitimate trajectory stopped; see evidence_ref",
                **base))
        if c.get("apparatus_incomplete"):
            recs.append(make_record(
                receipt_id="exp-%s-%s-ai" % (exp, cid),
                event_type="apparatus_incomplete",
                reason=c.get("apparatus_note"),
                **base))
        if c.get("warning_corresponded_to_real_problem") is False and \
                c.get("semantic_decision"):
            # warning raised on a trajectory that stayed legitimate:
            # recorded as observed outcome, distinct from false_hold
            # (false_hold requires the trajectory to have been stopped)
            pass
    return recs


# ---------------------------------------------------------------------------
# openline.bureau.canonical.v1  (pre-normalized dump, e.g. synthetic demo)
#
# {"format": "openline.bureau.canonical.v1", "records": [<canonical>]}
# Records are validated at insert; provenance falls back to the ingest call.
# ---------------------------------------------------------------------------
def detect_canonical_dump(p):
    return isinstance(p, dict) and p.get("format") == \
        "openline.bureau.canonical.v1"


def adapt_canonical_dump(p, prov):
    recs = []
    for r in p.get("records", []):
        r = dict(r)
        for k in ("source_repo", "source_path", "adapter"):
            if not r.get(k):
                r[k] = prov.get(k) or ("synthetic-demo" if k == "source_repo"
                                      else "canonical_dump")
        if not r.get("raw_ref"):
            r["raw_ref"] = prov.get("raw_ref")
        recs.append(r)
    return recs


# ---------------------------------------------------------------------------
# bureau.receipt.v0.1  (external receiver — does NOT run OpenLine)
#
# Minimal consequence receipts from an independent receiver, validated by
# bureau/conformance.py. Only structurally valid receipts normalize;
# INVALID ones raise UnsupportedReceiptFormat with the exact problems.
# External receipt ids and parent links are preserved verbatim so ancestry
# survives the round trip; nothing is re-keyed into an OpenLine namespace.
# ---------------------------------------------------------------------------

_EXTERNAL_AUTHORITY_MAP = {
    "ACTIVE": "MANDATE_ACTIVE",
    "REVOKED": "MANDATE_REVOKED",
    "SUPERSEDED": "MANDATE_SUPERSEDED",
    "NARROWED": "MANDATE_NARROWED",
    "EXPIRED": "MANDATE_EXPIRED",
    "NO_MANDATE": "NO_MANDATE",
    "UNKNOWN": "UNKNOWN",
}

_EXTERNAL_DECISION_MAP = {
    "COMMIT": "COMMIT",
    "DENY": "DENY",
    "QUARANTINE": "QUARANTINE",
    "STOPPED": "STOPPED",
    "OBSERVED": None,  # report only; no decision to normalize
}


def detect_external_receipt(p):
    return isinstance(p, dict) and p.get("receipt_version") == RECEIPT_VERSION


def adapt_external_receipt(p, prov):
    result = conformance_validate(p)
    if result["status"] in ("INVALID", "UNSUPPORTED_VERSION"):
        raise UnsupportedReceiptFormat(
            "external receipt failed conformance: %s"
            % "; ".join(result["problems"]))
    action = p.get("action") or {}
    authority = p.get("authority") or {}
    decision = p.get("decision") or {}
    effect = p.get("effect") or {}
    provenance = p.get("provenance") or {}
    extensions = p.get("extensions") or {}

    status = authority.get("status")
    outcome = decision.get("outcome")
    dec = _EXTERNAL_DECISION_MAP.get(outcome)
    action_label = " ".join(x for x in (action.get("type"),
                                        action.get("target")) if x) or None

    # Event-type inference from inspectable propositions only.
    reason = decision.get("reason") or ""
    event_type = None
    if outcome in ("STOPPED", "DENY", "QUARANTINE") \
            and status in ("REVOKED", "SUPERSEDED"):
        event_type = "stale_authority_attempt"
    elif outcome == "COMMIT" and status == "ACTIVE" and p.get("parents") \
            and (action.get("type") in ("authority_grant", "grant_issued")
                 or extensions.get("successor_of")):
        event_type = "successor_continuation"
    elif outcome == "COMMIT":
        event_type = "action_committed"
    elif outcome == "DENY":
        event_type = "action_refused"
    elif outcome == "QUARANTINE":
        event_type = "action_quarantined"
    elif outcome == "STOPPED":
        event_type = "action_stopped"
    elif outcome == "OBSERVED" and effect.get("observed") is True:
        event_type = "effect_observed"
    elif status == "REVOKED" and outcome is None \
            and action.get("type") in ("authority_revoke", None):
        event_type = "mandate_revoked"
    elif action.get("type") in ("authority_grant", "grant_issued") \
            and status == "ACTIVE":
        event_type = "mandate_issued"

    unmapped = {
        "receiver": p.get("receiver"),
        "authority": authority,
        "provenance_detail": provenance,
        "effect_detail": effect,
        "action_id": action.get("action_id"),
        "extensions": extensions,
    }
    rec = make_record(
        receipt_id=p.get("receipt_id"),  # preserved verbatim; not re-keyed
        timestamp=p.get("timestamp"),
        system="external:" + (provenance.get("system") or p.get("receiver")
                              or "unknown-receiver"),
        principal=p.get("principal"),
        actor=p.get("actor"),
        action=action_label,
        target=action.get("target"),
        authority_state=_EXTERNAL_AUTHORITY_MAP.get(status),
        decision=dec,
        event_type=event_type,
        reason=reason or None,
        effect_observed=effect.get("observed"),
        standing="REVOKED" if status == "REVOKED" else None,
        parent_receipts=list(p.get("parents") or []),
        adapter="external_receipt",
        raw=p, unmapped=unmapped, **prov)
    return [rec]


ADAPTERS = [
    ("wallet_effect_receipt", detect_wallet_effect_receipt,
     adapt_wallet_effect_receipt),
    ("gate_action_receipt", detect_gate_action_receipt,
     adapt_gate_action_receipt),
    ("wallet_trace", detect_wallet_trace, adapt_wallet_trace),
    ("experiment_record", detect_experiment_record, adapt_experiment_record),
    ("canonical_dump", detect_canonical_dump, adapt_canonical_dump),
    ("external_receipt", detect_external_receipt, adapt_external_receipt),
]

from . import exchange
ADAPTERS.insert(0, ("exchange", exchange.detect, exchange.adapt))


def detect(payload):
    for name, det, _ in ADAPTERS:
        try:
            if det(payload):
                return name
        except Exception:
            continue
    return None


def adapt(payload, provenance):
    """Adapt one payload (dict/list). Raises UnsupportedReceiptFormat."""
    name = detect(payload)
    if name is None:
        raise UnsupportedReceiptFormat(
            "no adapter recognized this payload shape")
    for aname, _, fn in ADAPTERS:
        if aname == name:
            return fn(payload, provenance)
    raise UnsupportedReceiptFormat("adapter vanished: " + name)  # pragma: no cover
