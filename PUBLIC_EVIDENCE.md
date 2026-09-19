# OpenLine Bureau — Public Evidence Bundles v0.1

A stranger should be able to inspect an OpenLine experimental claim without
trusting anyone's prose and without rerunning the original experiment.

Each bundle under `public-evidence/<experiment-id>/` contains:

- **exact frozen source bytes** (`source/`), never edited, bound by SHA-256;
- **derived `bureau.receipt.v0.1` projections** (`receipts/`), each visibly
  marked as derived — the historical systems did not emit Bureau receipts;
- a **manifest** stating the terminal classification, what is established,
  what is not, and the known limitations.

**What the Bureau validates:** the structure of the evidence projections and
the bounded claims they support. **What it does not:** re-adjudicate the
scientific result. Source experiment records remain authoritative. A
structurally valid receipt never changes a terminal classification.

Failures are displayed with the same prominence as passes. A FAIL in the
terminal column is a first-class scientific result, not a defect in the
bundle.

## One-command validation

From the Bureau repo root (read-only, deterministic, stdlib-only, no
network; nonzero exit on any structural, hash, or conformance failure):

    python3 -m bureau.evidence public-evidence

Or a single bundle:

    python3 -m bureau.evidence public-evidence/trust-handoff-001

Machine-readable:

    python3 -m bureau.evidence public-evidence --json

## Bundles

| Experiment | Terminal standing | Bundle validation | Bureau claims evidenced from derived receipts | Frozen source |
|---|---|---|---|---|
| trust-handoff-001 | PASS_TRUST_HANDOFF_001_DEFERRED_AUTHORITY_REVOKED | PASS | action attempt, receiver decision, effect, effect absence, current authority, revocation, post-revocation attempt, revocation enforcement, successor authority, provenance chain, stale-artifact attempt, recovery continuation | `public-evidence/trust-handoff-001/source/` |
| sentry-live-001 | PASS_SENTRY_LIVE_001_GRACEFUL_DEGRADATION_OBSERVED | PASS | action attempt, receiver decision | `public-evidence/sentry-live-001/source/` |
| sentry-trajectory-001 | PASS_SENTRY_TRAJECTORY_001_PROCESS_CHALLENGE | PASS | action attempt, receiver decision | `public-evidence/sentry-trajectory-001/source/` |
| fixed-authority-scale-001 | FAIL_FIXED_AUTHORITY_SCALE_001_COORDINATION_TAX | PASS | action attempt, receiver decision, effect, current authority | `public-evidence/fixed-authority-scale-001/source/` — see historical-anomaly note below |
| incident-replay-001 | FAIL_INCIDENT_REPLAY_001_FALSE_HOLD | PASS | action attempt, receiver decision | `public-evidence/incident-replay-001/source/` |
| containment-003 | FAIL_CONTAINMENT_003_DEFENDER_USELESS | PASS | action attempt, receiver decision, effect, current authority, revocation, post-revocation attempt, successor authority, provenance chain, recovery continuation | `public-evidence/containment-003/source/` |
| recovery-001 | PASS_RECOVERY_001_EXECUTABLE_HANDOFF_PROPOSAL | PASS | action attempt, receiver decision, current authority | `public-evidence/recovery-001/source/` |

Each bundle's `source/` directory carries the frozen bytes directly; no
original local directory is needed (or resolvable) for validation. The
original experiments were frozen in a private development workspace; the
bundle contents — not the original directory paths — are what the
validator checks.

Validation result at build time: **7/7 bundles PASS**, 42/42 derived
receipts conform, 0 source bytes modified.

## Reading guide

- Start with a bundle's `README.md`, then `manifest.json`
  (`terminal_classification`, `known_limitations`, `authenticity`).
- `source/` holds the frozen bytes; `hashes.json` binds every bundle file
  by SHA-256.
- The validator confirms the manifest's terminal classification appears
  verbatim in the bound terminal-result artifact — a FAIL relabeled PASS
  fails validation.
- Cryptographic authenticity: no signatures are present in any bundle.
  SHA-256 digests are integrity bindings, not authenticity proofs. The
  validator reports this explicitly.

## Preserved historical anomaly: fixed-authority-scale-001

The frozen `RESULT.md` inside `public-evidence/fixed-authority-scale-001/source/`
contains a self-recorded SHA-256 digest that does **not** reproduce from the
present frozen bytes. The evidence layer preserves this discrepancy rather
than repairing it: the original bytes are kept exactly as frozen, and the
bundle manifest's `known_limitations` records that the historical digest does
not reproduce. This is an example of the layer's rule — source bytes are
sacred, discrepancies are surfaced, not silently fixed. It does not affect
the bundle's structural validity or the terminal classification
(`FAIL_FIXED_AUTHORITY_SCALE_001_COORDINATION_TAX`), which is preserved
verbatim.

## What the bundles do not claim

Independent replication, third-party interoperability, demand,
standardization, cryptographic authenticity where not verified, or
scientific truth beyond the frozen source results.
