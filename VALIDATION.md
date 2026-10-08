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
