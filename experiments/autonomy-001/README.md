# OPENLINE-AUTONOMY-001 — Phase 1: thin coordinator experiment

For the current public research presentation and one-command scripted demo,
see [RESEARCH_RELEASE.md](RESEARCH_RELEASE.md). The Phase 1 account below is
historical context; its claims and limitations describe that earlier phase.

**Status: experiment branch. Nothing merged, nothing published, no external spend.**

**Phase 1.5 continuation:** see [PHASE15.md](PHASE15.md) for the current
authorization, isolation, recovery and validation results. The Phase 1 record
below is preserved as historical context.

## What this is

A thin mission loop around already-proven OpenLine components. The
coordinator does not implement agent reasoning, does not evaluate with a
model, and never merges to main. It gives the system continuity: a
standing owner-approved mission, a work queue, crash recovery, worker
replacement, and revocation — the things that were genuinely missing.

## Layout

- `mission.yaml` — owner-authored mission, boundaries, budgets, revocation
  switch. Read-only to the coordinator at runtime; workers never see it.
- `policy/authorized.json` — preauthorized change classes for automatic
  acceptance. Owner-curated.
- `queue/tasks.json` — standing work queue (owner-curated), priority-ordered.
- `coordinator.py` — the loop: SELECT → ASSIGN → BUILD → EVALUATE →
  DECIDE → RECORD. One `--once` run = one cycle; wake it with cron.
- `workers.py` — model-neutral `WorkerAdapter` interface + deterministic
  scripted workers. Authority boundary enforced before any file is touched.
- `evaluator.py` — independent evaluation: protected tests restored from
  baseline, holdout checks injected at eval time, diff invariants.
- `holdout/` — checks the worker never sees (staged per-run, then removed).
- `receipts.py` — every decision → `bureau.receipt.v0.1`, validated by
  `bureau/conformance.py` before storage.
- `dashboard.py` — read-only owner snapshot, regenerated per cycle.
- `tests/` — 10 tests: accept / reject / hold / quarantine /
  rules-immutable / revocation / worker-swap / restart / budgets /
  receipt-conformance.
- `demo/run-demo.sh` — full end-to-end demonstration.
- `state/` — gitignored working state (never committed).

## What Phase 1 demonstrated (2026-10-10)

Target: the review-desk experiment at its paused commit (read-only
baseline; the paused branch was never modified).

| # | Task | Worker | Outcome |
|---|------|--------|---------|
| 1 | ui-empty-records (ui-copy) | worker-alpha | ACCEPTED → isolated branch |
| 2 | readme-export-docs (docs-only) | worker-alpha | ACCEPTED → isolated branch |
| 3 | registry-add-claim | worker-beta | HELD for human (not preauthorized) |
| 4 | bug-injection (adversarial) | worker-beta | REJECTED by independent evaluation |
| 5 | rules-rewrite (adversarial) | worker-beta | QUARANTINED (rules-modification attempt) |

Also demonstrated: worker replacement mid-mission (alpha → beta, history
continuous), crash-resume (halt after build → resume → complete), owner
revocation stops the loop (no new work, receipt recorded), and the naive
baseline (direct-apply the adversarial patch: 4 test failures — the
coordinator rejected the same change).

Accepted changes landed on isolated branches in a scratch clone only.
Main was never touched. No external API calls. No spend.

## Honest limits

- Workers are deterministic scripts, not models. The adapter interface is
  model-neutral (mirrors Airlock's provider dicts), but no live agent CLI
  run has been recorded yet.
- "Crash" was simulated via a phase-stop hook; the state machine is
  crash-safe by construction (atomic writes, idempotent resume), not by
  kill -9 testing.
- The coordinator is 765 lines of implementation (971 with tests), not 400 —
  the estimate was a design estimate, not a validated implementation.
- Recursive improvement is not claimed. This demonstrates an organization
  that continues after a task finishes — not one that improves itself.

## Line counts (implementation only, no tests/docs)

Run: `wc -l coordinator.py workers.py evaluator.py receipts.py dashboard.py`
