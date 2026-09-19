# OpenLine Bureau

**What does the receipt history say actually happened?**

An evidence ledger / assurance prototype for autonomous-system consequence
receipts. It normalizes receipts from independent OpenLine controls
(Wallet, Receipt Gate, Airlock, experiment evidence) into one inspectable
record and answers operator questions from receipts — not from vibes.

## What it is

- A normalized, provenance-preserving store of consequence receipts.
- Five analyst views: System Overview, Event/Receipt Ledger,
  Authority Timeline, Incident/Recovery Record, Evidence Coverage.
- Disciplined metrics: every number carries its definition, numerator,
  denominator, source events, and an honest "not measurable" state.
- A deterministic program. No LLM inference, no auth, no billing,
  no distributed infrastructure. Python stdlib + SQLite + vanilla JS.

## What it is not

- Not an AI trust score. There is no `TRUST = 87` anywhere in this system,
  and there will not be until such a score has independently earned meaning.
- Not an agent.
- Not a replacement for receiver enforcement.
- Not proof that unobserved actions did not happen. Absence of a receipt
  is not evidence of absence of action.

## Core principle

**The Bureau reports what receivers can prove happened at consequence
boundaries.** Everything else is marked unknown.

## Quick start

```bash
cd openline-bureau

# 1. Validate the public evidence bundles (read-only, deterministic, stdlib-only)
python3 -m bureau.evidence public-evidence

# 2. Build and serve the synthetic demo database (marked SYNTHETIC DEMO DATA)
python3 -m bureau.demo --db data/demo.db
python3 -m bureau.server --db data/demo.db --port 8765
# open http://127.0.0.1:8765/
```

## Ingesting real evidence (local, read-only)

```bash
# A directory of receipt JSON files; sources are never mutated.
python3 -m bureau.ingest /path/to/receipts --db data/local.db \
    --source-repo terryncew/openline-wallet --source-commit <sha>
```

Supported formats (auto-detected):

| Adapter | Source format |
|---|---|
| `wallet_effect_receipt` | `openline.wallet.effect_receipt.v1` — consequence receipts (STOPPED/COMMITTED, effect_applied, reason codes) |
| `gate_action_receipt` | `openline.gate.action_receipt.v1` — receiver decisions (ALLOWED/STOPPED) |
| `wallet_trace` | Wallet closure-set trace events (grant_admitted, revocation_signed, set_closure_verified, …) |
| `experiment_record` | `openline.bureau.experiment_record.v1` — curated frozen-experiment evidence (sentry decisions, false holds, apparatus notes) |
| `canonical_dump` | `openline.bureau.canonical.v1` — pre-normalized records (used by the synthetic demo) |
| `external_receipt` | `bureau.receipt.v0.1` — minimal consequence receipts from a receiver that does **not** run OpenLine (see `conformance/`) |

### Conformance Kit (external receivers)

A system that does not run OpenLine can still produce evidence the
Bureau can validate, normalize, and report honestly. Start at
`conformance/README.md`:

```bash
# validate one receipt / check one claim / report over a directory
python3 -m bureau.validate conformance/examples/02-post-revocation-attempt.json
python3 -m bureau.validate conformance/examples/05-partial-receipt.json \
  --claim REVOCATION_ENFORCEMENT_OBSERVED
python3 -m bureau.conformance conformance/examples/

# see what an independent receiver emits (no OpenLine imports, stdlib only)
python3 examples/reference_receiver.py --out /tmp/ext-receipts
python3 -m bureau.ingest /tmp/ext-receipts --db data/external.db
```

The validator answers what a receipt proves (VALID / INCOMPLETE /
UNSUPPORTED CLAIM / INVALID) without pretending an unfamiliar system is
an OpenLine system. Structural conformance is kept separate from
cryptographic authenticity: unsigned receipts are structurally valid and
reported as unauthenticated. Ingested external receipts show SUPPORTED /
NOT ESTABLISHED claim panels in the receipt detail view.

Payloads no adapter recognizes fail visibly as `UNSUPPORTED_RECEIPT_FORMAT`
— listed, never silently ignored. Sources are opened read-only; the
summary always ends with `source files modified: 0`.

Example:

```
python3 -m bureau.ingest /path/to/receipts --db data/local.db
files_seen=22 inserted=17 duplicate=3 invalid=0 adapters=['wallet_effect_receipt']
---
Bureau ingest summary
  receipts ingested:    17
  duplicates skipped:   3
  unsupported formats:  2
  unreadable files:     0
  invalid records:      0
  adapters used:        wallet_effect_receipt
  source files modified: 0
UNSUPPORTED_RECEIPT_FORMAT: /path/to/receipts/a.json
UNSUPPORTED_RECEIPT_FORMAT: /path/to/receipts/b.json
```

Every visible metric carries its definition, numerator, and denominator;
every metric value links to the exact ledger rows it was computed from.
Rates that cannot be established from the loaded receipts show
**NOT MEASURABLE FROM AVAILABLE RECEIPTS** — never zero.

## The five views

1. **System Overview** — evidence-backed counts (committed/refused/quarantined
   consequences, revocations, replays, recoveries, false holds, handoffs…).
   Every number links to the underlying ledger rows. Rates show their
   denominators or a "not measurable" reason.
2. **Event / Receipt Ledger** — chronological, filterable (actor, decision,
   event type, experiment, system, authority state, time). Selecting a
   receipt shows normalized fields, provenance, raw payload, and
   parent/child ancestry.
3. **Authority Timeline** — mandate issued → actions → revocation →
   post-revocation attempts → replacement. Makes "was this action still
   authorized when the consequence occurred?" visually obvious.
4. **Incident / Recovery Record** — challenge → stop → revocation →
   recovery proposal → successor authorization → resumed consequence,
   grouped per experiment. Effect-observed vs unknown is explicit.
5. **Evidence Coverage** — the most important screen: what the Bureau can
   and cannot know, in exactly three epistemic states. OBSERVED: current
   authority at receiver, receiver decision, effect confirmation (where a
   receipt exists), provenance, temporal ordering. DERIVED: revocation
   propagation lag, measured from two observed timestamps — where no pair
   exists it is UNKNOWN from these receipts, never estimated. UNKNOWN:
   agent hidden intent, actions through credentials outside the receiver,
   uninstrumented actuator behavior, and the absence of unobserved
   actions (absence of a receipt is not evidence of absence of action).

## Metric discipline

- `stale_authority_attempt_rate` — stale attempts over protected actions
  with observable authority standing. Not computed when the denominator
  cannot be established.
- `revocation_propagation_lag` — revocation observed → first confirmed
  enforcement, only where both timestamps exist. Pairs missing either
  are excluded, never estimated.
- `false_hold_rate` — legitimate actions stopped over challenge cases with
  independently established ground truth. Legitimacy is never inferred
  from later allowance.

## Synthetic demo data

`bureau/demo.py` generates 28 records telling one coherent walkthrough
story, prominently bannered **SYNTHETIC DEMO DATA** in the UI and in the
file:

1. `worker-a` receives authority.
2. `worker-a` performs legitimate actions (proposed → committed, observed).
3. `worker-a` builds a checkpoint artifact at a consequence boundary.
4. The owner revokes `worker-a`.
5. `worker-a` attempts another protected action; the receiver refuses it
   as `MANDATE_REVOKED` (refusal links back to the revocation receipt).
6. The already-created `worker-a` artifact is presented at a second
   receiver later and is refused because the origin's standing is stale
   (ancestry links to both the artifact's creation and the revocation).
7. Successor `worker-b` receives fresh authority.
8. `worker-b` continues from the accepted checkpoint and resumes
   legitimate work (effect observed).

A second thread (`worker-c`) adds the incident/coverage material: a
reconciled challenge, a false hold, a successful and a failed recovery,
unresolved cases, and a narrowed mandate.

## Tests

```bash
python3 -m unittest tests.test_bureau
```

42 tests: schema validation, store round-trip/dedup/filters/ancestry,
all five adapters, provenance preservation, unsupported-format behavior,
metric measurability conditions, ingest CLI (incl. summary block and
read-only sources), the canonical demo story (sequence, stale refusal,
delayed artifact ancestry, successor continuation), metric→ledger
drilldown parity, unknown/not-measurable behavior, every HTTP endpoint,
and a static frontend syntax check (`node --check ui/app.js`).

## Project status

Prototype. Single-user, local operation. The product question it exists
to explore: can receipts from independent OpenLine controls be normalized
into a record that is materially useful to an operator, insurer,
procurement team, auditor, or platform owner? Technical coherence is
demonstrable here; **commercial demand is not established** — that
requires external evidence, which this prototype does not manufacture.
