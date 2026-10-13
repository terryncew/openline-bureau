# Limited beta release and deployment plan

**Current state: local implementation for review; public launch is not
authorized.** The real catalog begins empty. Synthetic examples are a distinct
learning mode. No real contributor, independent evaluation, customer, payment,
commercial benefit or production readiness is implied by those fixtures.

Prepare and review draft PRs for Bureau and Exchange together. Wallet's
protocol and owner/receiver authorization boundary are preserved. Merging and
public deployment each require the owner's separate approval.

## Reproduce the public catalog locally

Use Python 3.11 or newer. The catalog compiler uses local JSON only; it does not
fetch external URLs, run capabilities, use paid APIs, or read Wallet state.
From the Bureau feature checkout:

```bash
python3 -m bureau.catalog validate --source catalog --pending
python3 -m bureau.catalog build --source catalog --out /tmp/openline-public/catalog/v1/index.json
python3 -m bureau.catalog build --source catalog --fixtures --out /tmp/openline-examples/synthetic/v1/index.json
python3 -m bureau.evidence public-evidence
python3 -m unittest discover -s tests -v
python3 scripts/check_select_parity.py --exchange /workspace/openline-exchange
```

The public build contains only reviewed data; the explicit fixture build emits
a separate synthetic catalog. Original reviewed records/evidence and schemas
are exported beside each index so people and agents can inspect the bytes.
Neither command approves a contribution. Existing
allocation/membership suites additionally require the local Wallet dependency
described in [BUREAU-ALLOCATION-001](../../BUREAU_ALLOCATION_001.md). Do not
upload their generated private databases, Wallet homes, keys or input files.

Run Exchange's beta build according to its beta README. Its offline browser
tests require Python Playwright and an installed `/usr/bin/chromium`; they do
not download a browser or contact external sites:

```bash
cd /workspace/openline-exchange
python3 scripts/build_beta.py --bureau /workspace/openline-bureau
python3 scripts/validate_beta.py
node --test tests/beta_model.test.mjs
node --check docs/beta/app.js
python3 tests/browser_beta.py --screenshots-dir /workspace/beta-deliverables/screenshots
python3 -m http.server 8765 --bind 127.0.0.1 --directory docs
# Open http://127.0.0.1:8765/beta/
```

Inspect the generated JSON and all visible views locally: discovery,
comparison, provenance, receipt/evaluation limitations, version lineage,
synthetic mode, empty real state and work-request generation. Confirm that a
browser test prepares a request without sending one or initiating payment.
Keep screenshots labeled with the data mode and commit under review. The
browser suite writes `beta-reviewed-empty-desktop.png` plus synthetic catalog,
detail, Select and mobile screenshots. They show fixture data or the empty real
state; they are not customer evidence.

## Proposed release architecture

Deploy only Exchange's generated static beta directory, including its versioned
JSON catalog and schemas. This needs no server database, account service,
worker execution, Wallet key custody or payment provider. Keep Bureau's analyst
server, private membership data, legacy `minisvc.py` and local commission homes
off the public host.

The manual Pages workflow uploads `docs/beta`, so its contents become the
approved site's root; the local preview serves the parent `docs` directory and
uses `/beta/`. Validate relative links at the chosen public base path before
launch. The build manifest covers UI assets, original approved records,
receipts, reproduction reports and schemas. The release validator rejects
undeclared, private, stale and symlinked files; only that inspected bundle is
suitable for the approved public artifact.

Use one release workflow with a protected branch and a protected publishing
environment. PR checks have no secrets, no write token, no deployment job and
no `pull_request_target` execution of fork code. A data contribution is checked
with trusted base validator code and review policy; changing policy or code in
the contribution cannot approve it. Maintainer changes to validator, schemas,
ledger and publishing configuration need separate review.

The initial implementation PR necessarily adds trusted compiler/guard code that
does not exist on the old base branch. Its data-only guard intentionally cannot
approve that bootstrap. Review the implementation as code, run its tests through
the manual read-only approved-code job, and require maintainer approval. Once
that reviewed code is on the protected base, subsequent data-only PRs use the
base parser/registry and an append-only check against the actual PR author.

Build the artifact from the approved paired Bureau/Exchange revisions. Record
both commit IDs and the generated catalog digest with the release. Structural
validation, review bindings, tests and browser checks must all pass. Publish
the inspected artifact rather than compiling different data after approval.
Preserve TLS verification and dependency integrity checks.

The inspected Exchange baseline had two `main`-push Pages workflows that
tolerated verification failure. The beta change replaces automatic publishing
with manual, protected release checks. Before approving any merge, inspect the
final workflow configuration and require reviewers on the publishing
environment: an environment name alone does not enforce approval. Restrict the
legacy arbitrary-URL `add-offer` path to reviewed data. Do not use its stored
badge or `verify_receipt_v12.py` as the beta publication verifier.

## Conditions for opening to outside contributors

Every item below is a launch gate, not an automatic follow-up to passing tests.
Their initial state is **pending owner/maintainer review**.

| Gate | Concrete decision or evidence required |
| --- | --- |
| Owner authorization | Separate approval to merge the reviewed paired PRs and approval to publish the exact artifact to the selected origin. No deployment, payment, paid API or customer-data approval is inferred from implementation permission. |
| Public origin and policy | Approved HTTPS host/base path; final repository, contribution and catalog URLs in the protected review policy; tested relative links, schema URLs and JSON discovery at that origin. |
| Maintainer ownership | Named reviewers and release operators with repository access, available review capacity, a release suspension path and an approved private security-reporting contact. |
| GitHub safeguards | Protected code/schema/workflow/review ledger; required checks and trusted review; fork-safe read-only PR validation; one fail-closed release workflow; no unreviewed-PR publication or automatic deploy on an unapproved merge. |
| Submission privacy and terms | Approved public-only submission instructions, contributor rights/permission statements, usage-term presentation, data retention/withdrawal process and explicit prohibition on confidential/customer data. |
| Moderation | Defined response to spam, malicious links, impersonation, forged evidence, missing failures, attribution/rights disputes and accidental disclosure. Decide who can suspend a listing or release and how changes retain a safe audit trail. |
| Request operation | Approved destination repository with Issues enabled, accountable operator and response expectations; public-data warning tested; inquiries explicitly enabled only after this approval. No promises of worker availability or purchase completion. |
| Permissioned real pilot | At least one useful real capability from a willing contributor, public usage terms/provenance and permissioned evidence; a separately contributed evaluation with disclosed independence, conditions, failures and limitations. Review actual PR authors and exact bytes. Synthetic fixtures cannot satisfy this gate. |
| Product validation | Passing automated and browser validation of the paired revisions; screenshot walkthrough of all states; inspection of the exact public artifact for private data, credential exposure and misleading claims. |
| Rollback rehearsal | Known previous artifact or empty-catalog fallback, tested ability to suspend inquiries and remove/suspend a listing, and an incident owner. |

Rights and privacy review can reject a record even when its schema and signatures
are valid. Technical reviewers must not create permissioned "real examples" by
assuming that publicly accessible evidence has unrestricted publication rights.

## Approved launch sequence

After those gates and the separate owner approval are satisfied:

1. Land the reviewed code and protected release configuration using the
   approved merge process. Confirm that conflicting legacy workflows are
   disabled before any push that could trigger them.
2. Review and land the first permissioned data contributions, with separate
   trusted review entries bound to the exact records and evidence.
3. Rebuild the paired static artifact, run the release checks, record its
   revisions/digest and inspect the published-content diff.
4. Publish the approved artifact to the approved origin. Test discovery JSON,
   schemas, UI, consent labels and the issue draft at the live origin using
   non-sensitive test content. Do not send a customer inquiry as a smoke test.
5. Enable inquiries only for the approved staffed destination. Invite the
   agreed limited pilot group; monitor review queues and reported problems.

Opening a limited pilot is evidence of an available workflow. Adoption requires
actual independent contributors and useful evaluations; economic value requires
prospective real task evidence and measured costs. Those findings must be
reported with negative results and uncertainty, separately from launch status.

## Rollback

Suspend inquiries in the protected policy and redeploy the last inspected
artifact or an empty public catalog. Remove unsafe listings through reviewed
changes and preserve safe correction metadata. For leaked credentials, revoke
them immediately and remove sensitive history through the host/GitHub process;
rollback alone does not erase already published data. Do not expose private
Bureau or Wallet state to diagnose a public incident.
