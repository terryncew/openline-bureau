"""Task-specific buyer comparison over authenticated selected evidence."""
from .adapters.exchange import assess, FORMAT

MIN_HISTORY = 3  # decision rule for the deterministic fixture, not statistical confidence


def comparison(store, service="text_digest", trusted_buyers=(), before=None):
    records = store.ledger(system="openline-exchange", limit=1000000)
    jobs, profiles = {}, {}
    for rec in records:
        raw = rec.get("raw") or {}
        if raw.get("format") != FORMAT or not isinstance(raw.get("job"), dict):
            continue
        if before and (not rec.get("timestamp") or rec["timestamp"] >= before):
            continue
        job = raw["job"]
        a = job.get("agreement", {}).get("record", {})
        if a.get("service") != service:
            continue
        for profile in raw.get("profiles", []):
            if profile.get("service") == service:
                profiles[profile["seller_id"]] = profile
        key = (a.get("buyer"), a.get("job_id"))
        item = jobs.setdefault(key, {"snapshots": [], "ids": {}, "evidence": []})
        item["snapshots"].append(job)
        item["evidence"].append(rec)
        item["ids"].setdefault(raw.get("phase"), set()).add(rec["receipt_id"])
    rows = []
    for worker, profile in sorted(profiles.items()):
        job_states = []
        accepted, rejected, costs, known, unresolved, sources, success_sources, failure_sources, cost_sources = [], [], [], [], [], [], [], [], []
        for key, item in jobs.items():
            candidates = [j for j in item["snapshots"]
                          if j["agreement"]["record"].get("seller") == worker]
            if not candidates:
                continue
            states = [(j, assess(j, trusted_buyers)) for j in candidates]
            agreement_hashes = {s['agreement_hash'] for j, s in states if s['agreement']}
            outcomes = {"accepted" if s["accepted"] else "rejected"
                        for j, s in states if s["accepted"] or s["rejected"]}
            sources.extend(rid for ids in item["ids"].values() for rid in ids)
            if len(outcomes) != 1 or len(agreement_hashes) != 1:
                unresolved.append(key[1])
                job_states.append({"job_id": key[1], "outcome": "NOT ESTABLISHED",
                                   "settlement": "NOT ESTABLISHED"})
                continue
            known.append(key[1])
            if "accepted" in outcomes:
                accepted.append(key[1])
                success_sources.extend(r['receipt_id'] for r in item['evidence']
                                       if r['raw']['phase'] == 'verdict'
                                       and assess(r['raw']['job'], trusted_buyers)['accepted'])
                settlements = {j["settlement"]["record"]["amount"] for j, s in states if s["settled"]}
                if len(settlements) == 1:
                    costs.append(next(iter(settlements)))
                    cost_sources.extend(r['receipt_id'] for r in item['evidence']
                                        if r['raw']['phase'] == 'settlement'
                                        and assess(r['raw']['job'], trusted_buyers)['settled'])
                job_states.append({"job_id": key[1], "outcome": "BUYER_VERIFIED_ACCEPTED",
                                   "settlement": "SIMULATED_SETTLEMENT_OBSERVED" if len(settlements) == 1 else "PENDING / NOT ESTABLISHED"})
            else:
                rejected.append(key[1])
                failure_sources.extend(r['receipt_id'] for r in item['evidence']
                                       if r['raw']['phase'] == 'verdict'
                                       and assess(r['raw']['job'], trusted_buyers)['rejected'])
                job_states.append({"job_id": key[1], "outcome": "BUYER_VERIFIED_REJECTED",
                                   "settlement": "NO PAYMENT UNDER AGREEMENT RULE; release evidence not exported"})
        complete_cost = len(costs) == len(accepted) and bool(known)
        rows.append({"worker_id": worker, "profile": profile,
                     "advertisement_authenticity": "self-reported registry profile",
                     "comparable_verified_jobs": len(known),
                     "accepted": len(accepted), "rejected": len(rejected),
                     "unresolved_jobs": unresolved,
                     "job_states": job_states,
                     "accepted_fraction": len(accepted) / len(known) if known else None,
                     "denominator": "distinct authenticated buyer verdicts for this job type; not all attempts",
                     "attempt_count": None, "unobserved_failure_count": None,
                     "observed_simulated_cost": sum(costs) if complete_cost else None,
                     "cost_definition": "signed SIM_USD settlement amounts for accepted jobs; rejected jobs pay nothing under the Exchange rules; excludes work and opportunity costs",
                     "accepted_per_simulated_unit": len(accepted) / sum(costs) if complete_cost and sum(costs) else None,
                     "real_payment": "NOT ESTABLISHED — all settlement is simulated",
                     "authorization_standing": "NOT ESTABLISHED — selected transaction evidence is not a current mandate",
                     "ranking_status": "fixture decision rule available" if len(known) >= MIN_HISTORY and not unresolved else "cannot yet be ranked reliably",
                     "receipt_ids": sorted(set(sources)),
                     "accepted_receipt_ids": sorted(set(success_sources)),
                     "rejected_receipt_ids": sorted(set(failure_sources)),
                     "cost_receipt_ids": sorted(set(cost_sources))})
    return {"service": service, "workers": rows, "trusted_buyers": list(trusted_buyers),
            "minimum_history": MIN_HISTORY,
            "warning": "Local controlled demonstration. Buyer verification is independent of the seller, not independent commercial attestation. Sparse history is not evidence of untrustworthiness."}


def choose(profiles, history=None, budget=60):
    """Frozen selector accepts only public candidates and historical rows.

    Control picks the cheapest matching offer. Bureau maximizes observed
    accepted fraction / offered price if >=3 verdicts and no unresolved job;
    otherwise it uses the identical control rule. It can lose after drift.
    """
    pool = [p for p in profiles if p["service"] == "text_digest"
            and p["standing"] == "active" and 0 < p["price"] <= budget]
    if not pool:
        raise ValueError("no candidate within budget")
    eligible = {r["worker_id"]: r for r in (history or [])
                if r["comparable_verified_jobs"] >= MIN_HISTORY and not r["unresolved_jobs"]}
    if eligible:
        supported = [p for p in pool if p["seller_id"] in eligible]
        if supported:
            return min(supported, key=lambda p: (
                -eligible[p["seller_id"]]["accepted_fraction"] / p["price"],
                p["price"], p["seller_id"]))["seller_id"]
    return min(pool, key=lambda p: (p["price"], p["seller_id"]))["seller_id"]
