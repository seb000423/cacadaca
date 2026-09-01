#!/usr/bin/env bash
# 과부하 실패 셀 재실행 — 감압(힘 ×0.7) + 소형 패드(반경 0.035 m). 결과는 별도 CSV(원 순회 데이터 보존).
#   setsid nohup bash learning/rl/robot/results/rerun_overload.sh > learning/rl/robot/results/rerun_overload.log 2>&1 &
set -u
cd /home/rokey/Desktop/cacadaca
PY=${ISAAC_PY:-$HOME/isaacsim/python.sh}
CKPT=learning/rl/robot/champion/model_ppo_curved.pt
OUT=${OUT:-learning/rl/robot/results/car_cells_rerun.csv}
LIST=${LIST:-learning/rl/robot/results/overload_cells.txt}
FS=${FS:-0.7}; PR=${PR:-0.035}; TAG=${TAG:-pad0.035_f0.7}; BATCH=${BATCH:-16}
IFS=',' read -r -a IDS < "$LIST"
# 이미 결과가 있는 셀은 건너뛴다(재개 가능)
done_ids=""; [ -f "$OUT" ] && done_ids=$(awk -F, 'NR>1{print $1}' "$OUT" | tr '\n' ',')
todo=(); for id in "${IDS[@]}"; do case ",$done_ids" in *",$id,"*) ;; *) todo+=("$id");; esac; done
echo "[rerun] $(date +%H:%M:%S) 대상 ${#IDS[@]}셀, 남은 ${#todo[@]}셀 (force×$FS, pad $PR m, tag $TAG)"
i=0; n=${#todo[@]}
while [ "$i" -lt "$n" ]; do
  chunk=("${todo[@]:$i:$BATCH}"); cells=$(IFS=','; echo "${chunk[*]}")
  echo "[rerun] $(date +%H:%M:%S) 배치 시작: $cells"
  timeout 3600 "$PY" learning/rl/car_cells_robot.py --headless --checkpoint "$CKPT" \
      --cells "$cells" --num_envs "${#chunk[@]}" --out "$OUT" \
      --force_scale "$FS" --pad_radius "$PR" --tag "$TAG" 2>&1 | grep -E "\[car_cells\]|Traceback|Error\]" | grep -v "omni.kit.app"
  echo "[rerun] $(date +%H:%M:%S) 배치 종료 (누적 행: $(( $(wc -l < "$OUT" 2>/dev/null || echo 1) - 1 )))"
  i=$(( i + BATCH ))
done
echo "[rerun] 완료 → $OUT"
