#!/usr/bin/env bash
# 순차: ① 클로즈업 재녹화(패드 실제 손목 부착판) → 인코딩 ② 차 전체 491셀 순회 (16셀/배치)
cd /home/rokey/Desktop/cacadaca
PY=$HOME/isaacsim/python.sh
echo "[overnight] $(date +%F_%T) 클로즈업 재녹화 시작"
rm -rf learning/rl/logs/demo_rec/close && mkdir -p learning/rl/logs/demo_rec/close
$PY learning/rl/demo_arm.py --headless --enable_cameras --num_envs 2 --all_policy --checkpoint learning/rl/champion/model_terminal_ppo_14ch_it800.pt --surface_kinds flat,cylinder --env_spacing 1.4 --cam_preset close --cam_dist_scale 0.75 --cam_focal 21 --no_status --n_passes 2 --record_res 1920x1080 --record learning/rl/logs/demo_rec/close --record_dt 0.3 --max_seconds 960 > learning/rl/logs/demo_rec/close.log 2>&1
if grep -q "시연 결과" learning/rl/logs/demo_rec/close.log; then
  ffmpeg -y -loglevel error -framerate 30 -i learning/rl/logs/demo_rec/close/frame_%05d.png -c:v libx264 -pix_fmt yuv420p -crf 19 -movflags +faststart /home/rokey/Desktop/polish_demo_close_2robots.mp4 && echo "[overnight] 클로즈업 인코딩 완료"
fi
echo "[overnight] $(date +%F_%T) 차 전체 셀 순회 시작"
rm -f learning/rl/robot/results/car_cells.csv
bash learning/rl/run_car_cells.sh 0 490 16 learning/rl/robot/champion/model_ppo_curved.pt learning/rl/robot/results/car_cells.csv
echo "[overnight] $(date +%F_%T) 완료"
