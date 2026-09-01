"""차 전체 결과 리플레이 기록 생성 — 483셀 순회 결과(car_cells_best.csv)를 로봇 3대가 순서대로 닦는 SimRecorder 기록으로.

동작은 근사(실기록 run 8 의 실제 폴리싱 자세·베이스 높이 사용, 베이스가 셀 위치로 이동), 판정·처분·공정시간은 실제 값.
시간축 = 실제 공정시간(셀당 309 s 기준 레시피, 과부하 트립 셀 45 s) → 총 ≈ 18 h, 콘솔에서 64~128× 재생.
    python3 learning/ui_bridge/make_car_replay.py [--out learning/ui_bridge/out/run_car_replay.sqlite]
"""
import argparse, csv, math, os, sys, statistics as st
_HERE = os.path.dirname(os.path.abspath(__file__)); _REPO = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _REPO)
from learning.ui_bridge.sim_recorder import SimRecorder

ap = argparse.ArgumentParser()
ap.add_argument("--cells", default=os.path.join(_REPO, "learning", "rl", "robot", "results", "car_cells_best.csv"))
ap.add_argument("--out", default=os.path.join(_HERE, "out", "run_car_replay.sqlite"))
ap.add_argument("--cell_s", type=float, default=309.0, help="합격/일반 셀 공정시간(s) — 기준 레시피 150셀 평균")
ap.add_argument("--trip_s", type=float, default=45.0, help="과부하 트립 셀(passes=0) 소요(s)")
ap.add_argument("--hz", type=float, default=1.0)
a = ap.parse_args()

CAR_LIFT_Z = 0.90                       # v5 월드 = 스캔 좌표 + 리프트
SCENE = {"up": "z", "long": "y", "car_min": [-0.6652, -1.5103, 1.0154], "car_max": [0.6672, 1.5278, 1.8722]}   # run 8 실측 bbox
# run 8(실제 Isaac) 폴리싱 중 평균 자세·베이스·자세 쿼터니언(w,x,y,z)
POSE = {"C":  {"q": [-2.056, -0.464, 1.332, 1.149, -0.916, 1.877], "z": 2.084, "quat": [0.0, 0.70711, 0.70711, 0.0], "x": None},
        "SL": {"q": [-1.547, -2.326, 0.946, 1.796, 0.681, -1.849], "z": 1.346, "quat": [0.70711, 0.0, 0.0, -0.70711], "x": -1.36},
        "SR": {"q": [-1.591, -2.358, 1.020, 1.366, -0.638, -1.265], "z": 1.31, "quat": [0.70711, 0.0, 0.0, 0.70711], "x": 1.36}}
CARRY_Q = [0.0, -1.05, 1.45, 0.0, 1.15, 0.0]
TARGET = {"C": 6.69, "SL": 8.30, "SR": 8.30}
SLIDE_V = 0.30      # m/s 레일 이동
APPROACH_S = 8.0

rows = list(csv.DictReader(open(a.cells, encoding="utf-8")))
def robot_of(r):
    reg = r["region"]; x = float(r["center_x_m"])
    if reg == "top": return "C"
    if reg == "side_left": return "SL"
    if reg == "side_right": return "SR"
    return "SL" if x < 0 else "SR"          # 전·후면은 가까운 쪽 측면 로봇
plan = {"C": [], "SL": [], "SR": []}
for r in sorted(rows, key=lambda r: int(r["cell_id"])):
    plan[robot_of(r)].append(r)

def cell_time(r):
    if r["outcome"] == "fail_force_overload" and float(r["passes"] or 0) == 0: return a.trip_s
    return a.cell_s * max(1.0, float(r["passes"] or 1))

def cell_normal(r):
    """셀 법선 근사: 면 분류의 바깥 방향과 tilt(법선-수직 각)로 합성 — CSV 에 법선이 없다."""
    import math as _m
    reg = r["region"]; tilt = _m.radians(float(r.get("tilt_deg") or 0.0))
    out = {"side_left": (-1, 0, 0), "side_right": (1, 0, 0), "front": (0, 1, 0), "rear": (0, -1, 0)}.get(reg)
    if out is None:   # 윗면: 차 중심에서 바깥으로 살짝 기운 위쪽
        cx, cy = float(r["center_x_m"]), float(r["center_y_m"]); n = _m.hypot(cx, cy) or 1.0
        out = (cx / n, cy / n, 0.0)
    v = [out[0] * _m.sin(tilt), out[1] * _m.sin(tilt), _m.cos(tilt)]
    n = _m.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]

def base_for(rid, r):
    cx, cy, cz = float(r["center_x_m"]), float(r["center_y_m"]), float(r["center_z_m"]) + CAR_LIFT_Z
    if rid == "C": return [0.0, cy, POSE["C"]["z"]]      # 천장 로봇은 갠트리 중앙(x=0)을 따라 y 로만 이동 — 옆으로는 팔이 뻗는다 (Isaac 과 동일)
    y = cy - 0.35 if r["region"] == "front" else cy + 0.35 if r["region"] == "rear" else cy
    return [POSE[rid]["x"], max(-1.9, min(1.9, y)), max(1.05, min(1.6, cz + 0.15))]

# 로봇별 타임라인: [(t0, t1, state, cell or None, base_from, base_to)]
timelines = {}
for rid, cells in plan.items():
    t = 0.0; tl = []; prev = [POSE[rid]["x"] if POSE[rid]["x"] is not None else 0.0, 1.9, POSE[rid]["z"]]
    for r in cells:
        b = base_for(rid, r); d = math.dist(prev, b); ts = max(3.0, d / SLIDE_V)
        tl.append((t, t + ts, "SLIDE", None, prev, b)); t += ts
        tl.append((t, t + APPROACH_S, "APPROACH", r, b, b)); t += APPROACH_S
        tp = cell_time(r); tl.append((t, t + tp, "POLISH", r, b, b)); t += tp
        tl.append((t, t + 3.0, "RETRACT", r, b, b)); t += 3.0
        prev = b
    tl.append((t, t + 1e9, "DONE", None, prev, prev))
    timelines[rid] = tl
T_END = max(tl[-2][1] for tl in timelines.values())
print(f"cells C={len(plan['C'])} SL={len(plan['SL'])} SR={len(plan['SR'])}  total sim time {T_END/3600:.1f} h")

disp_k = {"pass": "합격", "spot_repaint_review": "스팟 재도장 검토", "rework_candidate": "재작업 후보"}
rec = SimRecorder(a.out, meta={"scene": SCENE, "hz": a.hz, "robots": [{"id": "C", "name": "천장"}, {"id": "SL", "name": "좌측"}, {"id": "SR", "name": "우측"}],
                              "recipe": {"replay_of": os.path.basename(a.cells)}, "rl": True, "physical_contact": True,
                              "recipe_values": {"force_n": 6.69, "feed_mm_s": 5.65, "rpm": 3259, "step_over_ratio": 0.27, "n_passes": 2, "pad_radius_m": 0.055, "robots": ["C", "SL", "SR"]},
                              "params": {"robotCount": 3, "hasRail": True, "hasLift": True, "tool": "dual", "pad": 110, "carLift": 0, "recipe": "base"},
                              "kind": "result_replay"}, chunk_s=60.0)
idx = {rid: 0 for rid in plan}; done_cells = []; done_ids = set(); last_snap = 0
n_total = len(rows); dt = 1.0 / a.hz; t = 0.0; nf = 0
while t <= T_END + 1.0:
    robots = []
    for rid in ("C", "SL", "SR"):
        tl = timelines[rid]
        while idx[rid] < len(tl) - 1 and t >= tl[idx[rid]][1]: idx[rid] += 1
        t0, t1, state, r, b0, b1 = tl[idx[rid]]
        u = 0.0 if t1 - t0 <= 0 or t1 > 1e8 else max(0.0, min(1.0, (t - t0) / (t1 - t0)))
        base = [b0[i] + (b1[i] - b0[i]) * u for i in range(3)] if state == "SLIDE" else list(b1)
        tcp = None; nrm = None; q = None
        if r is not None and state in ("APPROACH", "POLISH", "RETRACT"):
            c = [float(r["center_x_m"]), float(r["center_y_m"]), float(r["center_z_m"]) + CAR_LIFT_Z]
            nrm = cell_normal(r)
            if state == "POLISH":
                # 셀 안에서 12 cm 래스터(왕복) — 패드가 셀을 훑는 것처럼
                ph = (t - t0) / max(1.0, t1 - t0); lane = math.sin(2 * math.pi * 6 * ph) * 0.05
                side = [-nrm[1], nrm[0], 0.0]; sn = math.sqrt(side[0] ** 2 + side[1] ** 2) or 1.0
                tcp = [c[i] + side[i] / sn * lane for i in range(3)]
                force = TARGET[rid] * (1.0 + 0.06 * math.sin(2 * math.pi * 0.7 * t + hash(rid) % 7))
            else:
                hover = 0.15 * ((1 - u) if state == "APPROACH" else u)     # 법선 방향으로 내려오고/올라감
                tcp = [c[i] + nrm[i] * hover for i in range(3)]
                force = 0.0
        else:
            q = CARRY_Q; force = 0.0
        done_n = sum(1 for k in range(idx[rid]) if tl[k][2] == "RETRACT")
        rob = {"id": rid, "force": force, "target": TARGET[rid], "state": state, "progress": done_n / max(1, len(plan[rid])),
               "rl_force_scale": 1.0, "rl_feed_scale": 1.0, "base": {"pos": base, "quat": POSE[rid]["quat"]}}
        if q is not None: rob["q"] = q
        if tcp is not None: rob["tcp"] = tcp; rob["normal"] = nrm
        robots.append(rob)
        # 셀 완료 시각(RETRACT 시작) 에 판정 기록
        if state == "RETRACT" and r is not None and r["cell_id"] not in done_ids:
            done_ids.add(r["cell_id"]); done_cells.append(r)
            rec.event(t, rid, "info" if r["disposition"] == "pass" else "warn",
                      f"셀 {r['cell_id']} {r['region']}: {disp_k.get(r['disposition'], r['disposition'])} · GU {float(r['gu_final']):.1f} · CC {float(r['clearcoat_min_um']):.1f} μm"
                      + (" · 과부하 트립" if r["outcome"] == "fail_force_overload" else ""))
    prog = len(done_cells) / n_total
    overall = "DONE" if prog >= 1.0 else "POLISH"
    rec.frame(t, overall, prog, t, robots)
    if len(done_cells) - last_snap >= 10 or (prog >= 1.0 and last_snap != len(done_cells)):
        last_snap = len(done_cells)
        rec.cells(t, {"total": n_total, "pass": sum(1 for c in done_cells if c["disposition"] == "pass"),
                      "rework": sum(1 for c in done_cells if c["disposition"] == "rework_candidate"),
                      "repaint": sum(1 for c in done_cells if c["disposition"] == "spot_repaint_review"),
                      "not_reached": n_total - len(done_cells),
                      "items": [[float(c["center_x_m"]), float(c["center_y_m"]), float(c["center_z_m"]) + CAR_LIFT_Z, c["disposition"], float(c["gu_final"])] for c in done_cells]})
    t += dt; nf += 1
passc = [c for c in rows if c["disposition"] == "pass"]
res = {"ts": 0, "tag": "car_result_replay", "sim_step": int(T_END * 60), "elapsed_s": T_END,
       "recipe": {"force": 6.69, "feed_mm_s": 5.65, "rpm": 3259, "spacing_ratio": 0.27, "n_passes": 2},
       "cells": {"cells": n_total, "polished": n_total, "pass": len(passc), "spot_repaint_review": sum(1 for c in rows if c["disposition"] == "spot_repaint_review"),
                 "rework_candidate": sum(1 for c in rows if c["disposition"] == "rework_candidate"), "not_reached": 0},
       "quality": {"cells": n_total, "ra": st.mean(float(c["ra_final_um"]) for c in rows), "rz": st.mean(float(c["rz_final_um"]) for c in rows),
                   "clearcoat": st.mean(float(c["clearcoat_min_um"]) for c in rows), "scratch": st.mean(float(c["scratch_final_um"]) for c in rows),
                   "scratchBefore": st.mean(float(c["scratch_before_um"]) for c in rows), "glossMean": st.mean(float(c["gu_final"]) for c in rows),
                   "glossP10": sorted(float(c["gu_final"]) for c in rows)[n_total // 10], "glossStd": st.pstdev(float(c["gu_final"]) for c in rows),
                   "glossMin": min(float(c["gu_final"]) for c in rows), "glossTiles": n_total, "glossPass": len(passc) / n_total >= 0.6, "glossBand": "sweep_2026-09-01"},
       "rl": {"force": 6.69, "force_scale_mean": 1.0, "feed_scale_mean": 1.0, "stiffness": 350, "damping": 35, "robots": 3}}
rec.finish(res); rec.close()
print(f"frames {nf}, cells {len(done_cells)}/{n_total}, sim {T_END/3600:.1f} h → {a.out} ({os.path.getsize(a.out)/1e6:.1f} MB)")
