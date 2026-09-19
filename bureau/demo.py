#!/usr/bin/env python3
"""OpenLine Bureau — synthetic demo dataset generator.

Deterministic. Writes data/synthetic-demo.json (canonical dump) and can
load it into a SQLite store. The entire dataset is prominently marked
SYNTHETIC DEMO DATA and must never be presented as observed data.

The dataset tells ONE canonical walkthrough story, step by step:

  1. worker-a receives authority (mandate_issued).
  2. worker-a performs legitimate actions (proposed -> committed, observed).
  3. worker-a builds an artifact at a consequence boundary (observed
     checkpoint; this receipt matters later).
  4. The owner revokes worker-a (mandate_revoked).
  5. worker-a attempts another protected action; the receiver refuses it
     as MANDATE_REVOKED (stale_authority_attempt -> STOPPED).
  6. The already-created worker-a artifact is presented at a second
     receiver later and is refused because the origin's standing is stale
     (delayed_standing_failure -> DENY, ancestry links to both the
     artifact creation and the revocation).
  7. Successor worker-b receives fresh authority (mandate_issued).
  8. worker-b continues from the accepted checkpoint (successor_continuation)
     and resumes legitimate work (action_committed, observed).
  9. The Bureau displays the whole chain with evidence: every refusal
     links back to the revocation; every continuation links back to the
     accepted checkpoint.

A second thread (worker-c) adds the incident/coverage material the other
views need: a reconciled challenge, a false hold, a successful and a
failed recovery, unresolved cases, and a narrowed mandate.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from bureau.schema import make_record, validate  # noqa: E402

BASE = "2026-09-10T"
PRINCIPAL = "demo:principal:acme-corp"
PROV = dict(source_repo="synthetic-demo",
            source_path="data/synthetic-demo.json",
            raw_ref="data/synthetic-demo.json")


def T(h, m, s=0):
    return "%s%02d:%02d:%02dZ" % (BASE, h, m, s)


_seq = [0]


def rid(kind):
    _seq[0] += 1
    return "syn-%s-%03d" % (kind, _seq[0])


def R(event_type, ts, actor, action=None, decision=None, authority_state=None,
      reason=None, effect_observed=None, standing=None, parents=(),
      target=None, experiment="SYNTHETIC_DEMO"):
    rec = make_record(
        receipt_id=rid(event_type.replace("_", "")[:6]),
        timestamp=ts, system="synthetic-demo", experiment=experiment,
        principal=PRINCIPAL, actor=actor, action=action, target=target,
        authority_state=authority_state, decision=decision,
        event_type=event_type, reason=reason, effect_observed=effect_observed,
        standing=standing, parent_receipts=list(parents),
        adapter="synthetic", raw={"synthetic": True, "note": "demo fixture"},
        **PROV)
    problems = validate(rec)
    assert not problems, problems
    return rec


def build():
    recs = []
    # -- Thread 1: the canonical walkthrough --------------------------------
    # Step 1: worker-a receives authority.
    issue_a = R("mandate_issued", T(9, 0), "worker-a",
                action="deploy:staging", authority_state="MANDATE_ACTIVE",
                reason="owner grant", standing="CURRENT")
    recs.append(issue_a)
    # Step 2: worker-a performs legitimate actions.
    proposed = R("action_proposed", T(9, 5), "worker-a",
                 action="deploy:staging", decision="ALLOWED",
                 authority_state="MANDATE_ACTIVE", target="receiver-1",
                 parents=[issue_a["receipt_id"]])
    recs.append(proposed)
    committed = R("action_committed", T(9, 5, 12), "worker-a",
                  action="deploy:staging", decision="COMMIT",
                  authority_state="MANDATE_ACTIVE", effect_observed=True,
                  target="receiver-1", parents=[proposed["receipt_id"]])
    recs.append(committed)
    # Step 3: worker-a builds an artifact at a consequence boundary.
    # This receipt is the accepted checkpoint the successor later uses.
    artifact = R("action_committed", T(10, 30), "worker-a",
                 action="bundle:build", decision="COMMIT",
                 authority_state="MANDATE_ACTIVE", effect_observed=True,
                 target="artifact/deploy-bundle-v7",
                 parents=[committed["receipt_id"]])
    recs.append(artifact)
    # Step 4: the owner revokes worker-a.
    revoked = R("mandate_revoked", T(11, 0), "worker-a",
                action="deploy:staging", authority_state="MANDATE_REVOKED",
                reason="owner revoked after incident", standing="REVOKED")
    recs.append(revoked)
    # Step 5: worker-a attempts another protected action; the receiver
    # refuses it as MANDATE_REVOKED. The refusal links to the revocation.
    stale = R("stale_authority_attempt", T(11, 1, 30), "worker-a",
              action="deploy:staging", decision="STOPPED",
              authority_state="MANDATE_REVOKED",
              reason="MANDATE_REVOKED", effect_observed=False,
              standing="REVOKED", target="receiver-1",
              parents=[revoked["receipt_id"]])
    recs.append(stale)
    # Revocation confirmed at a second receiver (gives a measurable
    # revocation -> enforcement pair for the propagation-lag metric).
    recs.append(R("revocation_propagated", T(11, 2, 5), "worker-a",
                  authority_state="MANDATE_REVOKED", standing="REVOKED",
                  reason="receiver-2 confirmed enforcement",
                  target="receiver-2", parents=[revoked["receipt_id"]]))
    # A replayed pre-revocation payload is refused too.
    recs.append(R("replay_attempt", T(11, 30), "worker-a",
                  action="deploy:staging", decision="DENY",
                  authority_state="MANDATE_REVOKED",
                  reason="payload_hash already seen", effect_observed=False,
                  standing="REVOKED", target="receiver-1"))
    # Step 6: the already-created worker-a artifact is presented at a
    # second consequence boundary and refused because the origin's
    # standing is stale. Ancestry links to both the artifact's creation
    # and the revocation that invalidated it.
    recs.append(R("delayed_standing_failure", T(12, 0), "worker-a",
                  action="present-artifact", decision="DENY",
                  authority_state="MANDATE_REVOKED",
                  reason="artifact standing changed after creation: "
                         "mandate revoked at %s" % revoked["timestamp"],
                  effect_observed=False, standing="REVOKED",
                  target="receiver-2",
                  parents=[artifact["receipt_id"], revoked["receipt_id"]]))
    # Step 7: successor worker-b receives fresh authority.
    issue_b = R("mandate_issued", T(13, 0), "worker-b",
                action="deploy:staging", authority_state="MANDATE_ACTIVE",
                reason="successor grant after worker-a revocation",
                standing="CURRENT")
    recs.append(issue_b)
    recs.append(R("provider_replacement", T(13, 5), "worker-b",
                  action="deploy:staging", authority_state="MANDATE_ACTIVE",
                  reason="worker-a revoked; worker-b holds fresh mandate; "
                         "continuity via accepted checkpoint",
                  standing="CURRENT",
                  parents=[revoked["receipt_id"], issue_b["receipt_id"]]))
    # Step 8: worker-b continues from the accepted checkpoint and resumes
    # legitimate work.
    continued = R("successor_continuation", T(13, 20), "worker-b",
                  action="deploy:staging", authority_state="MANDATE_ACTIVE",
                  reason="continued from accepted checkpoint of worker-a",
                  standing="CURRENT",
                  parents=[issue_b["receipt_id"], artifact["receipt_id"]])
    recs.append(continued)
    recs.append(R("action_committed", T(13, 20, 30), "worker-b",
                  action="deploy:staging", decision="COMMIT",
                  authority_state="MANDATE_ACTIVE", effect_observed=True,
                  target="receiver-1", parents=[continued["receipt_id"]]))
    # -- Thread 2: incident / coverage material (worker-c) -------------------
    ch1 = R("semantic_challenge", T(15, 10), "worker-c",
            action="db:drop-table", decision="CHALLENGE",
            authority_state="MANDATE_ACTIVE",
            reason="guardian: destructive action, confirm intent")
    recs.append(ch1)
    recs.append(R("action_quarantined", T(15, 10, 20), "worker-c",
                  action="db:drop-table", decision="QUARANTINE",
                  authority_state="MANDATE_ACTIVE",
                  reason="held pending reconciliation",
                  parents=[ch1["receipt_id"]]))
    rec_ok = R("challenge_reconciled", T(15, 25), "worker-c",
               action="db:drop-table",
               reason="operator confirmed intended migration step",
               parents=[ch1["receipt_id"]])
    recs.append(rec_ok)
    recs.append(R("action_committed", T(15, 26), "worker-c",
                  action="db:drop-table", decision="COMMIT",
                  authority_state="MANDATE_ACTIVE", effect_observed=True,
                  target="receiver-1", parents=[rec_ok["receipt_id"]]))
    # False hold: legitimate action stopped by challenge machinery.
    ch2 = R("semantic_challenge", T(16, 0), "worker-c",
            action="cache:flush", decision="CHALLENGE",
            authority_state="MANDATE_ACTIVE",
            reason="guardian: unusual hour")
    recs.append(ch2)
    held = R("action_quarantined", T(16, 0, 15), "worker-c",
             action="cache:flush", decision="QUARANTINE",
             authority_state="MANDATE_ACTIVE",
             reason="held pending reconciliation",
             parents=[ch2["receipt_id"]])
    recs.append(held)
    recs.append(R("false_hold", T(16, 45), "worker-c",
                  action="cache:flush",
                  reason="independent review: action was legitimate and "
                         "routine; quarantine was premature",
                  parents=[held["receipt_id"]]))
    # Recovery: one success, one failure.
    rp1 = R("recovery_proposed", T(17, 0), "agent-recovery-1",
            action="db:migrate", reason="retry after receiver timeout")
    recs.append(rp1)
    recs.append(R("recovery_succeeded", T(17, 12), "agent-recovery-1",
                  action="db:migrate", effect_observed=True,
                  reason="second attempt committed",
                  parents=[rp1["receipt_id"]]))
    rp2 = R("recovery_proposed", T(17, 30), "agent-recovery-1",
            action="deploy:staging", reason="retry after quarantine")
    recs.append(rp2)
    recs.append(R("recovery_failed", T(17, 44), "agent-recovery-1",
                  action="deploy:staging", effect_observed=False,
                  reason="mandate revoked during recovery; stopped",
                  parents=[rp2["receipt_id"]]))
    # Unresolved: challenge raised, evidence never arrived.
    ch3 = R("semantic_challenge", T(18, 5), "worker-c",
            action="net:egress", decision="CHALLENGE",
            authority_state="MANDATE_ACTIVE",
            reason="guardian: unclassified external call")
    recs.append(ch3)
    recs.append(R("challenge_unresolved", T(19, 5), "worker-c",
                  action="net:egress",
                  reason="no reconciliation evidence within 24h window",
                  parents=[ch3["receipt_id"]]))
    recs.append(R("apparatus_incomplete", T(19, 5, 1), "worker-c",
                  action="net:egress",
                  reason="effect confirmation unavailable: "
                         "uninstrumented path",
                  parents=[ch3["receipt_id"]]))
    # Mandate narrowed for worker-c.
    recs.append(R("mandate_narrowed", T(20, 0), "worker-c",
                  action="db:migrate", authority_state="MANDATE_NARROWED",
                  reason="scope reduced to read-only after review",
                  standing="CURRENT"))
    assert len(recs) == 28, len(recs)
    return recs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="data/synthetic-demo.json")
    ap.add_argument("--db", default=None,
                    help="optional: also load into this SQLite store")
    args = ap.parse_args(argv)
    recs = build()
    os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
    dump = {"format": "openline.bureau.canonical.v1",
            "dataset": "SYNTHETIC DEMO DATA",
            "warning": ("SYNTHETIC DEMO DATA — not observed OpenLine "
                        "production data"),
            "records": recs}
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=1, default=str)
    print("wrote %d synthetic records -> %s" % (len(recs), args.json))
    if args.db:
        from bureau.store import Store
        st = Store(args.db)
        from bureau.adapters import adapt
        prov = dict(source_repo="synthetic-demo",
                    source_path=os.path.abspath(args.json),
                    raw_ref=os.path.abspath(args.json))
        s = st.ingest_many(adapt(dump, prov))
        print("ingest:", s)
        st.close()


if __name__ == "__main__":
    main()
