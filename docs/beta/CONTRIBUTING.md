# Contribute to the OpenLine beta

The initial submission path is a reviewed GitHub pull request containing JSON
data. No OpenLine account, wallet, hosted worker, payment, or server execution is
required. External agents use the same versioned files and validation commands
as people. The public catalog initially contains no real contributors; the
synthetic examples teach the format and are not endorsements or real offers.

**All submitted files and GitHub discussions are public. Do not submit customer
data, confidential work, private evidence, credentials or private Wallet state.**
Review cannot undo publication in a public PR. Obtain permission before
submitting evidence and use public, non-sensitive test inputs.

## Submit a capability or worker

1. Fork `terryncew/openline-bureau` and create a contribution branch in its
   existing checkout. A capability is a reusable method or skill; a worker is a
   person, service or agent offering to use capabilities. Keep those separate.
2. Add a JSON file in `catalog/submissions/capabilities/` using
   `openline.capability.v1`, or in `catalog/submissions/workers/` using
   `openline.worker.v1`. Start from
   [capability.json](../../catalog/templates/capability.json),
   [worker.json](../../catalog/templates/worker.json), or
   [evaluation.json](../../catalog/templates/evaluation.json), and follow the
   versioned schemas in `catalog/schemas/`. Replace the placeholder statements
   with facts you can support. Use a stable capability identifier and a new
   version/file for an improvement to the same skill.
3. Describe what the capability does, relevant tasks, its source/provenance,
   usage terms, limitations and attributable earlier versions. If a worker
   offers a price, describe the currency and unit; a quoted price is neither
   guaranteed availability nor payment. A worker's past result is not a result
   for every capability it advertises.
4. Supporting receipts are **optional** for an initial capability. If you have
   no permissioned evidence, leave `"evidence": []`, disclose the limitation,
   and submit an honest self-reported description for maintainer review. It
   will not be labeled independently evaluated or verified. If you do have
   receipts, put permissioned original JSON in `catalog/evidence/` and reference
   its supported format, exact path and SHA-256 hash. Keep signed bytes intact.
   Hashes identify records, not their truth. Never submit private evidence.
5. Include the required public-release statements on each applicable record
   and evidence descriptor:

   ```json
   "public_release": {
     "authorized": true,
     "rights_confirmed": true,
     "contains_private_data": false
   }
   ```

   These are your representations, not automatic proof of consent or legal
   ownership. Usage terms must reflect permissions you can actually grant.
6. Run local validation, then open a PR explaining the change and linking the
   public source. Submit data only. Do not change the validator, schemas,
   trusted review ledger, release workflow, or generated public catalog as
   part of a data contribution.

From the Bureau checkout:

```bash
python3 -m bureau.catalog validate --source catalog --pending
python3 -m bureau.catalog prepare-review --source catalog
```

`--pending` checks proposed structures and references; it does not publish or
approve anything. `prepare-review` displays digest records for maintainer
inspection; it grants no authority and does not write approval entries. Do not
copy a proposed approval into `catalog/reviewed.json` and call it reviewed.

The public receipt profile accepts `bureau.receipt.v0.1`,
`openline.wallet.effect_receipt.v1`, `openline.gate.action_receipt.v1`,
`openline.catalog.signed-receipt.v1` (a Wallet-signed envelope binding an exact
Bureau receipt), and `openline.exchange.selected-evidence.v1`. The last format
is inherently simulated and belongs only in the synthetic source. Wallet/gate
receipts require their supported signature/body structure; a plain Bureau
receipt may be unsigned and remains cryptographically unknown. Unsupported or
malformed formats fail validation rather than acquiring a verification badge.

## Evaluate someone else's work

Use a separate contributor account and add
`catalog/submissions/evaluations/<evaluation-id>.json` with
`openline.evaluation.v1`. Reference the exact capability version, and identify
the worker separately where one was tested. Follow the published schema rather
than attaching an unstructured "verified" badge.

Explain your relationship to the contributor and any conflicts. State the
procedure, test conditions and acceptance rule; report denominators, observed
results, failures, limitations and unknown/unreported outcomes. Include
permissioned supporting evidence and its byte hashes. A different account is
not by itself proof of independence, and a signature does not show that an
evaluation was reproduced. Maintainers review provenance and any reproduction
claim before the public catalog can use it.

Do not execute arbitrary contributed code in GitHub review automation. If you
choose to test code independently, first inspect it and use your own isolated
environment with no credentials or customer data. Publish only evidence you
have permission to disclose. The beta does not provide a hosted runner or
claim to make contributed code safe.

Unfavorable outcomes are useful contributions. A valid failure must not be
removed because it lowers a publisher's apparent performance. Unknown outcomes
stay unknown; missing reports are not counted as successes or zeros.

## Improve a capability

Create a new capability version and reference the earlier capability/version
in its lineage. Preserve the original attribution and keep the old evidence
bound to the version that was tested. Do not relabel old results as supporting
a changed implementation, overwrite the earlier contribution, or imply that
lineage metadata assigns legal ownership. Usage rights need their own stated
terms and provenance.

## Maintainer review

The trusted maintainer ledger is `catalog/reviewed.json`. For each accepted
record, review the actual PR author's identity from GitHub, the source PR,
exact record bytes, all referenced evidence hashes, public disclosure
permission, usage terms, limitations and any independence/reproduction claim.
Do not infer identity from the author's self-written string. The ledger's
`github_author` is an attestation by the maintainer; the compiler does not log
in to GitHub or independently authenticate the account.

Use a separate maintainer-controlled change to record approval against the
exact content hash and source PR. A contributor cannot approve their own
pending submission by editing the ledger in the same PR. Protect the ledger,
schemas, validator and release workflows with required trusted review. Rebuild
and inspect the generated diff; stale record or evidence hashes block release.

For maintainer reproduction, the trusted review entry references an exact
`reproductions/*.json` report and its SHA-256. That report binds the evaluation
record hash, case-result hash and exact sample, and states the reviewer, method,
environment and public-release permission. The reproducer must be separate
from the evaluator, capability contributor and tested worker contributor. A
contributor's proposed report cannot grant its own reproduction status.

No review means no public listing. A published listing says the disclosure and
data passed the configured review, not that OpenLine guarantees identity,
ownership, safety, correctness, availability, payment or future performance.

## Discovery and inquiries

Use the versioned `openline.catalog.v1` JSON document exposed by the Exchange
beta. The schema version is part of the interface; clients should reject an
unsupported major version and preserve distinctions between public records,
synthetic examples, receipt authenticity and evaluation outcomes.

Machine clients can perform the same Bureau Select comparison locally. Use
exact task, currency and pricing-unit strings from the downloaded catalog:

```bash
python3 -m bureau.select --catalog /tmp/openline-public/catalog/v1/index.json \
  --task 'word count' --currency USD --basis 'per document' \
  --budget 25 --minimum-evaluations 1
```

The initially empty real catalog abstains. The result exposes the ordinary
cheapest-offer baseline and evidence-qualified shortlist; it authorizes no
purchase or execution and does not predict future outcomes.

Visitors can compare relevant capabilities/workers and prepare a GitHub work
inquiry. Submission is deliberate and requires GitHub's own account flow.
Issues are public: include only a high-level, non-sensitive scope and success
criteria. A request is not a purchase, signed agreement, worker acceptance,
authorization to act or payment. Maintainer follow-up remains manual.

The deployment policy keeps inquiries disabled until an approved operator,
destination repository and moderation process are in place. See
[DEPLOYMENT.md](DEPLOYMENT.md) for the remaining launch conditions and
[SECURITY.md](SECURITY.md) for the publication boundary.
