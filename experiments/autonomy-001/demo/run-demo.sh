#!/bin/bash
# OPENLINE-AUTONOMY-001 Phase 1 demonstration.
# End-to-end in fresh state dirs (nothing committed, nothing published):
#   1. mission cycles with worker-alpha (2 accepts)
#   2. worker replacement: worker-beta continues the same mission
#      (hold, reject, quarantine)
#   3. crash-resume: halt after build, then resume to completion
#   4. owner revocation stops the loop
#   5. naive baseline: direct-apply the adversarial patch, no evaluation
set -u
EXP="$(cd "$(dirname "$0")/.." && pwd)"
export AUTONOMY_TARGET_REPO="/tmp/rd/bureau"
S="/tmp/autonomy-001-demo"
rm -rf "$S"; mkdir -p "$S"
LOG="$S/demo.log"

run() { echo "\$ $*" | tee -a "$LOG"; "$@" 2>&1 | tee -a "$LOG"; }

echo "=== OPENLINE-AUTONOMY-001 Phase 1 demo ===" | tee "$LOG"

echo -e "\n--- 1+2. Mission cycles: alpha does 2, beta takes over for 3 ---" | tee -a "$LOG"
run python3 "$EXP/coordinator.py" --once --cycles 2 --worker worker-alpha \
    --state-dir "$S/main"
run python3 "$EXP/coordinator.py" --once --cycles 3 --worker worker-beta \
    --state-dir "$S/main"

echo -e "\n--- 3. Crash-resume ---" | tee -a "$LOG"
rm -rf "$S/resume"
run python3 "$EXP/coordinator.py" --once --cycles 1 --worker worker-alpha \
    --state-dir "$S/resume" --stop-after-phase build || true
run python3 "$EXP/coordinator.py" --once --cycles 1 --worker worker-alpha \
    --state-dir "$S/resume"

echo -e "\n--- 4. Owner revocation ---" | tee -a "$LOG"
rm -rf "$S/revoke"
cp "$EXP/mission.yaml" /tmp/mission-backup.yaml
python3 -c "
import yaml
p = '$EXP/mission.yaml'
d = yaml.safe_load(open(p).read()); d['revoked'] = True
open(p, 'w').write(yaml.safe_dump(d))"
run python3 "$EXP/coordinator.py" --once --cycles 1 --worker worker-alpha \
    --state-dir "$S/revoke"
cp /tmp/mission-backup.yaml "$EXP/mission.yaml"
echo "(mission.yaml restored to revoked: false)" | tee -a "$LOG"

echo -e "\n--- 5. Naive baseline: apply adversarial patch with no evaluation ---" | tee -a "$LOG"
BS="$S/baseline"; rm -rf "$BS"
git clone -q /tmp/rd/bureau "$BS" 2>/dev/null
git -C "$BS" checkout -q 24f5609
python3 -c "
p = '$BS/experiments/review-desk-001/review.py'
t = open(p).read()
assert t.count('result[\"classification\"] = ADDRESSED') == 1
open(p, 'w').write(t.replace('result[\"classification\"] = ADDRESSED',
                             'result[\"classification\"] = NO_CLAIM'))
print('naive baseline: worker output applied directly, no evaluation')"
(cd "$BS/experiments/review-desk-001" && python3 -m unittest discover -s tests 2>&1 | tail -3) | tee -a "$LOG"
echo "(the coordinator REJECTED this same change in step 1-2)" | tee -a "$LOG"

echo -e "\n=== summary ===" | tee -a "$LOG"
python3 - "$S/main" <<'EOF' | tee -a "$LOG"
import json, sys
s = json.load(open(sys.argv[1] + "/state.json"))
print("task outcomes:", {k: v["status"] for k, v in s["tasks"].items()})
print("cycles completed:", s["cycles_completed"])
print("receipts:", len(s["receipts"]))
EOF
git -C "$S/main/scratch" branch --list "autonomy-001/accepted/*" | tee -a "$LOG"
echo "dashboard: $S/main/dashboard.html" | tee -a "$LOG"
