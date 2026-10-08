"""One local reproducible loop and a prospectively frozen synthetic trial."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from .adapters import adapt
from .adapters.exchange import assess
from .allocation import choose, comparison
from .store import Store

PROTOCOL = {
    "version": "BUREAU-ALLOCATION-001/v1",
    "label": "DETERMINISTIC SYNTHETIC WORKERS AND TASKS; NO ECONOMIC CLAIM",
    "control": "lowest advertised price within budget; ties by worker id",
    "bureau": "with >=3 distinct buyer-verified historical verdicts and no unresolved job, maximize accepted fraction / offered price; otherwise control",
    "pool": "same three text_digest workers and advertised prices, both conditions",
    "task_budget": 60, "held_out_tasks": 4,
    "evaluation": "existing buyer receiver exact_recompute; existing settlement rules",
    "primary": "Bureau verified completion rate minus control rate on paired held-out tasks",
    "decision": "INCONCLUSIVE if fewer than 4 paired tasks, unknown outcomes or fewer than 3 historical verdicts for A and B; ADVANTAGE if primary >0, otherwise NO_ADVANTAGE (including losses)",
    "secondary": "accepted per signed settled SIM_USD, rejected selections, sparse fallback, paired worse choices",
    "cost_boundary": "only simulated settlement cost is observed; failed work remains unpaid; labor/compute/opportunity cost unknown",
    "privacy": "export selected signed public text_digest records only; no inputs or private Wallet history",
}


def write(path, obj):
    with Path(path).open("x") as f:
        json.dump(obj, f, indent=2, sort_keys=True)


def seal(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def trial_result(rows, sparse=False):
    groups = {condition: [r for r in rows if r["condition"] == condition]
              for condition in ("control", "bureau")}
    summary = {}
    for condition, runs in groups.items():
        accepted = sum(r["accepted"] is True for r in runs)
        rejected = sum(r["rejected"] is True for r in runs)
        cost = sum(r["settled_sim_usd"] for r in runs if r["settled_sim_usd"] is not None)
        summary[condition] = {"accepted": accepted, "rejected": rejected, "selections": len(runs),
                              "completion_rate": accepted / len(runs) if runs else None,
                              "observed_settled_sim_usd": cost,
                              "accepted_per_settled_sim_usd": accepted / cost if cost else None}
    complete = (len(groups["control"]) == len(groups["bureau"]) == 4
                and all(r["accepted"] or r["rejected"] for r in rows) and not sparse)
    delta = (summary["bureau"]["completion_rate"] - summary["control"]["completion_rate"]
             if summary["control"]["completion_rate"] is not None and summary["bureau"]["completion_rate"] is not None else None)
    worse = [b["task"] for b in groups["bureau"] if not b["accepted"] and
             any(c["task"] == b["task"] and c["accepted"] for c in groups["control"])]
    return {"verdict": "INCONCLUSIVE" if not complete else "ADVANTAGE" if delta > 0 else "NO_ADVANTAGE",
            "completion_delta": delta, "bureau_worse_tasks": worse, "conditions": summary,
            "sparse_history": sparse, "rows": rows, "protocol_sha256": seal(PROTOCOL)}


def run(wallet_repo, out, scenario="mixed", sparse=False):
    # Refuse reuse: no stale artifacts or future evidence can contaminate history.
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    write(out / "protocol.json", PROTOCOL)  # freeze BEFORE creating any jobs
    sys.path.insert(0, str(Path(wallet_repo).resolve() / "demo/agent-exchange-001"))
    from exchange.kernel import Exchange
    from exchange.evidence import export_selected
    from exchange.buyer import prepare, review_hash, authorize, standing
    x = Exchange(out / "exchange"); x.bootstrap(budget=2000)
    listings = {l["seller_name"]: l for l in x.registry.all()}
    buyer = x.principal("owner")
    write(out / "trust.json", {"trusted_buyer": buyer,
                              "scope": "locally provisioned controlled owner receiver"})
    store = Store(str(out / "bureau.db"))
    job_ids = []
    for name in ("Seller A", "Seller B"):
        for i in range(1 if sparse else 3):
            listing = listings[name]
            job = x.commission(listing, text=f"public historical digest {name} {i}")
            x.deliver(job, listing["identity"], wrong_input=name == "Seller B")
            x.adjudicate(job); job_ids.append(job)
    history = export_selected(x, job_ids)
    write(out / "history.json", history)
    prov = {"source_repo": "terryncew/openline-wallet", "source_path": str(out / "history.json")}
    store.ingest_many(adapt(history, prov))
    before = comparison(store, trusted_buyers=[buyer]); write(out / "comparison-before.json", before)
    profiles = history["profiles"]
    choices = {"control": choose(profiles, budget=60),
               "bureau": choose(profiles, before["workers"], budget=60)}
    selections = {"protocol_sha256": seal(PROTOCOL), "history_sha256": seal(history),
                  "choices": choices, "task_ids": [f"heldout-{i}" for i in range(4)],
                  "scenario": scenario, "synthetic": True}
    write(out / "selections.json", selections)  # no future outcomes exist yet
    frozen_hash = seal(selections)
    rows, new_jobs = [], []
    for condition in ("control", "bureau"):
        identity = "trial-" + condition
        x.cli_ok("init-identity", "--name", identity, "--role", "agent")
        x.cli_ok("delegate", "--caller", "owner", "--to", identity, "--budget", "240")
    for i in range(4):
        # Same task content, job type, budget and evaluation. The existing
        # kernel requires a globally unique nonce for each commission.
        task_text = f"public held-out digest task {i}\n"
        for condition in ("control", "bureau"):
            inp = out / f"heldout-{i}-{condition}.txt"
            inp.write_text(json.dumps({"nonce": f"heldout-{i}-{condition}"}) + "\n" + task_text)
            listing = next(l for l in listings.values() if l["seller_id"] == choices[condition])
            if scenario == "reversal":
                fails = listing["seller_name"] == "Seller A"
            else:
                fails = (listing["seller_name"] == "Seller A" and i == 3
                         or listing["seller_name"] == "Seller B" and i != 3)
            job = x.commission(listing, input_path=str(inp), agent_name="trial-" + condition)
            x.deliver(job, listing["identity"], wrong_input=fails); x.adjudicate(job)
            selected = export_selected(x, [job])["jobs"][0]
            checked = assess(selected, [buyer])
            rows.append({"task": f"heldout-{i}", "condition": condition,
                         "worker": listing["seller_id"], "job_id": job,
                         "input_sha256": selected["agreement"]["record"]["input_sha256"],
                         "task_content_sha256": hashlib.sha256(task_text.encode()).hexdigest(),
                         "accepted": checked["accepted"], "rejected": checked["rejected"],
                         "settled_sim_usd": selected["settlement"]["record"]["amount"] if checked["settled"] else None})
            new_jobs.append(job)
    assert seal(json.loads((out / "selections.json").read_text())) == frozen_hash
    result = trial_result(rows, sparse=sparse); write(out / "experiment.json", result)
    # Show the practical owner-reviewed buyer path using the same kernel.
    buyer_listing = next(l for l in listings.values() if l["seller_id"] == choices["bureau"])
    for failure in (False, True):
        inp = out / ("buyer-failure.txt" if failure else "buyer-success.txt")
        inp.write_text(json.dumps({"nonce": inp.stem}) + "\npublic owner-reviewed digest\n")
        plan = prepare(x, buyer_listing["listing_id"], inp, 60, 1)
        approval = authorize(x, plan, review_hash(plan))
        write(out / ("buyer-failure-review.json" if failure else "buyer-success-review.json"), plan)
        x.deliver(approval["job_id"], buyer_listing["identity"], wrong_input=failure)
        x.adjudicate(approval["job_id"]); new_jobs.append(approval["job_id"])
        x.cli_ok("revoke", "--caller", "owner", "--of", approval["agent_identity"])
        assert standing(x, approval["agent_identity"])["standing"] == "NOT ACTIVE"
    # A commissioned but unobserved job never becomes a completion or zero failure.
    pending = x.commission(listings["Seller C"], text="public incomplete evidence fixture")
    new_jobs.append(pending)
    feedback = export_selected(x, new_jobs); write(out / "feedback.json", feedback)
    stats = store.ingest_many(adapt(feedback, {**prov, "source_path": str(out / "feedback.json")}))
    again = store.ingest_many(adapt(feedback, {**prov, "source_path": str(out / "feedback.json")}))
    assert again["inserted"] == 0
    after = comparison(store, trusted_buyers=[buyer]); write(out / "comparison-after.json", after)
    write(out / "walkthrough.json", {"synthetic": True, "trust": buyer, "selected_worker": choices["bureau"],
          "experiment": result["verdict"], "feedback_ingest": stats, "repeat_ingest": again,
          "incomplete_job": pending, "real_payments": 0, "paid_external_calls": 0,
          "evidence_exports": ["history.json", "feedback.json"],
          "private_exchange_home": "exchange/ (contains local private keys; do not publish)",
          "privacy": "selected-record data minimization; no cryptographic selective disclosure"})
    store.close()
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--wallet-repo", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--scenario", choices=["mixed", "reversal"], default="mixed")
    ap.add_argument("--sparse", action="store_true")
    args = ap.parse_args(argv)
    result = run(args.wallet_repo, args.out, args.scenario, args.sparse)
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())
