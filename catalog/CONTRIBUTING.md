# Public catalog contribution format

Start with the [public beta contribution guide](../docs/beta/CONTRIBUTING.md).
It describes permissions, review, independent evaluation, immutable history and
the conditions that must be met before accepting outside contributions.

The public catalog starts empty. Records under `fixtures/` are explicitly
synthetic and appear only in a separate opt-in fixture build. No real contributor,
customer, independently reproduced result or payment is represented by them.

Copy `templates/capability.json`, `templates/worker.json` or
`templates/evaluation.json` into the corresponding `submissions/` directory.
Replace every placeholder with accurate information. Keep `worker_id` null when
an evaluation tests the capability without observing a specific worker execution.
The shapes are defined in `schemas/`; the data-only compiler additionally checks
URLs, sizes, hashes, publication permission, role separation and references.

```sh
python -m bureau.catalog validate --source catalog --pending
python -m bureau.catalog prepare-review --source catalog
python -m bureau.catalog build --source catalog --out /tmp/openline-beta/catalog/v1/index.json
python -m bureau.catalog build --source catalog --fixtures --out /tmp/openline-beta/synthetic/v1/index.json
```

Validation and digest preparation do not approve or publish contributions.
Maintainers protect `reviewed.json` outside the contributed records; reviewed
GitHub authorship is an explicit human attestation, not authentication by the
compiler. An approval binds the exact record bytes and every referenced evidence
file by SHA-256. New versions preserve old files and link to exact earlier hashes.
Attribution metadata does not establish legal ownership or license rights.

Supporting evidence lives under `evidence/` and is referenced by relative JSON
path, exact byte hash, format and explicit `public_release` permission. The accepted
public profiles are `bureau.receipt.v0.1`, signed Wallet
`openline.wallet.effect_receipt.v1` and `openline.gate.action_receipt.v1`,
`openline.catalog.signed-receipt.v1` (a Bureau receipt signed with Wallet's
Ed25519 envelope), and `openline.exchange.selected-evidence.v1`. Exchange selected
evidence describes simulated exchange records; it cannot demonstrate real payment.
The original Bureau protocol remains unchanged; the public catalog accepts a
restricted typed profile and namespaced extensions. A signature authenticates a
key and bytes, not a useful outcome, legal identity or authorization to publish.

Task-specific sample denominators, all case results, failures, selection method,
runtime context, limitations and conflicts stay visible. Capability evidence and
explicit worker execution evidence have separate summaries. A separate reviewed
GitHub author supports a reported independent evaluation; account control and
organizational independence still need human review. A reproduced result requires
a trusted maintainer report binding the exact evaluation hash, case-result hash,
sample, method and environment, with a reproducer distinct from the evaluator and
the capability/worker publishers. Contributors cannot add a `verified` flag.

The compiled `openline.catalog.v1` JSON is deterministic. Its sibling
`artifacts.json` lists the exact hashes of approved original records, receipts,
reproduction reports and schemas. Evidence `source_url` and record `record_url`
are relative to the compiled JSON directory. Serve only the reviewed build;
never serve the source checkout, private databases or unreviewed evidence.
