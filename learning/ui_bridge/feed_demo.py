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
feed = MonitorFeed(path)
feed.event("C", "합성 피드 시작 (feed_demo.py)", "info", 0.0)
t0 = time.time(); n = 0
while time.time() - t0 < dur:
    t = time.time() - t0; n += 1
    prog = min(1.0, t / dur)
    robots = []
    for i, (rid, tgt) in enumerate((("C", 6.69), ("SL", 8.30), ("SR", 8.30))):
        f = tgt + 0.6 * math.sin(0.7 * t + i) + (1.5 if (n + i) % 37 == 0 else 0.0)
        robots.append({"id": rid, "force": f, "target": tgt, "state": "POLISH", "progress": prog,
                       "rl_force_scale": 1.0 + 0.2 * math.sin(0.3 * t + i), "rl_feed_scale": 1.0 - 0.1 * math.cos(0.2 * t)})
    if n % 40 == 0:
        feed.event("SL", f"셀 {n // 40} 판정 통과 — GU {71 + (n % 5) * 0.4:.1f}", "info", t)
    cells = {"total": 491, "pass": int(prog * 300), "rework": int(prog * 60), "repaint": int(prog * 80),
             "not_reached": 491 - int(prog * 440), "items": []}
    feed.update("POLISH" if prog < 1.0 else "DONE", prog, robots, elapsed_s=t, cells=cells)
    time.sleep(0.5)
print("feed_demo 종료")
