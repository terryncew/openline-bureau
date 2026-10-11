# OPENLINE-AUTONOMY-001 Phase 1.5

Continues Muse's Phase 1 at `f7c9515b8f9f08076e3f5ca83dc06199001a553b`.
Existing coordinator, queue, mission, owner policy, holdouts and dashboard
are retained. No merge, push, publication, deployment or external model call.
The target remains the original pinned review-desk baseline `24f5609992d5a1bb088e361b4b066d2e11bfa676`.

## Consequence boundary

The coordinator prepares an immutable evaluated Git commit, then calls
Receipt Gate's `evaluate_request` and `VerifiedCommitLedger.execute_once`
to authorize **one exact create-only isolated branch ref update**. The signed
permission binds tool, target, settings (commit and expected nonexistent ref),
mission digest, policy, run, evidence digest, expiry and a one-use code. No
worker-reported file list or line count can authorize acceptance: the evaluator
reads the actual staged and unstaged Git delta. Existing refs are never deleted
or overwritten. Failed checks cannot call the ref executor.

Signed Bureau receipts form a hash chain; signatures and links are verified on
restart. Local receiver Ed25519 keys are generated with mode 0600 outside
worker exports. Evidence, signed source/witness inputs, Gate permission and
execution results are retained under the runtime state's `gate/` directory.
File writes use fsync, atomic replacement and directory fsync. Git operations
request `core.fsync=all`. Receipt Gate consumption is flushed before the ref
update. An orphan receipt written before state replacement is reconciled.

These are local operator-controlled keys, **not independent external
attestation or owner-signed mandates**. The existing owner-authored mission and
policy remain the authority source. The receiver's cryptographic decision
binds them; cryptography does not prove that software improved.

## Interruption and revocation

A nonblocking controller lock prevents two loops executing one queue. An
interrupted build/evaluation or unused permission is HELD without automatically
rerunning a worker or minting replacement authority. If death occurs after the
ref update, recovery verifies the signed permission and evidence binding,
compares the exact ref/commit, and records the observed completed effect without
executing again. Missing/divergent or corrupt evidence fails closed. Recovery
may record a previously completed effect after revocation; it grants no new work.

Use the supported owner stop command (no credentials or valid mission parse
are needed):

```bash
export PYTHONPATH=/workspace/.onboarding/python
cd /workspace/openline-bureau
python3 experiments/autonomy-001/coordinator.py --revoke --state-dir /path/to/state
```

It writes a durable `REVOKED` marker under the same effect lock used for branch
updates. Once the command returns, later updates cannot pass. A build already
running is bounded by the 120-second sandbox deadline and discarded at the next
phase boundary. Observed `mission.yaml` revocation also latches the marker;
direct file edits do not share the command's concurrency serialization point.
Policy, mission (except its revoke flag), or queue changes require owner review
and do not silently renew authority. `max_tasks` and `max_cycles` are enforced.
Unsigned Phase 1 state is not auto-upgraded or erased; use a separate Phase 1.5
state directory and preserve historical evidence.

## Airlock reuse and isolation

Dependencies inspected and installed at exact upstream commits:

- Airlock `ac7da750b5cf85749650f19c0acb5946b0adc39e`.
- Receipt Gate `abc610be560284130e0d08b2fd51e59ef0b1c623`.

`AirlockWorker` reuses `airlock.providers.registry.resolve_provider` and
`airlock.util.expand`; execution and evaluation reuse
`airlock_submit.worker._docker_result`. No second provider registry, Docker
executor or objective scoring algorithm was introduced. These private upstream
APIs are deliberately pinned and must be retested before upgrading.

Airlock's `WorktreeSandbox` is filesystem organization, not an OS security
boundary. Its default tournament/sieve executes on the host; that is unsuitable
for this threat model. The full submission evaluator requires GitHub submission
metadata and a baseline `.airlock/config.json` that the review-desk baseline
does not have. Its Docker execution primitive can be used directly, while the
existing review-desk protected/holdout evaluator remains the task-specific layer.
Airlock's actual `evaluate_survivor` is exercised in the tests to distinguish
structural survival from measured objective gain; no objective is invented or
added to the owner's mission.

Workers receive a tracked export of only the target scope, without Git pointers,
coordinator, governing policy, credentials, protected tests or holdouts. The
worker interface currently permits existing-file edits only; new files,
deletions, symlinks and credential forwarding fail closed. Evaluation exports
tracked pinned baseline files plus the actual candidate diff, and imports the
candidate review engine for holdouts. It refuses protected paths, binaries,
unauthorized files, extra files, empty patches and zero-test runs. It checks
persistent evaluator side effects without following newly created symlinks.

Both run inside Docker with network disabled, all capabilities dropped,
no-new-privileges, a read-only image, a secretless non-root environment and
memory/CPU/PID limits. The only writable host bind is the expendable export;
controller state, keys and Git metadata are absent. The Python image is pinned
by digest `sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce`.
A trusted in-container deadline supervisor exits even if the controller/Docker
client dies. Log files are limited to 2 MiB; only their tails are returned.
Bubblewrap was tested and unavailable (`setting up uid map: Read-only file system`);
there is no unsafe host-execution fallback. Docker successfully executed checks.

## Run and limitations

```bash
export PYTHONPATH=/workspace/.onboarding/python
cd /workspace/openline-bureau
python3 -m unittest discover -s experiments/autonomy-001/tests
python3 -m unittest tests.test_bureau
python3 -m bureau.evidence public-evidence
# One deterministic, owner-preauthorized cycle, never a model API call:
python3 experiments/autonomy-001/coordinator.py --once --state-dir /path/to/new-state
```

`--provider codex` selects Airlock's existing adapter but stays offline in the
same pinned image. The host has Codex CLI 0.159.2, while that image contains no
coding agent or model. No authorized isolated authentication route with an
established $0 charge guarantee was available. A live coding-agent experiment
was therefore **not run**. Do not mount host auth, enable network or substitute
paid API access to bypass this blocker. The offline adapter fixture is explicitly
not a live coding agent.

Tests establish enforcement and recovery in this machine, not resistance to a
Docker/kernel escape, hostile host operator, rollback of the entire evidence
store, or power-loss durability. There is no remote evidence anchor, distributed
revocation, hardware-rooted signer or independently verified model identity.
Passing regressions/holdouts is labeled `NOT_ESTABLISHED` for improvement. The
metric test uses synthetic values through Airlock's real scoring code; it proves
the selection distinction, not improvement in real software. No continuous
self-improvement or recursive improvement is claimed. A real objective and
independent outcome evidence remain prerequisites to such a claim.

The Phase 1 `registry-add-claim` scripted proposal is now quarantined before its
protected registry file is written. The historical held result above remains
Phase 1 evidence; preserving it does not mean keeping that authorization gap.

A retained deterministic smoke cycle accepted `ui-empty-records` into the
original coordinator's scratch clone only. It ran **21 protected tests and 2
holdouts**. [evidence/phase15-smoke](evidence/phase15-smoke) contains its actual
candidate patch/commit body, signed local Bureau receipts, Receipt Gate
permission, bound evaluation evidence and execution result. No private keys,
credentials or one-use code are included. Manifest hashes and signatures were
verified after copying. The generic Bureau conformance validator still performs
structural checks; it does not itself verify this top-level OLP signature
envelope. Verification uses Receipt Gate's `verify_olp_signature` and
`verify_decision_receipt` against the manifest's explicitly local public key.

## Recorded validation results

Final validation on this cloud machine:

| Check | Exact result |
|---|---|
| Autonomy suite | **25 tests, all passed**, 158.098 seconds; raw runner output in [evidence/phase15-validation.txt](evidence/phase15-validation.txt) |
| Real process deaths | SIGKILL after build, after permission preparation, and after actual ref update; held/held/reconciled respectively |
| Attribution violation | Matching ref created without Gate consumption/execution is refused as unattributed |
| Authority violations | Tampered signature/target, changed tool/settings/run, wrong code, revoked preflight and reused permission all refused without executor effects |
| Isolation | Host-file canary absent, secret environment canary absent, outbound socket fails, credential forwarding refused, deadline returns 124 |
| Evaluation distinction | Candidate passes all 21 protected tests but fails the hidden injection holdout; rejected by evaluation |
| Improvement distinction | Airlock's scoring rejects flat/regressing synthetic metrics, accepts a qualifying synthetic gain; no real software improvement demonstrated |
| Deterministic smoke cycle | UI task accepted in scratch only; 21 protected tests + 2 holdouts; signed evidence and candidate commit body verified |
| Bureau core | 2 tests passed |
| Public evidence | 7/7 bundles validated; their own PASS/FAIL experiment outcomes are preserved |
| Full unrelated Bureau discovery | Failed with **20 import/setup errors**, missing Wallet/Exchange (`exchange` module); these suites remain unprepared, not diagnosed as application defects |
| Reusable setup | Complete pinned install script executed successfully over the existing dependency directory; `install_script` and `start_skill` draft fields confirmed saved |

Resolved setup/development failures: the initial Phase 1 suite had 8 errors from
its hardcoded missing `/tmp/rd/bureau` fixture; the test now uses the selected
checkout. The new synthetic metric fixture initially emitted `metric` instead
of Airlock's required `value`; corrected. A new recovery attribution check
initially used `action_hash` instead of the journal's `attempt_action_hash`;
corrected and both the affected SIGKILL test and final complete suite passed.
No assertions were disabled and no zero-test run was counted as validation.

The final suite's deliberately crashing children terminate with SIGKILL; those
are expected fault injections, not skipped or expected-failure tests. No
protected owner file or Phase 1 evidence was changed. Only a README link was
added to the historical Phase 1 writeup.

Remaining limits include no total disk quota on writable sandbox exports (the
file-size/log, memory, CPU, PID and time limits are enforced), no power-loss
fault injection, and no kernel/container-escape certification. No authenticated
live agent or real improvement measurement was performed. Installed Codex auth
file presence was checked without reading its values; existing Git access
worked. The live blocker is an unavailable **safe isolated, demonstrably $0
model route**, not an assertion that the user lacks credentials.

The environment configuration is a saved draft only. It was not applied by the
draft tool or published, and restoration in a new task was not tested. The
current machine supports this Phase 1.5 development/test workflow; fully ready
live-agent autonomy and continuous self-improvement are not claimed.
