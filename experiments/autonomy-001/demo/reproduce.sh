#!/usr/bin/env bash
# Public research reproduction: pinned setup and one scripted offline cycle.
# All generated files, including private runtime keys, stay outside checkout.
set -euo pipefail
umask 077

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
EXP="$(cd "$DEMO_DIR/.." && pwd)"
REPO="$(cd "$EXP/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if (($#)); then
    if [[ "$1" == '--help' && "$#" == 1 ]]; then
        echo 'Usage: bash experiments/autonomy-001/demo/reproduce.sh'
        echo 'Requires Linux, Python 3.12+ with venv, Git, and Docker.'
        echo 'Optional: PYTHON_BIN selects the host Python; TMPDIR selects private storage outside checkout.'
        echo 'Installs pinned dependencies and runs one scripted cycle; no live AI or paid API call.'
        exit 0
    fi
    echo 'No arguments are accepted; use --help for prerequisites.' >&2
    exit 2
fi

command -v "$PYTHON_BIN" >/dev/null
command -v git >/dev/null
command -v docker >/dev/null
# Check the destination before mktemp creates anything. The demo's state and
# setup's virtualenv share this private parent, never the public checkout.
PRIVATE_BASE="$("$PYTHON_BIN" -I - "$REPO" "${TMPDIR:-/tmp}" <<'CHECK'
from pathlib import Path
import sys
if sys.version_info < (3, 12):
    raise SystemExit('Python 3.12+ required.')
repo = Path(sys.argv[1]).resolve()
base = Path(sys.argv[2]).expanduser().resolve()
if base == repo or repo in base.parents:
    raise SystemExit('TMPDIR must be outside the checkout; no files were created.')
if not base.is_dir():
    raise SystemExit('TMPDIR must be an existing directory.')
print(base)
CHECK
)"
PRIVATE_RUN_DIR="$(mktemp -d "$PRIVATE_BASE/openline-research.XXXXXX")"
mkdir -m 700 "$PRIVATE_RUN_DIR/runtime"
export TMPDIR="$PRIVATE_RUN_DIR/runtime"
echo "Private workspace: $PRIVATE_RUN_DIR"
echo 'Preparing a scripted research demonstration; no live AI or paid API call.'

bash "$EXP/setup/setup.sh" --venv "$PRIVATE_RUN_DIR/venv"
unset PYTHONPATH
export PYTHON_BIN="$PRIVATE_RUN_DIR/venv/bin/python"
bash "$DEMO_DIR/run-demo.sh"
echo "Private workspace retained for inspection: $PRIVATE_RUN_DIR"
echo 'This run does not establish measured software improvement or production security.'

