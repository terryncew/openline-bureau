# Public evidence bundle: sentry-trajectory-001

**Terminal classification:** `PASS_SENTRY_TRAJECTORY_001_PROCESS_CHALLENGE`

**Question tested:** Can SENTRY watch the trajectory of autonomous work -- not merely individual consequential actions -- and challenge a degraded process before it produces a consequential action, while remaining non-sovereign?

This bundle lets a stranger inspect what the frozen evidence establishes without trusting prose and without rerunning the experiment. The Bureau validates the structure of the evidence projections and the bounded claims they support -- it does not re-adjudicate the scientific result. The source experiment records remain authoritative.

## Layout

- `manifest.json` -- machine-readable bundle record (classification, digests, receipt list, limitations).
- `source/` -- exact frozen source bytes, never edited.
- `preregistration/ref.json` -- immutable binding to the frozen preregistration.
- `result/ref.json` -- immutable binding to the terminal result record.
- `receipts/` -- derived `bureau.receipt.v0.1` projections, each visibly marked as derived.
- `hashes.json` -- SHA-256 of every bundle file.

## Clock

Both receipts share the scientific-contact timestamp 2026-09-18T08:02:33.034147+00:00: one guardian invocation judged both trajectories.

## Cryptographic authenticity

No signatures. SHA-256 bindings (TERMINAL_FREEZE + INTEGRITY_MANIFEST.json); recomputed digests match.
 Structural conformance is not authenticity: the validator reports signatures as absent, preserved, or unverified -- never as verified unless verified.

## Known limitations

- One frozen matched trajectory pair. Do not generalize to universal drift detection.
- Watcher reason strings are the model's own assertions about drift, recorded byte-for-byte; nothing external verifies the semantic judgment itself.
- No effect evidence recorded: effects unknown.

## Validate

From the Bureau repo root:

    python3 -m bureau.evidence public-evidence/sentry-trajectory-001

Read-only, deterministic, stdlib-only, no network. Returns nonzero on any structural, hash, or conformance failure.
