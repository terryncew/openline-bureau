# Public evidence bundle: trust-handoff-001

**Terminal classification:** `PASS_TRUST_HANDOFF_001_DEFERRED_AUTHORITY_REVOKED`

**Question tested:** Can a consequence artifact created while Worker A was authorized produce a new receiver-controlled effect after A is revoked, either directly or after transformation by trusted intermediaries?

This bundle lets a stranger inspect what the frozen evidence establishes without trusting prose and without rerunning the experiment. The Bureau validates the structure of the evidence projections and the bounded claims they support -- it does not re-adjudicate the scientific result. The source experiment records remain authoritative.

## Layout

- `manifest.json` -- machine-readable bundle record (classification, digests, receipt list, limitations).
- `source/` -- exact frozen source bytes, never edited.
- `preregistration/ref.json` -- immutable binding to the frozen preregistration.
- `result/ref.json` -- immutable binding to the terminal result record.
- `receipts/` -- derived `bureau.receipt.v0.1` projections, each visibly marked as derived.
- `hashes.json` -- SHA-256 of every bundle file.

## Clock

Frozen deterministic clock: T*10 seconds after 2026-09-18T08:00:00Z, verified against the wallet event log anchors (T0 mandate-a issued, T4 mandate-a revoked, T7 mandate-d issued). Timestamps are scenario time, not wall-clock.

## Cryptographic authenticity

No signatures. SHA-256 digests bind the frozen artifacts (recorded in RESULT.json / TERMINAL_FREEZE.md and recomputed here). Model calls: 0; spend: $0.00.
 Structural conformance is not authenticity: the validator reports signatures as absent, preserved, or unverified -- never as verified unless verified.

## Known limitations

- Timestamps are a deterministic frozen clock (BASE 2026-09-18T08:00:00Z), not third-party attested wall-clock.
- The Y-002 stripped arm was unscored (sealed expectation ORIGIN_UNBOUND vs observed ARTIFACT_TAMPERED); it does not affect the verdict.
- The th-004-naive-hole receipt records the demonstrated hole in the naive composition; it is evidence of the bug, not of success.
- Claim ceiling is narrow: one bounded deferred-execution fixture. No production security certification.

## Validate

From the Bureau repo root:

    python3 -m bureau.evidence public-evidence/trust-handoff-001

Read-only, deterministic, stdlib-only, no network. Returns nonzero on any structural, hash, or conformance failure.
