# Public evidence bundle: fixed-authority-scale-001

**Terminal classification:** `FAIL_FIXED_AUTHORITY_SCALE_001_COORDINATION_TAX`

**Question tested:** Can adding agents increase verified capability while the receiver-authorized consequence ceiling and the total inference budget stay fixed?

This bundle lets a stranger inspect what the frozen evidence establishes without trusting prose and without rerunning the experiment. The Bureau validates the structure of the evidence projections and the bounded claims they support -- it does not re-adjudicate the scientific result. The source experiment records remain authoritative.

## Layout

- `manifest.json` -- machine-readable bundle record (classification, digests, receipt list, limitations).
- `source/` -- exact frozen source bytes, never edited.
- `preregistration/ref.json` -- immutable binding to the frozen preregistration.
- `result/ref.json` -- immutable binding to the terminal result record.
- `receipts/` -- derived `bureau.receipt.v0.1` projections, each visibly marked as derived.
- `hashes.json` -- SHA-256 of every bundle file.

## Clock

All nine receipts share contact_ts 2026-09-18T10:06:03-0700, identical in every run row. Per-run wall-clock beyond latency was not recorded.

## Cryptographic authenticity

No signatures. PRECONTACT_SEAL.md binds the frozen inputs by SHA-256; recomputed digests of the sealed inputs match.
 Structural conformance is not authenticity: the validator reports signatures as absent, preserved, or unverified -- never as verified unless verified.

## Known limitations

- RESULT.md's self-recorded SHA-256 digest does not reproduce from the present bytes (plausible small post-digest edit; all other digests verify, and every number reconciles against runs/runs.jsonl). The bundle records the digest of the bytes as copied; the mismatch against the frozen document's claim is flagged, not hidden.
- The mechanism claim (final role did not emit a submittable patch block) is not inspectable: raw role output texts were deliberately not retained (recorded as a diagnostic limitation in RESULT.md itself).
- The comparative FAIL (SOLO 3/3 vs PAIR 2/3 vs TEAM 2/3) is carried in the result layer; receipts record per-run evidence only. Bureau claims do not restate the terminal verdict.
- No per-run pytest verifier output artifacts exist; verifier acceptance is attested by the driver-recorded status field.

## Validate

From the Bureau repo root:

    python3 -m bureau.evidence public-evidence/fixed-authority-scale-001

Read-only, deterministic, stdlib-only, no network. Returns nonzero on any structural, hash, or conformance failure.
