# Recorded validation

Prepared from Bureau main `73f84422109e3c0caf1c732e7322db1b3a1e5f8f`
and Wallet main `439977484229805b61ad741c03334953413c8d48`, on the
`feat/bureau-allocation-001` branches. Final commits are reported in the PRs.
Python 3.12.14; Node 24.19.0; cryptography 50.0.2; MCP 2.3.0.

| Check | Result |
|---|---|
| Bureau `python -m unittest discover -s tests -v` | 36 passed, 0 failed: completed allocation/baseline 21 plus subordinate membership 15 |
| Exchange `PYTHONPATH=demo/agent-exchange-001 python -m unittest discover -s demo/agent-exchange-001/tests -v` | 54 passed, 0 failed; includes original 43 |
| Original Wallet suite through runner below | 189 passed, 7 skipped, 0 failed (196 discovered) |
| Bureau `python -m bureau.evidence public-evidence` | 7/7 bundle validations passed, source files modified 0; underlying experiments retain their original positive/negative verdicts |
| `node --check ui/app.js` | passed |
| `node tests/browser_smoke.mjs http://127.0.0.1:8765` against populated, explicitly pinned local fixture | passed: three workers, unknown history, metric → exact signed receipt/provenance, existing ledger navigation |
| Wallet `openline-wallet demo-platform-exit --output <fresh-directory>` then `openline-wallet verify <directory>/wallet-after.olw` | PLATFORM_EXIT_CONTINUITY_ENFORCED; EVIDENCE_VALID |
| Wallet `python -m pip wheel . --no-deps --wheel-dir <outside-checkout-directory>` and `python -m pip check` | wheel built, no broken requirements |
| Wallet provider-effect reproduce/verify and frozen predecessor reappraisal | CONTROLLED_TRANSPORT_BOUNDARY_ENFORCED (self-attested fixture context); FROZEN_EVIDENCE_CONSISTENT |
| Selected recorded evidence | all SHA256.json hashes checked; every reported held-out result authenticated against its exact selected job and explicitly pinned buyer |

Normal Wallet test execution first found five errors from the read-only cloud
home. A writable Python home resolved those; the remaining real CLI version
assertion required Codex 0.153.0. No source files or assertions were changed:

```bash
npm install --prefix /workspace/setup-tools \
  --cache /workspace/setup-artifacts/npm-cache @openai/codex@0.153.0
cd /workspace/openline-wallet
PATH=/workspace/setup-tools/node_modules/.bin:$PATH /workspace/.venv/bin/python - <<'PY'
from pathlib import Path
import unittest
home = Path('/workspace/setup-artifacts/test-home')
home.mkdir(exist_ok=True)
Path.home = classmethod(lambda cls: home)
suite = unittest.defaultTestLoader.discover('tests')
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
PY
```

The seven skipped RRSI tests require external repository commit
`e4d1a7a0388e02b388bc40eb0a125fcfc7123f8d`. That optional upstream integration
was not installed or claimed as tested. The original Bureau checkout had no
tests or UI files; its documented tests could not run initially. The added
baseline and allocation regressions now execute real tests, including all
existing API routes and source preservation, rather than a zero-test check.

The added reciprocal membership example ran with two jointly signed pre-work
registrations. Omitting the refused job left the accepted fraction unknown;
contributing it yielded 1/2. A nonmember transaction was accepted by the open
Exchange, private membership analysis access was refused, and public export
was denied by the default private scope. All 15 membership regressions passed,
including explicit public authorization and field-scope enforcement. The
private membership records/database/analysis were kept outside the checkouts;
the previously recorded allocation experiment was not changed.

The first headless Chromium `--dump-dom` attempts timed out, including an
attempt outside the filesystem sandbox. Chromium's DevTools transport worked;
the checked-in browser smoke uses it and successfully validates the actual
JavaScript interactions. It does not use a paid API or a public preview.

## Outcomes retained

| Synthetic fixture | Control accepted | Bureau accepted | Primary verdict | Bureau worse choices |
|---|---:|---:|---|---:|
| Mixed history/future | 1/4 | 3/4 | ADVANTAGE (+0.5 completion delta) | 1 |
| History reversal | 4/4 | 0/4 | NO_ADVANTAGE (-1.0) | 4 |
| Sparse history | 1/4 | 1/4 | INCONCLUSIVE (0.0) | 0 |

In the mixed fixture, control spends 40 settled SIM_USD and produces
0.025 accepted jobs per settled unit; Bureau spends 150 and produces 0.020.
The primary completion advantage therefore coexists with **worse observed
cost efficiency**. In reversal Bureau spends zero settled units because
all work is refused: accepted work per unit is NOT MEASURABLE, never infinity.
Unpaid failed-work costs are unknown. These are deterministic fixtures with
local controlled roles; no economic advantage, real payment, real hiring
demand or independent commercial adoption has been established.

Reports preserve the four paired task IDs, common task-content hashes,
condition-specific signed job IDs, selection/history/protocol digests, raw
selected signatures, successful and failed transactions, unknown pending work,
and per-metric receipt links. Private Exchange homes and keys are not committed.

## COVERAGE-001 validation

Finding: **PASS under the frozen receiver/checkpoint assumptions**. The dishonest
receiver suppression counterexample remains reproducible; global completeness
is **NOT ESTABLISHED**. No external paid APIs were used ($0).

## Reproduce

Python 3.12.14, Node 24.19.0; Wallet at
`c46e82a324199050239540f1825a3b0c942e4053`, Bureau base
`3c3f7588b4665dff3344f834cce932628693aa02`. The plan was committed before
implementation and execution: `322a643`.

Use the existing checkouts; these commands do not require a worktree.
Wallet declares dependency ranges rather than a lockfile; installed versions
include cryptography 50.0.2 and MCP 2.3.0. No dependency declarations changed.

```bash
python3 -m venv /workspace/.venvs/openline
/workspace/.venvs/openline/bin/python -m pip install -e '/workspace/openline-wallet[mcp]'
source /workspace/.venvs/openline/bin/activate
cd /workspace/openline-bureau
python -m unittest tests.test_coverage -v
python -m unittest discover -s tests -v
python -m bureau.evidence public-evidence
# Choose a NEW scratch directory on each run; it contains simulated private DBs/keys.
python -m bureau.coverage_demo --wallet-repo /workspace/openline-wallet \
  --out /workspace/.onboarding/coverage-001-validated
```

The final full discovery run includes **54 passing tests: 18 new coverage tests
and 36 existing regressions**, no skips. All seven public evidence bundles pass
and report source files modified: 0. The standalone demonstration passes the
complete, selective, uncertifiable, dishonest-receiver and nonmember assertions.
`experiments/coverage-001/result.json` retains the observed synthetic counts;
the code regenerates the private signed evidence in the chosen scratch directory.
Keys and private databases are not committed. Generated identities/timestamps
vary between runs; arm outcomes and assertions are deterministic.

Expected core results:

| History | Verified reports / committed jobs | Missing outcomes | Completion rate |
| --- | --- | --- | --- |
| Complete | 8/8 | 0 | 2/8 |
| Selective | 2/8 | 6 | UNKNOWN |
| No anchor | denominator UNKNOWN | uncertifiable | UNKNOWN |
| Dishonest receiver, six admissions hidden | 2/2 visible; actual 8 | hidden six undiscoverable | 2/2 only relative to false receiver declaration; global NOT ESTABLISHED |

Checks cover signatures, fabricated completions, immutable scope and reports,
duplicate evidence, sequence gaps, missing registrations, stale/future checkpoints,
signed conflicts retained across restart, pre-anchor reports, late registration
after disclosure, partial/unsettled outcomes, interrupted admission and replay,
private fields and every existing unauthenticated JSON API view. Accepted-but-
unsettled work is reported separately from missing verification; it cannot earn
a complete settled-history rate.

## Wallet regression and setup diagnosis

The unchanged Wallet suite initially ran 196 tests with five errors because
`Path.home()` points to read-only `/home/agent`; seven optional RRSI tests skipped.
Redirecting only `Path.home()` for that run diagnosed one further failure: the
image's Codex 0.159.0-alpha.3 does not match the suite's pinned 0.153.0 assertion.
No assertions or tests were disabled. Install the repository's exact CI CLI pin:

```bash
npm install --prefix /workspace/.tools/codex-0.153.0 \
  --cache /workspace/.cache/npm @openai/codex@0.153.0
mkdir -p /workspace/.onboarding/test-home
cd /workspace/openline-wallet
PATH=/workspace/.tools/codex-0.153.0/node_modules/.bin:$PATH \
  /workspace/.venvs/openline/bin/python - <<'PY'
from pathlib import Path
from unittest.mock import patch
import unittest
with patch.object(Path, 'home', return_value=Path('/workspace/.onboarding/test-home')):
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover('tests'))
raise SystemExit(not result.wasSuccessful())
PY
```

Final Wallet result: **196 tests run, 189 passed, 7 skipped**, no failures/errors.
The existing Exchange regression suite also passed **54/54**:

```bash
cd /workspace/openline-wallet
PYTHONPATH=demo/agent-exchange-001 /workspace/.venvs/openline/bin/python \
  -m unittest discover -s demo/agent-exchange-001/tests -v
```

The skips require the optional google-research/rrsi checkout at
`e4d1a7a0388e02b388bc40eb0a125fcfc7123f8d`; that unrelated upstream comparator
was not installed. Real Claude/Codex provider experiments were not run. The
home override is limited to the test process; HOME and credentials are unchanged.

Additional setup checks passed: Wallet wheel build, provider-switch demo
(`PLATFORM_EXIT_CONTINUITY_ENFORCED`), exported bundle (`EVIDENCE_VALID`),
`pip check`, and Bureau's synthetic 28-receipt HTTP workflow (root, overview,
ledger, timeline, incidents and coverage). Reusable install/start instructions
were saved to the environment draft and the complete install script was rerun
successfully. Saving is not publication or fresh-task restoration validation.

## Limits and review

Local trusted-operator time/role policy, faithfully instrumented receiver and
pre-outcome independent retention are assumptions. An imported timestamp or
signature alone proves neither timing nor completeness. If the receiver hides
jobs before commitment, six real failures can be concealed; the experiment
preserves that counterexample rather than calling signatures complete evidence.
No remote witness, production auth, external adoption, off-platform detection,
general semantic privacy filtering or production settlement is claimed.
The existing headless browser interaction smoke and unrelated proof/comparator
suites were not rerun; the UI was unchanged, `node --check ui/app.js` passed,
and the coverage tests exercised all seven existing JSON API views directly.

Git reads and branch push succeeded through the existing HTTPS proxy. Initial
GitHub API requests to `api.github.com` received a proxy CONNECT 403. The domain
was added to the saved draft while preserving the package-manager presets.
After finishing independent validation and pushing the branch, the API operation
succeeded using existing credentials: draft PR
https://github.com/terryncew/openline-bureau/pull/2. No new credential was needed.
Review and save the reusable environment changes in settings, then publish to
activate the prepared snapshot. Publication and fresh-task restoration were not
performed or claimed. No merge was attempted.
