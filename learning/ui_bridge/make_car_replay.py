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
ap.add_argument("--no_ik", action="store_true", help="오프라인 IK 없이(콘솔 IK 사용) — 검증용")
a = ap.parse_args()
IK = None
if not a.no_ik:
    try:
        from learning.ui_bridge.replay_ik import ArmIK, base_T, fk
        from scripts.path_generator import load_ply_points
        import numpy as _np
        _pts = _np.asarray(load_ply_points(os.path.join(_REPO, "scan_result", "car", "points", "real_camera_surface_points.ply")), float)
        _pts[:, 2] += 0.90     # 리프트
        IK = ArmIK(_pts[::2], clearance=0.07)
        print(f"offline IK on: car points {len(_pts)//2}")
    except Exception as exc:
        print(f"offline IK unavailable ({exc}) → 콘솔 IK 사용"); IK = None

CAR_LIFT_Z = 0.90                       # v5 월드 = 스캔 좌표 + 리프트
SCENE = {"up": "z", "long": "y", "car_min": [-0.6652, -1.5103, 1.0154], "car_max": [0.6672, 1.5278, 1.8722],   # run 8 실측 bbox
         "gantry_beam_z": 3.65, "gantry_half_x": 1.36, "gantry_half_y": 3.20, "overhead_z": [2.05, 2.85],
         "rail_x": [-1.36, 1.36], "lift_h": [0.83, 1.70], "car_lift_z": 0.90}   # v5 common.py 상수
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
for r in rows:
    plan[robot_of(r)].append(r)

def boustrophedon(cells, band_key, sweep_key, band_w):
    """면을 띠(band)로 나눠 한 띠씩 왕복하며 훑는 순서 — Isaac 경로 생성기(레인 래스터)와 같은 진행 모양."""
    bands = {}
    for c in cells:
        bands.setdefault(round(band_key(c) / band_w), []).append(c)
    out = []
    for i, k in enumerate(sorted(bands)):
        seg = sorted(bands[k], key=sweep_key)
        out.extend(seg if i % 2 == 0 else seg[::-1])
    return out

def order_for(rid, cells):
    y = lambda c: float(c["center_y_m"]); x = lambda c: float(c["center_x_m"]); z = lambda c: float(c["center_z_m"])
    if rid == "C":   # 윗면: 앞→뒤 띠(0.24 m)마다 x 왕복
        return boustrophedon(cells, y, x, 0.24)[::-1]
    side = [c for c in cells if c["region"] in ("side_left", "side_right")]
    ends = [c for c in cells if c["region"] in ("front", "rear")]
    front = sorted([c for c in ends if c["region"] == "front"], key=lambda c: (round(z(c) / 0.24), x(c)))
    rear = sorted([c for c in ends if c["region"] == "rear"], key=lambda c: (round(z(c) / 0.24), -x(c)))
    # 앞면 → 옆면(앞→뒤, 높이 띠마다 y 왕복) → 뒷면 : 레일을 한 방향으로 훑는다
    return front + boustrophedon(side, z, y, 0.24) + rear

for rid in plan:
    plan[rid] = order_for(rid, plan[rid])

def cell_time(r):
    if r["outcome"] == "fail_force_overload" and float(r["passes"] or 0) == 0: return a.trip_s
    return a.cell_s * max(1.0, float(r["passes"] or 1))

_NORMALS = {}
_np = os.path.join(_REPO, "learning", "rl", "robot", "results", "cell_normals.csv")
if os.path.exists(_np):
    for _r in csv.DictReader(open(_np, encoding="utf-8")):
        _NORMALS[_r["cell_id"]] = [float(_r["nx"]), float(_r["ny"]), float(_r["nz"])]

def cell_normal(r):
    """셀 법선: CellRegistry 실측(cell_normals.csv) 우선, 없으면 면 분류+tilt 로 합성."""
    import math as _m
    if r["cell_id"] in _NORMALS:
        n = _NORMALS[r["cell_id"]]
        return n if n[2] >= -0.2 or r["region"] != "top" else [-x for x in n]   # 바깥(위) 방향 보장
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
    if rid == "C":
        if r["region"] in ("front", "rear"):   # 범퍼: 갠트리 끝에서 낮게 내려와 앞/뒤에서 접근
            return [cx * 0.5, max(-2.2, min(2.2, cy + (0.55 if r["region"] == "front" else -0.55))), 2.05]
        return [0.0, cy, max(2.05, min(2.85, cz + 0.75))]   # 천장 로봇: 갠트리 중앙(x=0) y 이동, 높이는 셀 위 0.75 m (팔이 접혀 차를 뚫지 않게; Isaac 승강 범위 2.05~2.85)
    y = cy - 0.35 if r["region"] == "front" else cy + 0.35 if r["region"] == "rear" else cy
    return [POSE[rid]["x"], max(-1.9, min(1.9, y)), max(1.05, min(1.6, cz - 0.05))]   # 베이스를 셀 높이 근처에 — 팔이 수평으로 뻗어 차를 뚫지 않게

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

# ── 전·후면 셀 재배정: 측면 로봇(레일 끝)과 천장 로봇 중 도달(패드 오차)이 좋은 쪽 ──
if IK is not None:
    import numpy as _np
    moved = 0
    for rid in ("SL", "SR"):
        keep = []
        for r in plan[rid]:
            if r["region"] not in ("front", "rear"): keep.append(r); continue
            c = _np.array([float(r["center_x_m"]), float(r["center_y_m"]), float(r["center_z_m"]) + CAR_LIFT_Z])
            n = _np.array(cell_normal(r), float); n /= (_np.linalg.norm(n) or 1.0)
            e_side = IK.solve(base_T(base_for(rid, r), POSE[rid]["quat"]), c, n, _np.array(POSE[rid]["q"]))[1]
            e_top = IK.solve(base_T(base_for("C", r), POSE["C"]["quat"]), c, n, _np.array(POSE["C"]["q"]))[1]
            # 측면 로봇이 10 cm 이내로 못 닿을 때만 천장으로 — 공정시간(3대 병렬 균형)을 크게 흔들지 않게
            if e_side > 0.10 and e_top + 0.02 < e_side: plan["C"].append(r); moved += 1
            else: keep.append(r)
        plan[rid] = keep
    if moved:
        plan["C"] = order_for("C", [c for c in plan["C"] if c["region"] == "top"]) + [c for c in plan["C"] if c["region"] != "top"]
        print(f"front/rear cells moved to ceiling robot: {moved}")
    # 타임라인 재계산
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
    print(f"reassigned: C={len(plan['C'])} SL={len(plan['SL'])} SR={len(plan['SR'])}  total sim time {T_END/3600:.1f} h")

# ── 오프라인 IK: 셀마다 (접근 시작, 폴리싱 시작, 중간 −, 중간 +, 끝, 후퇴 끝) 관절 키프레임 ──
KEYQ = {}          # (rid, cell_id) → dict(app0, pol0, polm, polp, pol1, ret1)
if IK is not None:
    import numpy as _np
    stats = []
    for rid, cells in plan.items():
        seed = _np.array(POSE[rid]["q"], float); prev_q = seed.copy()
        for r in cells:
            c = _np.array([float(r["center_x_m"]), float(r["center_y_m"]), float(r["center_z_m"]) + CAR_LIFT_Z])
            n = _np.array(cell_normal(r), float); n /= (_np.linalg.norm(n) or 1.0)
            side = _np.array([-n[1], n[0], 0.0]); sn = _np.linalg.norm(side); side = side / sn if sn > 1e-6 else _np.array([1.0, 0, 0])
            Tb = base_T(base_for(rid, r), POSE[rid]["quat"])
            keys = {}
            q_app, e, d = IK.solve(Tb, c + n * 0.15, n, prev_q, w_clear=200.0); keys["app0"] = q_app
            q_p0, e0, d0 = IK.solve(Tb, c, n, q_app); keys["pol0"] = q_p0
            q_pm, _, _ = IK.solve(Tb, c - side * 0.03, n, q_p0); keys["polm"] = q_pm
            q_pp, _, _ = IK.solve(Tb, c + side * 0.03, n, q_p0); keys["polp"] = q_pp
            keys["pol1"] = q_p0; keys["ret1"] = q_app
            KEYQ[(rid, r["cell_id"])] = keys; prev_q = q_app
            stats.append((e0, d0))
    es = _np.array([x[0] for x in stats]); ds = _np.array([x[1] for x in stats])
    print(f"IK: {len(stats)} cells, pad error mean {es.mean()*1000:.1f} mm / median {_np.median(es)*1000:.1f} / max {es.max()*1000:.1f} mm, "
          f">5 cm: {(es > 0.05).sum()}, >15 cm: {(es > 0.15).sum()}; min link clearance mean {ds.mean()*100:.1f} cm, cells < 5 cm: {(ds < 0.05).sum()}")

def _lerp_q(qa, qb, u):
    return [float(qa[j] + (qb[j] - qa[j]) * u) for j in range(6)]
print(f"cells C={len(plan['C'])} SL={len(plan['SL'])} SR={len(plan['SR'])}  total sim time {T_END/3600:.1f} h")

disp_k = {"pass": "합격", "spot_repaint_review": "스팟 재도장 검토", "rework_candidate": "재작업 후보"}
rec = SimRecorder(a.out, meta={"scene": SCENE, "hz": a.hz, "robots": [{"id": "C", "name": "천장"}, {"id": "SL", "name": "좌측"}, {"id": "SR", "name": "우측"}],
                              "recipe": {"replay_of": os.path.basename(a.cells)}, "rl": True, "physical_contact": True,
                              "recipe_values": {"force_n": 6.69, "feed_mm_s": 5.65, "rpm": 3259, "step_over_ratio": 0.27, "n_passes": 2, "pad_radius_m": 0.055, "robots": ["C", "SL", "SR"]},
                              "params": {"robotCount": 3, "hasRail": True, "hasLift": True, "tool": "dual", "pad": 110, "carLift": 0, "recipe": "base"},
                              "kind": "result_replay_q" if IK is not None else "result_replay"}, chunk_s=60.0)
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
        keys = KEYQ.get((rid, r["cell_id"])) if (r is not None and IK is not None) else None
        if keys is not None and state in ("APPROACH", "POLISH", "RETRACT"):
            if state == "APPROACH":
                q = _lerp_q(keys["app0"], keys["pol0"], u); force = 0.0
            elif state == "POLISH":
                ph = (t - t0) / max(1.0, t1 - t0); w = math.sin(2 * math.pi * 2 * ph)
                q = _lerp_q(keys["pol0"], keys["polp"] if w >= 0 else keys["polm"], abs(w))
                force = TARGET[rid] * (1.0 + 0.06 * math.sin(2 * math.pi * 0.7 * t + hash(rid) % 7))
            else:
                q = _lerp_q(keys["pol1"], keys["ret1"], u); force = 0.0
        elif keys is None and state == "SLIDE" and IK is not None:
            q = CARRY_Q; force = 0.0
        elif r is not None and state in ("APPROACH", "POLISH", "RETRACT"):
            c = [float(r["center_x_m"]), float(r["center_y_m"]), float(r["center_z_m"]) + CAR_LIFT_Z]
            nrm = cell_normal(r)
            q = POSE[rid]["q"]     # 실제 Isaac 폴리싱 자세 — 콘솔 IK 의 시드(팔꿈치 방향)
            if state == "POLISH":
                # 셀 안에서 6 cm 래스터(왕복, 셀당 2회) — 패드가 셀을 훑는 것처럼 (고배속에서도 떨리지 않게 작게)
                ph = (t - t0) / max(1.0, t1 - t0); lane = math.sin(2 * math.pi * 2 * ph) * 0.03
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
        if q is not None: rob["q"] = [float(v) for v in q]
        if tcp is not None and IK is None: rob["tcp"] = tcp; rob["normal"] = nrm   # 콘솔 IK 경로(오프라인 IK 없을 때만)
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
