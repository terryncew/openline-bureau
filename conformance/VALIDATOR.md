# Validator documentation

The validator is `bureau/conformance.py` (library) with two CLIs:

- `python3 -m bureau.validate receipt.json [--json] [--claim CLAIM]`
  — one receipt, human or machine output, explicit claim queries.
- `python3 -m bureau.conformance <path> [--json]`
  — a file or directory, full conformance report.

No network, no model calls, no external dependencies. Deterministic:
the same file always produces the same verdict.

## Validation levels

| Level | Meaning |
|---|---|
| `VALID` | Structurally conforms (required fields, vocabulary, internal consistency) **and** supports at least one declared claim. |
| `CONFORMANT_NO_CLAIMS` | Structurally valid but supports zero claims. Missing optional evidence is not a defect — it is reported as NOT ESTABLISHED. |
| `INVALID` | Fails a required structural or consistency rule. Listed problems name the exact failure. |
| `UNSUPPORTED_VERSION` | Speaks the `bureau.receipt.` family prefix but is not the supported version. Not the same as invalid. |
| `UNSUPPORTED_CLAIM` | Claim-check outcome (see below): the receipt is fine but cannot support the requested claim. |

Structural rules (each produces a named problem, never a silent drop):

- `receipt_version`, `receipt_id`, `timestamp`, `receiver` are required
  and non-empty; `timestamp` must parse as ISO-8601.
- `decision.outcome` ∈ {COMMIT, DENY, QUARANTINE, STOPPED, OBSERVED}.
- `authority.status` ∈ {ACTIVE, REVOKED, SUPERSEDED, NARROWED,
  EXPIRED, NO_MANDATE, UNKNOWN}.
- `effect.observed` ∈ {true, false, null}.
- `parents` is a list of strings when present; `extensions` is an object
  when present.
- Temporal consistency: `authority.revoked_at` must not precede
  `authority.issued_at`; a receipt timestamp must not precede
  `authority.issued_at` while the authority claims to be ACTIVE.
  Contradictions are INVALID, not warnings.

Warnings (advisory; never invalidate):

- missing provenance section or `provenance.system`;
- **no signature**: structural conformance only — the receipt is NOT
  cryptographically authenticated;
- no hash binding;
- decision recorded without effect evidence (outcome unknown, not assumed);
- revocation timestamp is receiver-external and unsigned;
- unknown top-level fields (preserved, listed, not rejected).

## Claim checking (`--claim`)

```
python3 -m bureau.validate receipt.json --claim POST_REVOCATION_ATTEMPT_OBSERVED
```

Returns `SUPPORTED` (exit 0) or `NOT SUPPORTED` / `UNSUPPORTED_CLAIM`
(exit 1) plus the exact missing evidence:

```
CLAIM:   POST_REVOCATION_ATTEMPT_OBSERVED
VERDICT: UNSUPPORTED_CLAIM

Missing evidence:
  - authority.revoked_at or authority.status == REVOKED
  - timestamp >= authority.revoked_at (receipt predates revocation)
```

Claim checking matters more than schema validation: a schema-valid
receipt that cannot prove what you need is the common case, and the
validator names the gap precisely.

## Read-only guarantee

Both CLIs open sources read-only. The validator snapshots each file's
(mtime, size) before reading and verifies it after; any modification —
which cannot happen, but is checked anyway — fails loudly. Every report
ends with `source files modified: 0`. The Bureau ingest path keeps the
same guarantee.

## Exit codes

`bureau.validate`: 0 = VALID, CONFORMANT_NO_CLAIMS, or SUPPORTED claim;
1 = unsupported claim / internal read-modify anomaly; 2 = INVALID,
UNSUPPORTED_VERSION, UNREADABLE, or unknown claim name.

`bureau.conformance`: 0 always (report is the product); 1 only if a
source file was somehow modified during the scan.
