# Source continuity and public review fixes

The exact original Phase 1.5 commit is retained privately. Its unpublished
author/committer metadata contains a private-relay email address, so that
commit is not pushed to the public repository. No private keys, raw one-use
codes, credentials or private review records were found in its source tree.
The public branch also replaces the unpublished Phase 1 email metadata with
the existing public GitHub noreply identity. It preserves Muse's source.

## Identical source before review fixes

| Snapshot | Commit | Git tree |
|---|---|---|
| Original Phase 1, retained in private history | `f7c9515b8f9f08076e3f5ca83dc06199001a553b` | `dae9b3c2a98c131d473d70b1bb9c67cd17929604` |
| Public Phase 1 metadata-only copy | `1d874e5ee17fb27a079d714fd65fec966ef405aa` | `dae9b3c2a98c131d473d70b1bb9c67cd17929604` |
| Exact original Phase 1.5, private | `db0356f76ff5ae02abf2ca51843b616c121b9e19` | `ca001897053cff64286a9dff613c8687c20f14e6` |
| Public Phase 1.5 metadata-only copy | `88019fd7c24f657f9559b5365ac51bcdaec26657` | `ca001897053cff64286a9dff613c8687c20f14e6` |

Equal Git tree hashes mean identical tracked paths, modes and file contents.
Commit hashes differ because metadata and parent commit identifiers differ.
The historical signed evidence is preserved; its source-verification public
key is added separately below. The original commit is intentionally unavailable
from the public remote. An authorized private reviewer can verify both trees
from the private Git bundle, without trusting this table:

```bash
git rev-parse db0356f76ff5ae02abf2ca51843b616c121b9e19^{tree}
git rev-parse 88019fd7c24f657f9559b5365ac51bcdaec26657^{tree}
git diff --exit-code db0356f76ff5ae02abf2ca51843b616c121b9e19 \
    88019fd7c24f657f9559b5365ac51bcdaec26657
```

## Subsequent changes, separately identified

These changes deliberately differ from the original source. They address
review findings, setup and presentation; they do not alter the owner's mission,
policy, task queue, holdout checks or registry, or relax an original assertion.

| Commit | Change |
|---|---|
| `87af86215c7dde31f75ef792565326120239d850` | Review Desk rejects foreign Host/Origin and non-JSON writes; closes file handles; smoke records use unique external temporary directories. |
| `4e48a7e231af60ae2b59d31eac13050c61c9e6e0` | Dashboard escapes dynamic HTML, restricts status classes, and documents supported revocation; revocation tests use temporary mission copies. |
| `ca01234b332374ef636ed84af83b38363b76892d` | Deadline supervisor requires namespace PID 1 and disables tracing; root callers are refused; UI acceptance requires the owner's exact queued replacement; obsolete evaluator claims/helper removed. Adds controller/client-death, interruption, UI-authority and root-refusal regressions. |
| `7ca9eb22420a7145e5954e80f73424f61e654008` | Adds only the historical source public-key mapping; verifies retained checksums, source/witness/Gate/Bureau signatures, receipt chain and candidate Git commit. Signed artifacts remain unchanged. |
| `be046a2a348a49f35761b33d203c38240215fc67` | Pins runtime, build tools, upstream commits and image; supplies portable isolated setup and optional Wallet dependency; replaces the obsolete destructive demo with one checked cycle and refuses checkout-local private state. |
| `36a986ee3e9f3bd76f60f41be2d101f3d276c391` | Adds the public research goal, honest scripted-worker explanation, setup-plus-demo command and README links. |

The following documentation commit records this table and exact validation
results; use `git log` to obtain its own identifier. Future changes require
their own review. Passing checks does not authorize merging or demonstrate
production security or recursive self-improvement.

## Public checkout and reproducibility

```bash
git clone --branch feature/openline-autonomy-001-phase-1-5-public \
    https://github.com/terryncew/openline-bureau.git
cd openline-bureau
git log -8 --oneline
# One fresh pinned setup plus one scripted, offline cycle:
bash experiments/autonomy-001/demo/reproduce.sh
```

Pin the public head reported with the release when comparing results. The
required original target baseline `24f5609992d5a1bb088e361b4b066d2e11bfa676`
remains in the public branch's Git ancestry. A source ZIP without Git history
is insufficient for this experiment.

For the complete Bureau and experimental suites, as a non-root Linux user
with Python 3.12+, Git and Docker:

```bash
phase15_review_root=$(mktemp -d /tmp/openline-review.XXXXXX)
bash experiments/autonomy-001/setup/setup.sh \
    --venv "$phase15_review_root/venv" --wallet-repo "$phase15_review_root/wallet"
unset PYTHONPATH
export OPENLINE_WALLET_REPO="$phase15_review_root/wallet"
"$phase15_review_root/venv/bin/python" -m unittest discover -s experiments/autonomy-001/tests -v
"$phase15_review_root/venv/bin/python" -W error::ResourceWarning \
    -m unittest discover -s experiments/review-desk-001/tests -v
"$phase15_review_root/venv/bin/python" -m unittest discover -s tests -v
"$phase15_review_root/venv/bin/python" -m bureau.evidence public-evidence
node --check ui/app.js
node --check experiments/review-desk-001/ui/app.js
```

Exact dependency pins, historical failures and current results are in
[PHASE15.md](PHASE15.md) and the tracked setup requirements. The demo and tests
use no paid API, hosting or deployment. A live AI worker and independently
demonstrated software improvement remain absent.
