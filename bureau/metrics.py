#!/usr/bin/env python3
"""OpenLine Bureau — disciplined metrics.

Every metric returns:
    {
      "name": ...,
      "definition": ...,
      "value": <number or None>,
      "numerator": <int or None>, "numerator_desc": ...,
      "denominator": <int or None>, "denominator_desc": ...,
      "measurable": True/False,
      "reason_not_measurable": ... or None,
      "source_event_count": <int>,
      "window": {"since": ..., "until": ...} or None,
    }

A metric is NOT MEASURABLE when its denominator cannot be established from
evidence. It is never inferred.
"""

from .store import Store


def _m(name, definition, value, num, num_desc, den, den_desc,
        source_event_count, window=None, not_measurable_reason=None):
    return {
        "name": name,
        "definition": definition,
        "value": value,
        "numerator": num,
        "numerator_desc": num_desc,
        "denominator": den,
        "denominator_desc": den_desc,
        "measurable": not_measurable_reason is None,
        "reason_not_measurable": not_measurable_reason,
        "source_event_count": source_event_count,
        "window": window,
    }


def _count(store, **filters):
    return len(store.ledger(limit=1000000, **filters))


def compute_all(store, since=None, until=None):
    window = {"since": since, "until": until} \
        if (since or until) else None
    kw = {"since": since, "until": until}
    out = {}

    def cnt(**f):
        return _count(store, **dict(kw, **f))

    # -- volume ------------------------------------------------------------
    out["receipts_observed"] = _m(
        "receipts_observed",
        "Normalized receipts present in the Bureau store.",
        cnt(), cnt(), "receipts in store", None, None, cnt(), window)

    # -- consequence lifecycle ----------------------------------------------
    attempted = cnt(event_type="action_proposed")
    committed = cnt(decision="COMMIT") + cnt(event_type="action_committed")
    refused = (cnt(decision="DENY") + cnt(decision="STOPPED")
               + cnt(event_type="action_refused"))
    quarantined = cnt(decision="QUARANTINE") + cnt(event_type="action_quarantined")
    out["protected_consequences_attempted"] = _m(
        "protected_consequences_attempted",
        "Actions proposed against a protected consequence boundary.",
        attempted, attempted, "action_proposed events", None, None,
        attempted, window)
    out["committed_consequences"] = _m(
        "committed_consequences",
        "Protected consequences the receiver allowed to proceed.",
        committed, committed, "COMMIT decisions + action_committed events",
        None, None, committed, window)
    out["refused_consequences"] = _m(
        "refused_consequences",
        "Protected consequences refused or stopped at the boundary.",
        refused, refused, "DENY/STOPPED decisions + action_refused events",
        None, None, refused, window)
    out["quarantined_actions"] = _m(
        "quarantined_actions",
        "Actions held for review; consequence did not proceed.",
        quarantined, quarantined,
        "QUARANTINE decisions + action_quarantined events",
        None, None, quarantined, window)

    # -- stale authority ----------------------------------------------------
    # Denominator: protected actions with observable authority standing,
    # each record counted once. (A stale attempt is itself such an action.)
    ACTION_FAMILY = ("action_proposed", "action_committed", "action_refused",
                     "action_quarantined", "action_stopped",
                     "stale_authority_attempt")
    _STANDING_OK = ("MANDATE_ACTIVE", "MANDATE_REVOKED", "MANDATE_SUPERSEDED",
                    "MANDATE_NARROWED")
    stale = cnt(event_type="stale_authority_attempt")
    standing_observable = sum(
        1 for r in store.ledger(limit=1000000, since=since, until=until)
        if r["event_type"] in ACTION_FAMILY
        and r["authority_state"] in _STANDING_OK)
    if standing_observable > 0:
        out["stale_authority_attempt_rate"] = _m(
            "stale_authority_attempt_rate",
            "Protected actions attempted on authority no longer in standing, "
            "over protected actions where current authority standing was observable.",
            round(stale / standing_observable, 4),
            stale, "stale_authority_attempt events",
            standing_observable,
            "protected actions with observable authority standing",
            stale + standing_observable, window)
    else:
        out["stale_authority_attempt_rate"] = _m(
            "stale_authority_attempt_rate",
            "Protected actions attempted on authority no longer in standing, "
            "over protected actions where current authority standing was observable.",
            None, stale, "stale_authority_attempt events",
            None, "protected actions with observable authority standing",
            stale, window,
            not_measurable_reason="denominator cannot be established: no "
                                  "protected actions with observable authority "
                                  "standing in this window")
    out["stale_authority_attempts"] = _m(
        "stale_authority_attempts",
        "Count of protected actions attempted on non-current authority.",
        stale, stale, "stale_authority_attempt events", None, None,
        stale, window)

    # -- replay --------------------------------------------------------------
    replay = cnt(event_type="replay_attempt")
    out["replay_attempts"] = _m(
        "replay_attempts",
        "Observed attempts to replay a previously seen receipt/action.",
        replay, replay, "replay_attempt events", None, None, replay, window)

    # -- revocation ------------------------------------------------------------
    revocations = cnt(event_type="mandate_revoked")
    out["revocations"] = _m(
        "revocations",
        "Mandate revocations recorded.",
        revocations, revocations, "mandate_revoked events", None, None,
        revocations, window)

    lag = _propagation_lag(store, since, until)
    out["revocation_propagation_lag"] = lag

    # -- ancestry ---------------------------------------------------------------
    ancestry_fail = cnt(event_type="invalid_ancestry")
    out["ancestry_failures"] = _m(
        "ancestry_failures",
        "Receipts whose ancestry chain failed validation.",
        ancestry_fail, ancestry_fail, "invalid_ancestry events", None, None,
        ancestry_fail, window)

    # -- recovery ------------------------------------------------------------------
    rec_att = cnt(event_type="recovery_proposed")
    rec_ok = cnt(event_type="recovery_succeeded")
    rec_fail = cnt(event_type="recovery_failed")
    out["recovery_attempts"] = _m(
        "recovery_attempts",
        "Recovery proposals recorded.", rec_att, rec_att,
        "recovery_proposed events", None, None, rec_att, window)
    out["successful_recoveries"] = _m(
        "successful_recoveries",
        "Recoveries that completed.", rec_ok, rec_ok,
        "recovery_succeeded events", None, None, rec_ok, window)
    out["failed_recoveries"] = _m(
        "failed_recoveries",
        "Recoveries that failed.", rec_fail, rec_fail,
        "recovery_failed events", None, None, rec_fail, window)

    # -- false holds -----------------------------------------------------------------
    fh = cnt(event_type="false_hold")
    gt = cnt(event_type="semantic_challenge") + cnt(event_type="semantic_hold")
    if gt > 0:
        out["false_hold_rate"] = _m(
            "false_hold_rate",
            "Legitimate actions incorrectly stopped, over cases with "
            "independently established legitimate ground truth. Ground truth "
            "is NOT inferred from later allowance.",
            round(fh / gt, 4), fh, "false_hold events", gt,
            "challenge/hold cases with established ground truth",
            fh + gt, window)
    else:
        out["false_hold_rate"] = _m(
            "false_hold_rate",
            "Legitimate actions incorrectly stopped, over cases with "
            "independently established legitimate ground truth.",
            None, fh, "false_hold events", None,
            "challenge/hold cases with established ground truth",
            fh, window,
            not_measurable_reason="no challenge/hold cases with independently "
                                  "established ground truth in this window")
    out["false_holds"] = _m(
        "false_holds",
        "Count of legitimate actions stopped by challenge machinery.",
        fh, fh, "false_hold events", None, None, fh, window)

    # -- unresolved ------------------------------------------------------------------
    unresolved = cnt(event_type="unresolved_standing") \
        + cnt(event_type="challenge_unresolved") \
        + cnt(event_type="apparatus_incomplete")
    out["unresolved_incidents"] = _m(
        "unresolved_incidents",
        "Cases where standing or outcome could not be established from evidence.",
        unresolved, unresolved,
        "unresolved_standing + challenge_unresolved + apparatus_incomplete events",
        None, None, unresolved, window)

    # -- continuity ----------------------------------------------------------------------
    handoffs = cnt(event_type="provider_replacement")
    cont_fail = cnt(event_type="continuity_failure")
    out["provider_handoffs"] = _m(
        "provider_handoffs",
        "Provider/model replacements recorded.", handoffs, handoffs,
        "provider_replacement events", None, None, handoffs, window)
    out["continuity_failures"] = _m(
        "continuity_failures",
        "Handoffs where continuity was not preserved.", cont_fail, cont_fail,
        "continuity_failure events", None, None, cont_fail, window)

    return out


def _propagation_lag(store, since, until):
    """Revocation propagation lag: revocation observed -> first confirmed
    enforcement at a receiver. Only where BOTH timestamps exist."""
    revocations = store.ledger(event_type="mandate_revoked",
                               since=since, until=until, limit=1000000)
    lags = []
    for rev in revocations:
        if not rev["timestamp"]:
            continue
        # enforcement: a refusal/stop naming the same principal+actor after revocation
        cands = store.ledger(since=rev["timestamp"], until=until, limit=1000000)
        best = None
        for c in cands:
            if not c["timestamp"]:
                continue
            if c["decision"] not in ("DENY", "STOPPED"):
                continue
            if rev.get("principal") and c.get("principal") != rev["principal"]:
                continue
            if rev.get("actor") and c.get("actor") != rev["actor"]:
                continue
            if best is None or c["timestamp"] < best:
                best = c["timestamp"]
        if best:
            lags.append({"revocation_receipt": rev["receipt_id"],
                         "enforcement_receipt": None,
                         "revoked_at": rev["timestamp"],
                         "enforced_at": best})
    # find enforcement receipt ids
    for l in lags:
        cands = store.ledger(since=l["enforced_at"], until=l["enforced_at"],
                             limit=1000000)
        l["enforcement_receipt"] = cands[0]["receipt_id"] if cands else None
    if not lags:
        return _m(
            "revocation_propagation_lag",
            "Time from authoritative revocation observation to first confirmed "
            "enforcement at a receiver. Only where both timestamps exist.",
            None, None, "measured lags", None, "revocations with timestamps",
            0, {"since": since, "until": until} if (since or until) else None,
            not_measurable_reason="no revocation->enforcement pairs with both "
                                  "timestamps in this window")
    # report as list of measured lags (seconds where parseable); value = count
    return _m(
        "revocation_propagation_lag",
        "Time from authoritative revocation observation to first confirmed "
        "enforcement at a receiver. Only where both timestamps exist.",
        len(lags), len(lags), "measured revocation->enforcement pairs",
        None, None, len(lags),
        {"since": since, "until": until} if (since or until) else None)


def metric_definitions():
    """Static catalog of metric definitions for the Coverage view."""
    return [
        ("stale_authority_attempt_rate",
         "Requires observable authority standing on the denominator actions; "
         "not computed when the denominator cannot be established."),
        ("revocation_propagation_lag",
         "Requires both revocation and enforcement timestamps; pairs missing "
         "either are excluded, not estimated."),
        ("false_hold_rate",
         "Requires independently established legitimate ground truth; "
         "legitimacy is never inferred from later allowance."),
    ]
