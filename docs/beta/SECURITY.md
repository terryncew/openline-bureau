# Public beta security and evidence boundary

The limited beta serves reviewed public JSON and a static Exchange interface.
It does not run capabilities, fetch submitted receipt URLs during compilation,
sign commissions, authorize Wallet effects, accept customer inputs, or process
payments. This document describes the beta boundary; it does not certify the
older prototype services for internet exposure.

## Threat model

Treat contribution files, free text, receipt contents, URLs, contributor claims
and evaluation results as hostile input. A pull request can include a false
identity, malicious URL, forged "verified" field, copied benchmark, selective
successes, secrets, confidential evidence or changes to the validator itself.
GitHub author identity and a different evaluator identifier do not prove two
independent people; maintainers must review provenance and disclosed conflicts.

The review ledger and protected release workflow are security policy. A
contributor's proposed edits to either are not permission to publish. Hash
binding prevents a reviewed file from changing unnoticed; it does not turn the
reviewer into an outcome verifier or make malicious approved content harmless.

## Data and publication rules

- Keep the public catalog empty by default. Synthetic examples have their own
  namespace/output and remain conspicuously labeled in every view and JSON.
- Validate data against the versioned contract and reject extra fields,
  duplicate identifiers, malformed references, nonfinite numeric values,
  excessive size/depth and invalid version lineage. Bound file counts and file
  sizes before parsing. Read only the intended input files; reject traversal
  and symlinks escaping the submission root.
- A contribution is publishable only when its public-consent/rights statements
  and exact source hash match a maintainer review entry. All dependent records
  and evidence need their own applicable review, not inherited approval from a
  capability description. Evaluation is bound to an exact version.
- Public permission must cover the original evidence and any persons or
  organizations described by it. A submitter's checkbox is a representation;
  it is not independently established legal consent. Maintainers must examine
  the context before approval. Never upload a private record first and seek
  permission later: public PR history may preserve it even after deletion.
- Do not publish personal/customer data, confidential task inputs, prompts,
  wallet exports, local database files, private keys, access tokens, environment
  dumps or authenticated URLs. Automated secret-pattern checks reduce mistakes;
  they cannot identify every secret or private fact in arbitrary prose.
- Preserve original signed data and provenance. Editing an original receipt to
  redact it invalidates its original signature. When the full signed record
  cannot be published safely, do not publish it or claim that a redacted record
  keeps that signature's assurance.

## Safe rendering and links

Render contributed strings as text, never as HTML or executable Markdown. Only
validated HTTPS links may be followed. Reject credentials in URLs, non-web
schemes, control characters, localhost/private-address destinations and other
URL forms forbidden by the compiler. No server-side URL retrieval is part of
this workflow, so a submitted endpoint cannot be used to reach cloud metadata
or internal services. An accepted external link is not a safety endorsement;
its destination may change after review.

URL validation is syntactic and the compiler does not resolve DNS. Agent clients
that choose to fetch external links must enforce their own destination,
credential and redirect policy, including rejecting addresses that resolve to
private networks. Catalog discovery never authorizes a client to download or
execute a referenced capability.

Keep inquiry destinations restricted to the configured repository. The browser
constructs a plain-text issue draft and leaves final submission to the visitor.
Never copy confidential job descriptions from private Bureau databases into an
issue. The interface must make clear that issues and their contents are public.
If a buyer needs confidential work, the beta must direct them to an approved
separate contact process without accepting those inputs itself.

## Verification claims

A schema match establishes structure. Signature verification establishes
authenticated bytes under a specified key policy. A hash identifies content.
None by itself establishes business identity, factual accuracy, outcome
reproduction, comprehensive reporting, legal rights, receiver authorization,
delivery or payment. Contributor-supplied "verified", trust or authenticity
booleans cannot promote evidence to verified status.

An independently submitted evaluation needs a different contributor from the
capability publisher, exact version references, procedure, test conditions,
denominators, failures, limitations and conflict disclosures. Publication
review confirms these records meet policy; scientific confidence remains
limited to the evidence. Self-reported performance cannot silently acquire an
independent badge. Missing receipt verification support stays unknown.

The private membership module trusts a principal supplied by the local operator.
Its audience checks are not an internet login system. They must not be reused
as public authentication. Bureau's existing HTTP server exposes raw receipt
payloads without authentication; keep it local and never serve a private
database publicly. This beta publishes only the deliberately reviewed static
catalog.

Wallet's `EVIDENCE_VALID` result does not grant permission to act. A receiver's
Gate decides whether a consequence is allowed. This beta makes no grant, signs
no buyer mandate, starts no work, and produces no real settlement. Existing
`SIM_USD` examples must remain simulated in all product copy.

## GitHub and release controls

PR validation must run without secrets and with `contents: read`. Do not use
`pull_request_target` to check out or execute fork code. Changes to scripts,
schemas, review policy and workflows require trusted maintainer review before
running them with write permissions. A fork may test itself, but it cannot
change the approved public catalog by supplying its own review entry.

Compile the release using trusted validator code and protected review policy,
then review the diff in generated data. Only an approved artifact from the
protected release branch may be deployed. A red build blocks publication; do
not use `|| true` for any release prerequisite. Keep publishing separate from
PR validation and require the separately approved deployment environment.

## Existing prototype paths to keep out of the beta

The inspected Exchange baseline contains an `add-offer` workflow that fetches
an arbitrary receipt URL and writes offers directly, and two Pages workflows
that tolerate verification failures. Its legacy receipt status derives from
version/field presence, rather than outcome verification. Those paths must
not import beta submissions or serve as its publication gate. Before launch,
replace or disable conflicting deploy workflows, and clearly separate the
legacy display from beta evidence claims.

The legacy Exchange `minisvc.py` uses unvalidated path suffixes to select local
files and binds on all interfaces. Do not deploy it. The public beta requires
only the generated static directory, not that service, Bureau's analyst server,
an Exchange commission home, or Wallet state.

## Incident and moderation response

Before launch designate maintainers who can suspend releases, remove unsafe
entries and handle private security reports. Keep a review audit trail for
corrections and withdrawals; history is useful but must not perpetuate a leaked
secret. For accidental disclosure, revoke the exposed credential, remove all
published copies and caches where possible, and use GitHub's sensitive-data
removal process. Deleting a JSON file alone does not remove Git history.

Reports of fraud, false attribution, rights disputes or cherry-picked results
should suspend the affected claim pending review. Corrections must identify the
affected version and evidence rather than silently changing past outcomes.
Until an approved private reporting contact exists, do not invite confidential
incident reports through public issues.
