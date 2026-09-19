# OpenLine Bureau Conformance Kit v0.1

An external receiver — a system that does **not** run OpenLine — can produce
a minimal consequence receipt that the Bureau validates, normalizes, and
reports honestly. This directory is the contract for that exchange.

## The deal

The Bureau does not require you to adopt OpenLine internals. It requires
only enough evidence to support a bounded consequence claim. The question
is not "did you implement our architecture?" but "what can your receiver
prove happened?"

The Bureau can say four things about your receipts, and only these:

- **VALID EVIDENCE** — structurally conforms and supports at least one claim
- **INCOMPLETE EVIDENCE** — structurally valid but supports no claim yet
- **UNSUPPORTED CLAIM** — valid receipt, cannot support the claim requested
- **INVALID RECEIPT** — fails a required structural or consistency rule

Unknown stays unknown. A receipt proving `decision = DENY` without effect
evidence supports `RECEIVER_DECISION_OBSERVED` and nothing more. The Bureau
will not claim no effect occurred, that revocation propagated, or that an
actor was permitted — unless the receipt carries that evidence.

## Contents

| File | What it is |
|---|---|
| `receipt.schema.json` | The minimal external receipt format (`bureau.receipt.v0.1`) |
| `claims.md` | The claim taxonomy: what each claim means and the exact evidence it requires |
| `VALIDATOR.md` | How validation works: levels, rules, CLI usage, exit codes |
| `integration-guide.md` | How to emit conformant receipts from your own receiver |
| `examples/` | Ten worked receipts covering the conformance space |

## Try it in two minutes

```bash
cd /path/to/openline-bureau

# 1. Validate one receipt (human-readable)
python3 -m bureau.validate conformance/examples/02-post-revocation-attempt.json

# 2. Machine-readable
python3 -m bureau.validate conformance/examples/02-post-revocation-attempt.json --json

# 3. Ask about one claim; get exact missing evidence on failure
python3 -m bureau.validate conformance/examples/05-partial-receipt.json \
  --claim REVOCATION_ENFORCEMENT_OBSERVED

# 4. Report over a whole directory (read-only; sources never modified)
python3 -m bureau.conformance conformance/examples/
python3 -m bureau.conformance conformance/examples/ --json

# 5. See what an independent receiver emits (no OpenLine imports)
python3 examples/reference_receiver.py --out /tmp/ext-receipts
python3 -m bureau.conformance /tmp/ext-receipts
```

## Structural conformance ≠ authenticity

A structurally valid receipt is **not** automatically authenticated.
Signatures are optional in v0.1. When absent, the validator says so
explicitly; when present, they are preserved and exposed. The Bureau never
silently trusts a self-asserted `receiver` or `provenance.system` field.

## Status

v0.1 is an interoperability primitive, not a certification program. There
is no trust score, no authority that stamps receivers "compliant", no
blockchain, no CA. The schema is namespaced and extensible (see
`integration-guide.md`) so later adapters can map Action Records, Consent
Receipts, Verifiable Intent, payment mandates, and agent identity
credentials without changing the core.
