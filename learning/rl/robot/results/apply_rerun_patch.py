"""순회 종료 후 적용: car_cells_robot.py 에 강곡률 셀 재실행 옵션 추가.
  --force_scale S   레시피 목표 힘 × S (감압; 임시 레시피 JSON 으로 env 에 전달)
  --pad_radius R    물리 패드 반경(m) 재정의 (v5 common + env + polytwin PC 상수) — 소형 패드
  --tag TXT         checkpoint 열에 붙일 실행 태그 (예: pad0.035_f0.7)
"""
p = "/home/rokey/Desktop/cacadaca/learning/rl/car_cells_robot.py"
s = open(p).read()
def rep(old, new):
    global s
    assert s.count(old) == 1, old[:70]; s = s.replace(old, new)

rep('''parser.add_argument("--registry_seed", type=int, default=7000)''',
'''parser.add_argument("--registry_seed", type=int, default=7000)
parser.add_argument("--force_scale", type=float, default=1.0,
                    help="강곡률 재실행: 레시피 목표 힘 배율 (감압, 예 0.7)")
parser.add_argument("--pad_radius", type=float, default=None,
                    help="강곡률 재실행: 물리 패드 반경 m (예 0.035 = Ø70 소형 패드)")
parser.add_argument("--tag", type=str, default="", help="결과 checkpoint 열에 붙일 태그")''')

rep('''    env_cfg = RobotPolishEnvCfg()
    env_cfg.surface_kind = "quad"''',
'''    env_cfg = RobotPolishEnvCfg()
    # ── 강곡률 재실행 옵션 (2026-09-01): 감압 / 소형 패드 ──
    if args.force_scale != 1.0:
        import json, tempfile
        from learning.rl.env.polish_env import _load_recipe
        base = _load_recipe(env_cfg.recipe_json_path)
        d = json.load(open(env_cfg.recipe_json_path))
        key = "target_contact_force_n"
        d[key] = float(base.target_contact_force_n * args.force_scale)
        tmp = tempfile.NamedTemporaryFile("w", suffix="_recipe.json", delete=False)
        json.dump(d, tmp); tmp.close()
        env_cfg.recipe_json_path = tmp.name
        print(f"[car_cells] 감압: 목표 힘 {base.target_contact_force_n:.2f} → {d[key]:.2f} N ({args.force_scale}×)")
    if args.pad_radius is not None:
        import scripts.polishing_v5_modules.common as _v5c
        import learning.rl.env.robot_polish_env as _rpe
        from learning.polytwin import config as _PC
        _v5c.POLISHING_DISK_RADIUS = float(args.pad_radius)
        _rpe.POLISHING_DISK_RADIUS = float(args.pad_radius)
        _PC.PAD_RADIUS_M = float(args.pad_radius); _PC.PAD_DIAMETER_M = 2.0 * float(args.pad_radius)
        print(f"[car_cells] 소형 패드: 물리 반경 {args.pad_radius} m (footprint/raster 도 동일; "
              f"제거 모델 pad_radius 는 보정 설정값 유지 — 주의)")
    env_cfg.surface_kind = "quad"''')

rep('''                "checkpoint": os.path.basename(args.checkpoint),''',
'''                "checkpoint": os.path.basename(args.checkpoint) + (f"|{args.tag}" if args.tag else ""),''')
open(p, "w").write(s)
print("rerun patch applied to car_cells_robot.py")
