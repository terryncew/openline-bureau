"""Read-only adapter for selected, original Exchange commission records.

No embedded trust list is accepted. Signature checks authenticate keys;
the buyer's trustworthiness is a separate, operator-configured policy.
Wallet's installed crypto helpers are reused; without them evidence remains
unauthenticated. No key files, inputs, prompts, or Wallet histories are read.
"""
import hashlib
import json

from ..schema import make_record

FORMAT = "openline.exchange.selected-evidence.v1"
PHASES = {"agreement": "commission.agreement.v1",
          "submission": "commission.result.v1",
          "verdict": "commission.verdict.v1",
          "settlement": "commission.settlement.v1"}
REQUIRED_CHECKS = {"agreement_integrity", "payee_matches_offer", "result_submitted",
                   "seller_signature", "result_binds_job", "acceptance_exact_recompute",
                   "within_deadline"}


def digest(value):
    # Commission uses Wallet canonical JSON, which preserves UTF-8.
    from openline_wallet.canonical import canonical_json
    return hashlib.sha256(canonical_json(value)).hexdigest()


def authentic(envelope, principal, schema):
    try:
        from openline_wallet.crypto import verify_record, principal_id
        record, signed = envelope["record"], envelope["signature"]
        if record.get("schema") != schema:
            return False
        if principal_id(signed["signature"]["public_key"]) != principal:
            return False
        ok, _ = verify_record(signed)
        body = {k: v for k, v in signed.items() if k not in ("payload_hash", "signature")}
        return ok and body == record
    except Exception:  # malformed public key/record or crypto unavailable: fail closed
        return False


def assess(job, trusted_buyers=()):
    """Recompute evidence status; never trust a stored verification boolean."""
    try:
        a = job["agreement"]["record"]
        ah = digest(a)
        agreement_ok = (authentic(job["agreement"], a["agent"], PHASES["agreement"])
                        and a["job_id"] == job["job_id"]
                        and a.get("service") == "text_digest"
                        and a.get("currency") == "SIM_USD (simulated)"
                        and type(a.get("amount")) is int and a["amount"] > 0
                        and a.get("payee") == a.get("seller"))
        offer = job.get("offer") or {}
        o = offer.get("record") or {}
        offer_ok = (authentic(offer, a["seller"], "commission.offer.v1")
                    and o.get("offer_id") == a.get("offer_id")
                    and o.get("price") == a["amount"]
                    and o.get("service") == a.get("service")
                    and o.get("acceptance") == a.get("acceptance")
                    and a.get("acceptance", {}).get("type") == "exact_recompute"
                    and set(a.get("acceptance", {}).get("fields", [])) ==
                    {"input_sha256", "word_count", "line_count", "nonce"})
        v = (job.get("verdict") or {}).get("record") or {}
        verifier = a["buyer"] if v.get("verified_by") == "owner" else a["agent"]
        buyer_independent = a["buyer"] != a["seller"] and verifier != a["seller"]
        verdict_ok = (agreement_ok and offer_ok and buyer_independent
                      and authentic(job.get("verdict"), verifier, PHASES["verdict"])
                      and v.get("agreement_hash") == ah
                      and v.get("job_id") == a["job_id"]
                      and v.get("verified_by") in ("owner", "agent", "agent-b"))
        checks = v.get("checks") or []
        all_checks = (len(checks) == len(REQUIRED_CHECKS)
                      and {c.get("name") for c in checks} == REQUIRED_CHECKS
                      and all(c.get("pass") is True for c in checks))
        s = (job.get("submission") or {}).get("record") or {}
        result_ok = (authentic(job.get("submission"), a["seller"], PHASES["submission"])
                     and s.get("job_id") == a["job_id"]
                     and s.get("input_sha256") == a.get("input_sha256")
                     and s.get("nonce") == a.get("nonce")
                     and s.get("service") == a.get("service"))
        # An embedded agent key proves no delegation from a pinned buyer.
        # Until selective delegation evidence is supplied, only that buyer's
        # own receiver signature can support a trusted completion claim.
        trusted = a["buyer"] in trusted_buyers and verifier == a["buyer"]
        accepted = verdict_ok and trusted and all_checks and result_ok and v.get("verdict") == "accepted"
        rejected = verdict_ok and trusted and v.get("verdict") == "rejected"
        settlement = (job.get("settlement") or {}).get("record") or {}
        settled = (accepted and authentic(job.get("settlement"), a["buyer"], PHASES["settlement"])
                   and settlement.get("agreement_hash") == ah
                   and settlement.get("verdict_hash") == digest(v)
                   and settlement.get("job_id") == a["job_id"]
                   and settlement.get("settlement_id") == "settle:" + ah
                   and settlement.get("amount") == a["amount"]
                   and settlement.get("currency") == "SIM_USD (simulated)"
                   and settlement.get("from") == a["buyer"]
                   and settlement.get("to") == a["seller"])
        return {"agreement": agreement_ok, "offer": offer_ok, "verdict": verdict_ok,
                "result": result_ok, "trusted_buyer": trusted,
                "accepted": bool(accepted), "rejected": bool(rejected),
                "settled": bool(settled), "agreement_hash": ah}
    except (ImportError, KeyError, TypeError, ValueError):
        return {k: False for k in ("agreement", "offer", "verdict", "result",
                                   "trusted_buyer", "accepted", "rejected", "settled")}


def detect(payload):
    return isinstance(payload, dict) and payload.get("format") == FORMAT


def adapt(payload, provenance):
    out = []
    for job in payload.get("jobs", []):
        a = job["agreement"]["record"]
        # No trust is inferred at ingestion. The comparison revalidates raw
        # evidence under the server's buyer policy on every request.
        state = assess(job)
        ids = {phase: "exchange:" + a["job_id"] + ":" + phase + ":" + envelope['signature']['payload_hash']
               for phase in PHASES if (envelope := job.get(phase))
               and envelope.get('signature', {}).get('payload_hash')}
        for phase, schema in PHASES.items():
            envelope = job.get(phase)
            if not envelope:
                continue
            record = envelope["record"]
            if record.get("schema") != schema:
                raise ValueError("unsupported Exchange record schema")
            signed_hash = envelope.get("signature", {}).get("payload_hash")
            identity = signed_hash or hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
            rid = "exchange:" + a["job_id"] + ":" + phase + ":" + identity
            event = {"agreement": "action_proposed", "submission": "effect_observed",
                     "verdict": "action_refused" if record.get("verdict") == "rejected" else "effect_observed",
                     "settlement": "effect_observed"}[phase]
            # Only cryptographically authenticated buyer decisions are mapped.
            decision = None
            if phase == "verdict" and state["verdict"]:
                decision = "DENY" if record.get("verdict") == "rejected" else None
            parents = []
            if phase == 'settlement' and 'verdict' in ids:
                parents = [ids['verdict']]
            elif phase == 'verdict':
                parents = [ids[p] for p in ('agreement', 'submission') if p in ids]
            elif phase == 'submission' and 'agreement' in ids:
                parents = [ids['agreement']]
            out.append(make_record(
                receipt_id=rid, system="openline-exchange", experiment="BUREAU-ALLOCATION-001",
                principal=a.get("buyer"), actor=a.get("seller"), action=a.get("service"),
                target=a.get("offer_id"), timestamp=record.get("at"), event_type=event,
                decision=decision, authority_state=None, effect_observed=None,
                parent_receipts=parents,
                raw={"format": FORMAT, "job": job, "phase": phase,
                     "source": payload.get("source"), "profiles": payload.get("profiles", [])},
                unmapped={"original_job_id": a["job_id"], "original_record_hash": identity,
                          "source_sha256": payload.get("source", {}).get("sha256"),
                          "authorization_standing": "NOT ESTABLISHED (no mandate evidence exported)",
                          "simulation": True}, adapter="exchange", **provenance))
    return out
