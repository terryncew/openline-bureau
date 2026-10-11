#!/usr/bin/env bash
# Phase 1.5: one deterministic, owner-preauthorized cycle in fresh local state.
# No model/API invocation. No existing state is deleted or mission file edited.
set -euo pipefail
umask 077
EXP="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
export AUTONOMY_TARGET_REPO="$(cd "$EXP/../.." && pwd)"
PRIVATE_BASE="$("$PYTHON_BIN" -I - "$AUTONOMY_TARGET_REPO" "${TMPDIR:-/tmp}" <<'CHECK'
from pathlib import Path
import sys
repo, base = (Path(value).expanduser().resolve() for value in sys.argv[1:])
if base == repo or repo in base.parents:
    raise SystemExit('TMPDIR must be outside the checkout; no state was created.')
print(base)
CHECK
)"
STATE="$(mktemp -d "$PRIVATE_BASE/autonomy-001-demo.XXXXXX")"
# State contains private signing keys. Retain it locally for review/recovery;
# never publish the directory, copy host auth into it, or reuse it for a model.
echo "Private local state: $STATE"
"$PYTHON_BIN" "$EXP/coordinator.py" --once --cycles 1 --worker worker-alpha \
    --state-dir "$STATE" 2>&1 | tee "$STATE/demo.log"
"$PYTHON_BIN" - "$STATE" <<'CHECK'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
state = json.loads((root / 'state.json').read_text())
assert state['cycles_completed'] == 1, state
assert state['tasks']['ui-empty-records']['status'] == 'accepted', state
print('Verified: one scripted UI task accepted in the isolated scratch clone.')
print('No live coding agent or measured software improvement was demonstrated.')
print('Receipts:', len(state['receipts']))
print('Local dashboard:', root / 'dashboard.html')
CHECK
