#!/usr/bin/env bash
# Local development dependencies only. No worker, model call, or ref update.
set -euo pipefail
umask 077

SETUP_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SETUP_DIR/../../.." && pwd)"
IMAGE='python@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce'
WALLET_COMMIT='c46e82a324199050239540f1825a3b0c942e4053'
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV=''
WALLET=''
PULL_IMAGE=1

usage() {
    echo 'Usage: setup.sh --venv /absolute/path [--wallet-repo /absolute/path] [--skip-image-pull]'
    echo 'Python 3.12+, Git, and a working Docker daemon are required.'
    echo 'Destinations must be outside this checkout. Existing unowned venvs are refused.'
}

while (($#)); do
    case "$1" in
        --venv|--wallet-repo)
            if (($# < 2)); then usage >&2; exit 2; fi
            if [[ "$1" == '--venv' ]]; then VENV="$2"; else WALLET="$2"; fi
            shift 2 ;;
        --skip-image-pull) PULL_IMAGE=0; shift ;;
        --help|-h) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done
if [[ -z "$VENV" ]]; then usage >&2; exit 2; fi
command -v git >/dev/null
command -v docker >/dev/null
# The controller's tar extraction filter and tested host toolchain need 3.12+.
"$PYTHON_BIN" -I -c 'import os,sys; assert sys.version_info >= (3, 12), "Python 3.12+ required"; assert os.getuid()!=0, "Run as a non-root user with Docker access"'
docker info >/dev/null

# Refuse writes into the checkout and avoid an accidental install into a
# preexisting virtualenv. A marker allows repeat setup of only our own venv.
VENV="$("$PYTHON_BIN" -I -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve())' "$VENV")"
if [[ -n "$WALLET" ]]; then
    WALLET="$("$PYTHON_BIN" -I -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve())' "$WALLET")"
fi
for dest in "$VENV" "$WALLET"; do
    if [[ -n "$dest" && ( "$dest" == "$REPO" || "$dest" == "$REPO/"* ) ]]; then
        echo 'Setup destinations must be outside the checkout.' >&2; exit 2
    fi
done
if [[ -n "$WALLET" && ( "$WALLET" == "$VENV" || "$WALLET" == "$VENV/"* || "$VENV" == "$WALLET/"* ) ]]; then
    echo 'Wallet and virtualenv destinations must not overlap.' >&2; exit 2
fi
MARKER="$VENV/.openline-phase15-setup"
if [[ -e "$VENV" ]]; then
    if [[ ! -f "$MARKER" || "$(cat "$MARKER")" != 'openline-autonomy-001-phase15-v1' ]]; then
        echo 'Existing virtualenv destination is not owned by this setup; choose a new path.' >&2; exit 2
    fi
else
    "$PYTHON_BIN" -I -m venv "$VENV"
    echo 'openline-autonomy-001-phase15-v1' > "$MARKER"
fi
unset PYTHONPATH
PY="$VENV/bin/python"
"$PY" -I -m pip install --require-virtualenv --disable-pip-version-check \
    -r "$SETUP_DIR/requirements-build.txt"
# Build isolation is intentionally disabled only after installing the exact
# declared build tools above, so upstream lower bounds do not drift over time.
"$PY" -I -m pip install --require-virtualenv --disable-pip-version-check \
    --no-build-isolation --no-deps -r "$SETUP_DIR/requirements.txt"

if [[ -n "$WALLET" ]]; then
    if [[ ! -e "$WALLET" ]]; then
        git -c core.hooksPath=/dev/null clone --quiet --no-checkout \
            https://github.com/terryncew/openline-wallet.git "$WALLET"
        git -C "$WALLET" -c core.hooksPath=/dev/null checkout --quiet --detach "$WALLET_COMMIT"
    fi
    if [[ "$(git -C "$WALLET" rev-parse HEAD)" != "$WALLET_COMMIT" || \
          -n "$(git -C "$WALLET" status --porcelain)" ]]; then
        echo 'Wallet destination must be a clean checkout of the pinned commit; it was not changed.' >&2; exit 2
    fi
    "$PY" -I -m pip install --require-virtualenv --disable-pip-version-check \
        --no-build-isolation --no-deps "$WALLET"
fi
"$PY" -I -m pip check

if ((PULL_IMAGE)); then docker pull "$IMAGE"; fi
docker image inspect "$IMAGE" >/dev/null
"$PY" -I - "$REPO" "$IMAGE" <<'PY'
from pathlib import Path
import sys, tempfile
sys.path.insert(0, str(Path(sys.argv[1]) / 'experiments/autonomy-001'))
import integrations as IN
assert IN.IMAGE == sys.argv[2], 'setup image differs from the runtime image'
with tempfile.TemporaryDirectory(prefix='phase15-setup-check-') as temp:
    result = IN.isolated_run(Path(temp), ['python', '-I', '-c', 'print("PHASE15_SANDBOX_READY")'], 10)
    assert result['exit_code'] == 0 and not result['timed_out'], result
    assert 'PHASE15_SANDBOX_READY' in result['stdout_tail'], result
print('Pinned dependencies and offline Docker execution verified.')
PY
echo "Virtualenv: $VENV"
if [[ -n "$WALLET" ]]; then echo "Wallet: $WALLET ($WALLET_COMMIT)"; fi
echo 'Run checks from the Bureau checkout with the virtualenv Python; no model route is configured.'
