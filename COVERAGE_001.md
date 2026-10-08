# COVERAGE-001 — Receiver-Anchored Reporting Completeness

## Frozen plan (before implementation or experiment execution)

This plan is frozen in a separate commit. Changes to expected results must be
reported as deviations, not silently substituted. All workers, content, funds
and transactions are local synthetic fixtures. External paid API spending: $0.

Research question: can a participant hide six failures and still obtain a
complete-looking assessment when admissions are independently committed?

Actors: one enrolled buyer/receiver, one participating worker, and a Bureau
operator who independently retains a checkpoint. The operator explicitly pins
the receiver principal; neither a participant-supplied trust list nor a valid
signature establishes that the receiver is trustworthy.

The versioned, receiver/worker-signed agreement freezes receiver, worker,
eligible categories, finite admission period, reporting obligations, exact
permitted evidence fields, private audiences, and checkpoint freshness. Each
eligible admission has an opaque stable job ID, monotonically increasing
sequence starting at 1, sharing-agreement hash and receiver signature. Admission
is separate from execution, verification and simulated settlement. Receiver
commitments cover the entire ordered prefix, not only the submitted outcomes.

Bureau retains a signed closing checkpoint before accepting outcome reports.
It binds the exact agreement and ordered admission hashes. Independent local
retention time and report ordering belong to Bureau, not imported metadata.
The selected test period is closed before anchoring, while jobs can finish later.
Analysis must distinguish missing admissions, sequence gaps, missing outcomes,
staleness, conflicts, verification and settlement. It never imputes an outcome.

The trust assumption is faithful instrumentation of all eligible admissions
at the enrolled receiver boundary and honest pre-outcome checkpoint timing.
Bureau's local retained checkpoint is independent of subsequent worker reports,
but this prototype does not provide a remote witness, production authentication,
trusted clocks, or proof that a receiver had not privately learned outcomes.
Signatures authenticate statements, not completeness. No off-platform or
uninstrumented activity is discoverable.

## Mandatory arms and expected results

| Arm | Input | Frozen expectation |
| --- | --- | --- |
| A | Eight admissions committed before outcomes; two verified successes and six verified failures, all reported | coverage 8/8; observed completion rate 2/8 |
| B | Same admissions and outcomes; only two successes submitted | six missing outcomes; coverage 2/8; completion rate UNKNOWN |
| C | Two authentic successes without independently retained complete checkpoint | completeness NOT ESTABLISHED; completion rate UNKNOWN |
| D | Duplicate submission, forgery, changed scope, missing sequence/registration, stale checkpoint, signed conflicting checkpoint, fabricated completion, interrupted report | duplicates cannot inflate counts; invalid evidence refused; gaps/staleness/conflicts/incompleteness cannot certify history; interrupted reporting recovers without inventing outcomes |
| E | Ordinary nonmember Wallet/Exchange transaction | transaction works; private analysis denied |
| Falsifier | Dishonest receiver hides six admissions before its first independent commitment and commits only two genuine successes | the mechanism cannot detect hidden jobs; global completeness NOT ESTABLISHED; any conditional 2/2 is limited to the committed boundary |

Deterministic tests will check the above arms, receiver identity pinning,
signature and scope binding, immutable evidence, privacy restrictions, missing
settlement, pre-anchor reporting refusal, reopen/restart retention, and absence
from all existing unauthenticated public ledger/API views. Reuse the Exchange
engine, membership registrations, adapter verification, and Wallet signatures.
Do not rewrite signed historical receipts or add a transaction engine.

Required regressions: Bureau discovery suite, seven public evidence bundles,
Wallet discovery suite (report runtime-specific failures/skips honestly), and
local demonstration. Preserve public evidence and frozen Paper I. No World
changes, production service, scoring, dashboard, billing or marketplace work.

Stop after answering the question and preserving the suppression counterexample.
PASS means selective reporting is detected under the specified assumptions,
including an honest report of the critical falsifier; it never means global
receiver honesty or universal completeness was proven.

## Implemented mechanism and observed finding

The frozen plan commit is `322a643`. `bureau.coverage` adds private SQLite
tables separate from the public receipt table. `ReceiverBoundary.admit` reuses
the existing pre-work `Sharing.register`, records a signed receiver admission
with a durable sequence, then calls the unchanged Exchange commission method.
An interruption can therefore leave an admission without an execution; this is
incomplete evidence, not a failed outcome. The receiver journal and Bureau
checkpoint live in separate databases. The trusted local operator supplies
epoch seconds; demo times are synthetic, not claims about wall-clock timing.

The receiver's closing checkpoint lists every ordered admission hash, binds the
exact signed agreement and period, and is retained before reports. Bureau checks
that local admissions match every committed sequence. Missing admissions can
arrive later if they match the retained hash, but a previously disclosed outcome
cannot acquire a retrospective registration. Authenticated equivocation is
retained and quarantines future assessments, including after reopening the DB.
Replays do not refresh a checkpoint. Expiry requires a new prospective coverage
period; this implementation does not retroactively renew old commitments.

Reports reuse original authorized membership/Exchange receipts and the existing
adapter's signature, job, receiver-verification and settlement checks. Signed
records are never redacted or rewritten. Admission counts, execution receipts,
verified outcomes, missing verification, and missing settlement remain separate.
Reporting coverage counts verified outcomes. An overall completion rate requires
the entire committed history, including settlement evidence for successes;
unreported jobs are never counted as failures. Evidence is limited to the existing
authorized receipt fields, opaque job identifiers and hashes: private input files
and contents, prompts, credentials and keys are not exported. This experiment
uses synthetic fixed receipt metadata, not a general free-text privacy scanner.

The private API reuses membership's local role check. It is not production
authentication. No new public route was added; all seven existing JSON API views
were checked for private coverage IDs, job IDs and receiver principals.

**Finding: PASS for receiver-relative selective-report detection.**

| Arm | Observed result |
| --- | --- |
| A | 8/8 coverage; 2 verified successes, 6 verified failures; completion 2/8 |
| B | 2/8 coverage; six missing outcomes; completion UNKNOWN |
| C | authentic successful receipts without an independent checkpoint; NOT ESTABLISHED, completion UNKNOWN; retrospective anchoring refused |
| D | duplicates idempotent; forgeries and changed scope refused; gaps, staleness, mismatches and signed conflicts prevent certification; interrupted reporting/admission can recover without imputing outcomes |
| E | simulated nonmember transaction accepted; private analysis denied |
| Critical falsifier | actual eight jobs, six failures hidden before independent commitment; dishonest checkpoint includes only two admissions; conditional 2/2 appears complete; global completeness NOT ESTABLISHED |

The critical counterexample is preserved in the demonstration and tests. It uses
a fresh receiver execution: the dishonest truncated checkpoint is independently
retained before any outcomes in that execution. This is not a backdated result.
The receiver journal has eight actual admissions, while the independent Bureau
sees only two. Bureau cannot infer the hidden six from authentic signatures.

Under honest instrumentation and pre-outcome independent retention, a worker
cannot hide six outcomes and receive a complete assessment: the ordered signed
commitment supplies an eight-job denominator and missing reports withhold the
rate. If the receiver suppresses admissions before commitment, the answer is
**yes for a misleading receiver-relative history**; broader completeness remains
NOT ESTABLISHED. No claim about external adoption or off-platform work is earned.

No frozen expectations changed. Wallet, World, public evidence, prior experiments
and Paper I were not edited. See `VALIDATION.md` for reproduction and limitations.
