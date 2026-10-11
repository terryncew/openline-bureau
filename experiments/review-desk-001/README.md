# REVIEW-DESK-001 — local-first public research review desk (experiment)

**Status: experiment on a feature branch. Not merged. Nothing here publishes anything.**

## Goal

Foundation for an automated public research review system: an independent
researcher can paste a public comment or technical objection, and a
verifiable process drafts a review from an explicit evidence registry —
while a human keeps control over every public response and consequential
decision.

Principle: **Criticism is welcome. Claims require evidence. Uncertainty
stays visible.**

## The workflow

```
intake (paste comment) → evidence (registry lookup) → review (draft)
    → record (local JSON) → human approval (local only, never published)
```

The engine (`review.py`) is deterministic and stdlib-only. It classifies
each comment into one of four buckets:

| Classification | Meaning |
|---|---|
| `ADDRESSED` | Matches a documented objection already resolved by registry evidence. False premises are corrected, not agreed with. |
| `TESTABLE` | A new, falsifiable technical objection. Recorded as a challenge with an explicit proposed falsifier before any response. |
| `UNRESOLVABLE` | Concerns matters the evidence cannot resolve (real-world occurrence, adoption, intent). Answer: `UNKNOWN`. |
| `NO_CLAIM` | No actionable technical claim. No response required. |

Every draft response is labeled a draft, cites only registry references
(never invented), and says `UNKNOWN` where evidence is missing.
Instruction-like language in a pasted comment is treated as data and
disregarded — the engine never obeys it, never accuses, never
psychoanalyzes.

## Run it

```sh
cd experiments/review-desk-001
python3 server.py            # local only: http://127.0.0.1:8771
python3 -m unittest discover -s tests
```

Records land in `records/` (gitignored — local working state, never
committed). The **Export** button produces the machine-readable review
record, with `human_statements`, `automated_checks`, `test_outcomes`, and
`human_approvals` kept in separate sections.

## What this reuses from the Bureau

- The claim-taxonomy concept (`conformance/claims.md`): every registry
  claim lists its minimum evidence and known limitations.
- The stdlib-only server + plain HTML/CSS/JS UI pattern (`bureau/server.py`, `ui/`).
- The evidence-bundle idea: references point at exact tests, specs, and docs.

## Boundaries (enforced by tests)

- No frozen interop spec or test vector is modified or depended on for
  correctness of this experiment.
- No automatic publishing, no replies sent anywhere, no social scraping.
- No accusations of bad faith, no psychological characterization.
- No personal data or psychology documents in the repo (`records/` is gitignored).
- No paid APIs, hosting, or external services. Localhost only.

## What remains manual / what automation would need

See REPORT.md.
