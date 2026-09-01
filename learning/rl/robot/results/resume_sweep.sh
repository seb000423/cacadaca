#!/usr/bin/env bash
# 차 전체 셀 순회 재개: car_cells.csv 에 이미 있는 셀은 건너뛰고 다음 셀부터 16셀 배치로 계속.
#   bash learning/rl/robot/results/resume_sweep.sh      (독립 프로세스로 띄우려면 setsid nohup ... &)
cd "$(dirname "$0")/../../../.."
OUT=learning/rl/robot/results/car_cells.csv
LOG=learning/rl/robot/results/overnight.log
NEXT=$(python3 - "$OUT" << 'PY'
import csv, sys, os
p = sys.argv[1]
done = {int(r["cell_id"]) for r in csv.DictReader(open(p))} if os.path.exists(p) else set()
n = 0
while n in done: n += 1
print(n)
PY
)
echo "[resume] $(date +%F_%T) 완료 $(( $(wc -l < "$OUT") - 1 ))셀, 셀 $NEXT 부터 재개" | tee -a "$LOG"
bash learning/rl/run_car_cells.sh "$NEXT" 490 16 learning/rl/robot/champion/model_ppo_curved.pt "$OUT" 2>&1 | tee -a "$LOG"
echo "[resume] $(date +%F_%T) 완료" | tee -a "$LOG"
