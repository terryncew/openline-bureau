# BUREAU-ALLOCATION-001

The loop runs locally: examine three workers in Bureau → select from their
task-specific buyer-verified history → review the exact input, worker, price,
maximum budget and expiry through Wallet's buyer CLI → commission using the
existing Exchange → receive its signed buyer verdict and simulated settlement
→ ingest selected records back into Bureau. Success, refusal, an unobserved
pending job, and a worker with insufficient history are included.

## Run the connected loop

Use the paired feature branches in `terryncew/openline-wallet` and
`terryncew/openline-bureau`, Python >=3.11, and Wallet's existing cryptography
dependency. Bureau adds no production dependencies. No paid APIs are called.

```bash
python3 -m venv /workspace/.venv
/workspace/.venv/bin/python -m pip install -e /workspace/openline-wallet
cd /workspace/openline-bureau
/workspace/.venv/bin/python -m bureau.allocation_demo \
  --wallet-repo /workspace/openline-wallet --out /tmp/allocation-fresh
```

The output directory must be new, preventing stale or future evidence from
entering history. It contains the private local Exchange home, selected public
`history.json` and `feedback.json`, the database, before/after comparison,
prospective protocol, frozen choices and experiment results. Keep `exchange/`
private; it contains keys and public fixture inputs. Only selected JSON exports
and reports are suitable for sharing. Source files are opened read-only for
export and ingestion; existing commission receipt formats are unchanged.

Read `/tmp/allocation-fresh/trust.json` and explicitly pin its controlled buyer
principal when starting Bureau:

```bash
/workspace/.venv/bin/python -m bureau.server \
  --db /tmp/allocation-fresh/bureau.db --port 8765 \
  --trusted-buyer <principal-from-trust.json>
```

The comparison is the default screen of the Bureau UI. The original overview,
ledger, authority timeline, incident/recovery and coverage APIs are accessible
through the same UI. The selected `main` checkout originally contained no UI
or tests despite the README describing them; this change supplies the missing
UI and baseline tests without replacing its backend.

Every comparison metric links to its exact source receipts. A receipt preserves
original job identity, original signed body/hash, worker/buyer, service, exact
scope, offered/agreed price, source-file hash and selected-record provenance.
The advertised profile is explicitly self-reported. No universal rating exists.

Inspect `openline-wallet/demo/agent-exchange-001/BUYER.md` for interactive review,
explicit digest approval, status, completion, revocation and selected export.
The browser is read-only: granting authority requires the local owner CLI.
The walkthrough executes the same buyer helper, creates separate one-price
grants for reviewed jobs, demonstrates both accepted and rejected work, then
revokes them. This is the existing trusted-operator simulation, not multi-user
authentication. The receiver retains the final consequence decision.

## Evidence and unknowns

- Wallet's existing Ed25519 verifier authenticates original records. An
  explicitly pinned buyer's **own** receiver signature is required for success
  or refusal measurements. Embedded agent keys alone do not prove delegation
  from that buyer. Missing crypto support or signatures leaves evidence
  unauthenticated. Buyer trust is operator policy, never taken from a packet.
- Accepted work additionally needs the signed seller result, matching job,
  nonce/input hash, frozen agreement and offer, and all seven existing receiver
  checks. A grant/agreement is never counted as successful execution.
- Rejected work remains rejected. Signed settlement must bind the accepted
  verdict, agreement, exact amount, owner, seller and SIM_USD currency. A result
  is not automatically payment. Missing settlement is unresolved.
- Counts deduplicate original buyer/job identity; contradictory signed bodies
  make a job unresolved. Rates use observed verified verdicts, **not all
  attempts**. Missing attempt counts and unobserved failures remain unknown.
- Costs mean signed simulated settlement amounts only. Refused jobs pay nothing
  under the original Exchange rules; this does not measure failed-work labor,
  compute or opportunity cost. No simulated amount is a real payment.
- Current authorization standing is NOT ESTABLISHED by the selected export;
  the private Wallet/receiver remains authoritative. Complete Wallet histories
  are unnecessary for comparing signed buyer verdicts. This is selected-record
  minimization, not cryptographic selective disclosure.
- The fixture uses comparable `text_digest` tasks with the same receiver rule.
  It does not establish predictive performance across arbitrary job types,
  input difficulty, buyers, or commercially independent workers.

## Prospectively frozen experiment

`protocol.json` is written before any jobs. `selections.json` binds its digest
and the exact historical packet before held-out task execution. Both conditions
have the same worker pool, profiles, offered prices, task content, per-task
budget (60), four-task allowance (240), and receiver evaluation. The kernel
requires distinct transaction nonces, so paired tasks share a content hash
while their signed input hashes differ. The selector accepts only profiles and
historical summary rows; future outcomes are neither supplied nor ingested
until evaluation completes. The fixture is transparent and deterministic,
not a blinded human trial.

Control chooses the cheapest eligible offer. Bureau uses accepted fraction per
offered price among workers with >=3 verified historical verdicts and no
unresolved job, falling back to control with sparse evidence. Three samples
are a fixture decision threshold, not a statistical reliability guarantee.
The primary metric is completion-rate delta. With four complete pairs and
sufficient history, a positive delta yields ADVANTAGE; zero or negative yields
NO_ADVANTAGE. Missing outcomes, fewer pairs or sparse history yield INCONCLUSIVE.
Secondary metrics and all worse choices are retained even when the primary wins.

Run both falsifiers in new directories:

```bash
/workspace/.venv/bin/python -m bureau.allocation_demo \
  --wallet-repo /workspace/openline-wallet --out /tmp/allocation-reversal \
  --scenario reversal
/workspace/.venv/bin/python -m bureau.allocation_demo \
  --wallet-repo /workspace/openline-wallet --out /tmp/allocation-sparse --sparse
```

Recorded public results and selected signed evidence are in
`demo/bureau-allocation-001/recorded/`. The mixed case improves completion but
**loses on accepted work per settled simulated dollar** and includes a worse
choice. The reversal case loses all four choices. Sparse evidence triggers the
same selection as control and prevents an advantage conclusion. These fixtures
demonstrate a falsifiable mechanism, not an economic advantage or demand.

## Validation

```bash
cd /workspace/openline-bureau
/workspace/.venv/bin/python -m unittest discover -s tests -v
/workspace/.venv/bin/python -m bureau.evidence public-evidence
node --check ui/app.js
cd /workspace/openline-wallet
PYTHONPATH=demo/agent-exchange-001 /workspace/.venv/bin/python \
  -m unittest discover -s demo/agent-exchange-001/tests -v
/workspace/.venv/bin/python -m unittest discover -s tests -v
```

The original Wallet suite requires writable `Path.home()` for five sandbox
preflight tests and Codex CLI 0.153.0 for its real CLI test. The cloud home is
read-only. Validation runs the **unmodified** suite through a runner that
redirects only Python `Path.home()` to a writable directory outside `/tmp`,
with the locally installed pinned CLI on PATH. No assertions are changed.
The seven RRSI integration tests remain explicitly skipped because their
pinned external repository is absent. Exact commands/counts and browser
validation are recorded in `VALIDATION.md`.

No production readiness, real payment, independent adoption, broad privacy
guarantee or commercial allocation advantage is claimed. Existing frozen
experiment files and published papers are untouched.

## Subordinate reciprocal-sharing foundation

The allocation integration and its 21 tests were completed first. A separate
small local example adds reciprocal sharing without changing the frozen
allocation protocol, Exchange receipt formats, or the open transaction path:

```bash
cd /workspace/openline-bureau
/workspace/.venv/bin/python -m bureau.membership_demo \
  --wallet-repo /workspace/openline-wallet --out /tmp/membership-private-fresh
```

Before an eligible commission begins, both local parties sign and durably
register `openline.bureau.evidence-sharing.v1`. It names the Bureau, buyer and
worker, the exact future job/agent/offer/input hash/nonce, permitted receipt
fields by original schema, reporting obligations for **all registered eligible
attempts and outcomes including failures**, and separate receipt/analysis
audiences. The existing Exchange request identity determines the future job
ID. Registration after the job has begun is refused. Registered scope is
immutable; changing scope requires a separately designed future agreement
version, not overwriting the original authorization.

Sharing is **private by default**. Reports retain original signed transaction
bodies and source hashes in separate SQLite tables, outside the existing
public receipt table and HTTP APIs. Members become eligible for private shared
analysis within each agreement's authorized audience. This is a local operator
role policy: the calling principal is supplied locally, and no remote login,
production identity, legal consent, subscription or billing system is added.
Analysis audiences do not silently enroll outsiders as contributing members.

The example registers two participating jobs before work: one successful and
one refused. It deliberately withholds the failed job's report. The registry
still shows two eligible jobs, the missing report stays visible, and the
completion fraction is NOT MEASURABLE. Contributing the original failure
evidence yields 1/2 accepted. Partial outcomes and unsettled accepted work also
remain incomplete. These are **registered commissions**, not proof of all
physical work attempts or external/off-register jobs; those counts remain
unknown. No unseen events are invented.

A third worker completes an ordinary nonmember Exchange transaction. That
worker cannot access the private reciprocal analysis, while Wallet and the
open OpenLine protocol remain usable without membership. Public receipt or
analysis export is refused unless the signed agreement explicitly authorizes
public visibility and the relevant public audience. A member's permission to
read analysis does not automatically grant access to another member's receipts.

Only the approved public `text_digest` fixture receipt schemas are supported.
Input contents/paths, prompts, private Wallet histories and credentials are
never included in these reports. Extra receipt fields and signature metadata
are refused. Field permissions do not provide semantic secret detection in
arbitrary free-form text: this demo uses approved synthetic contents only.
If a narrower field list would require redacting an original signed receipt,
sharing refuses it rather than pretending its original signature survives.
This is scoped data minimization, not cryptographic selective disclosure.

Keep the generated membership database, agreements, reports, analysis and
Exchange home private; they are not committed to public evidence. The example
prints only local fixture results. Fifteen additional regressions cover
pre-work registration, original signatures, omissions and failures, audience/
field restrictions, default-publication denial and explicit-public permission,
source preservation, report monotonicity and nonmember protocol operation.
