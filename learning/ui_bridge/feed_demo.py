"""모니터 피드 합성 데모 — 시뮬 없이 UI2 ② LIVE 모드를 검증한다 (2 Hz 로 값이 움직임).
    python3 learning/ui_bridge/feed_demo.py [초] [경로]
실제 피드는 v5 러너(POLISH_MONITOR_FEED) 가 쓴다; 이 스크립트는 연결 확인용이다.
"""
import math
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))
from learning.ui_bridge.monitor_feed import MonitorFeed  # noqa: E402

dur = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(_HERE, "out", "monitor_feed.json")
rec_path = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("POLISH_RECORD", "")   # 세 번째 인자: 기록 sqlite
feed = MonitorFeed(path)
recorder = None
if rec_path:
    from learning.ui_bridge.sim_recorder import SimRecorder
    recorder = SimRecorder(rec_path, meta={"scene": {"up": "z", "long": "y", "car_min": [-0.92, -2.3, 0.05], "car_max": [0.92, 2.3, 1.45]},
                                          "hz": 10.0, "robots": [{"id": "C", "name": "천장"}, {"id": "SL", "name": "좌측"}, {"id": "SR", "name": "우측"}],
                                          "recipe": {"synthetic": True}, "rl": False, "physical_contact": False})
feed.event("C", "합성 피드 시작 (feed_demo.py)", "info", 0.0)
ctl_path = os.environ.get("POLISH_CONTROL", "")
ctl = {"pause": False, "force_scale": 1.0, "feed_scale": 1.0}; _ctl_m = 0.0
t0 = time.time(); n = 0; t = 0.0; paused_total = 0.0; _last = time.time()
while t < dur:
    now = time.time(); _dt = now - _last; _last = now
    if ctl_path and os.path.exists(ctl_path):
        try:
            _m = os.path.getmtime(ctl_path)
            if _m != _ctl_m:
                _ctl_m = _m; ctl.update(json.load(open(ctl_path)) or {})
                feed.event("C", f"컨트롤 반영: {'일시정지' if ctl.get('pause') else '진행'} · 힘×{float(ctl.get('force_scale', 1)):.2f} · 이송×{float(ctl.get('feed_scale', 1)):.2f}", "info", t)
        except Exception: pass
    if ctl.get("pause"):
        robots = [{"id": rid, "force": 0.0, "target": tgt, "state": "HOLD", "progress": min(1.0, t / dur), "rl_force_scale": 1.0, "rl_feed_scale": 1.0}
                  for rid, tgt in (("C", 6.69), ("SL", 8.30), ("SR", 8.30))]
        feed.update("HOLD", min(1.0, t / dur), robots, elapsed_s=t, cells=globals().get("cells", {}))
        time.sleep(0.2); continue
    t += _dt * float(ctl.get("feed_scale", 1.0)); n += 1     # 이송 배율만큼 공정이 빨리/느리게 진행
    prog = min(1.0, t / dur)
    robots = []
    # 합성 관절/베이스: Isaac HOME (0,-1.05,1.45,0,1.15,0) 주변에서 천천히 흔들리고 레일(y)을 따라 왕복
    HOME = (0.0, -1.05, 1.45, 0.0, 1.15, 0.0)
    BASES = {"C": ((0.0, 0.0, 2.35), (0.0, 0.7071, 0.7071, 0.0)),        # 천장: 거꾸로(x 180°)·yaw −90° → w,x,y,z 근사
             "SL": ((-1.55, 0.0, 0.45), (0.7071, 0.0, 0.0, -0.7071)),    # 좌측 레일, yaw −90°
             "SR": ((1.55, 0.0, 0.45), (0.7071, 0.0, 0.0, -0.7071))}
    for i, (rid, tgt) in enumerate((("C", 6.69), ("SL", 8.30), ("SR", 8.30))):
        f = (tgt + 0.6 * math.sin(0.7 * t + i) + (1.5 if (n + i) % 37 == 0 else 0.0)) * float(ctl.get("force_scale", 1.0))
        q = [HOME[j] + (0.35 if j in (0, 1, 2, 4) else 0.1) * math.sin(0.5 * t + 0.9 * j + i) for j in range(6)]
        pos, quat = BASES[rid]; pos = [pos[0], 1.4 * math.sin(0.15 * t + i), pos[2]]
        robots.append({"id": rid, "force": f, "target": tgt, "state": "POLISH", "progress": prog,
                       "rl_force_scale": 1.0 + 0.2 * math.sin(0.3 * t + i), "rl_feed_scale": 1.0 - 0.1 * math.cos(0.2 * t),
                       "q": q, "base": {"pos": pos, "quat": list(quat)}})
    if n % 40 == 0:
        feed.event("SL", f"셀 {n // 40} 판정 통과 — GU {71 + (n % 5) * 0.4:.1f}", "info", t)
    # 합성 셀 판정 지도: 차 bbox(x ±0.9, y ±2.3, 윗면 z≈1.4 / 옆면 x=±0.92) 위 격자, 진행률만큼 순서대로 판정됨
    if n == 1:
        import random as _rnd; _r = _rnd.Random(7)
        _grid = [[0.12 * i - 0.84, 0.16 * j - 2.24, 1.42] for j in range(29) for i in range(15) if abs(0.12 * i - 0.84) < 0.75 or abs(0.16 * j - 2.24) < 1.3]
        _grid += [[sx * 0.93, 0.16 * j - 2.24, 0.45 + 0.16 * k] for sx in (-1, 1) for j in range(29) for k in range(5)]
        _disp = [_r.choices(["pass", "spot_repaint_review", "rework_candidate"], weights=[62, 30, 8])[0] for _ in _grid]
        globals()["_GRID"], globals()["_DISP"] = _grid, _disp
    _k = int(prog * len(_GRID))
    cells = {"total": len(_GRID), "pass": sum(1 for d in _DISP[:_k] if d == "pass"), "rework": sum(1 for d in _DISP[:_k] if d == "rework_candidate"),
             "repaint": sum(1 for d in _DISP[:_k] if d == "spot_repaint_review"), "not_reached": len(_GRID) - _k,
             "items": [[*_GRID[i], _DISP[i], 71.0 + (i % 7) * 0.5] for i in range(_k)]}
    scene = {"up": "z", "long": "y", "car_min": [-0.92, -2.3, 0.05], "car_max": [0.92, 2.3, 1.45]}
    feed.update("POLISH" if prog < 1.0 else "DONE", prog, robots, elapsed_s=t, cells=cells, scene=scene)
    if recorder is not None:
        recorder.frame(t, "POLISH" if prog < 1.0 else "DONE", prog, t, robots)
        if n % 40 == 0: recorder.event(t, "SL", "info", f"셀 {n // 40} 판정 통과 — GU {71 + (n % 5) * 0.4:.1f}")
        if n % 20 == 0: recorder.cells(t, cells)      # 합성: 2 s 마다 셀 스냅샷
    time.sleep(0.1)   # 10 Hz — 팔 동기화 확인용
# 연결 검증용 결과 요약(last_run.json) — 실제 러너의 _rl_flush 와 같은 자리에 같은 모양으로
import json as _json
_res = {"ts": time.time(), "tag": "feed_demo", "sim_step": n * 30, "elapsed_s": dur,
        "recipe": {"force": 6.69, "feed_mm_s": 5.65, "rpm": 3259, "spacing_ratio": 0.27, "n_passes": 2},
        "cells": {"cells": 491, "polished": 440, "pass": 300, "spot_repaint_review": 80, "rework_candidate": 60, "not_reached": 51},
        "quality": {"cells": 440, "ra": 0.121, "rz": 1.62, "clearcoat": 38.9, "scratch": 0.06, "scratchBefore": 0.31,
                    "glossMean": 72.4, "glossP10": 66.1, "glossStd": 3.2, "glossMin": 58.0, "glossTiles": 440,
                    "glossPass": True, "glossBand": "target_pass"},
        "rl": {"force": 5.2, "force_scale_mean": 0.97, "feed_scale_mean": 1.04, "stiffness": 350.0, "damping": 35.0}}
_json.dump(_res, open(os.path.join(os.path.dirname(path), "last_run.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
if recorder is not None:
    recorder.finish(_res); recorder.close(); print(f"기록 → {rec_path} ({recorder.n_frames} 프레임)")
print("feed_demo 종료 (last_run.json 기록)")
