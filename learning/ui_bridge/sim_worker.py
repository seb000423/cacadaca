"""GPU PC 워커 — PolyTwin UI2 작업 큐를 폴링해 Isaac Sim(v5 + 잔차 정책)을 실행하고 피드·결과를 밀어 올린다.

배포(Vercel)에서는 서버가 시뮬을 못 띄우므로, GPU 가 있는 PC 에서 이 데몬을 상시 돌린다.
아웃바운드 HTTPS 만 쓴다(NAT/방화벽 뒤 OK, ROS 불필요).

    python3 learning/ui_bridge/sim_worker.py --server https://<app>.vercel.app --token <PT_WORKER_TOKEN>
    python3 learning/ui_bridge/sim_worker.py --server http://127.0.0.1:8000 --token test --fake   # 시뮬 대신 합성 피드

흐름: GET /api/sim/jobs/next → 레시피 JSON 작성 → Isaac 기동(POLISH_RL=1, POLISH_MONITOR_FEED, ...)
      → 0.7 s 마다 monitor_feed.json 을 POST /api/sim/jobs/<id>/feed (응답의 stopRequested 면 종료)
      → 종료 시 last_run.json 을 POST .../result, 종료 코드를 POST .../exit
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
OUT = os.path.join(_HERE, "out")


def api(server: str, token: str, path: str, body=None, method: str | None = None, timeout: float = 10.0):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(server.rstrip("/") + path, data=data,
                                 method=method or ("POST" if data is not None else "GET"))
    req.add_header("X-PT-Worker", token)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def write_recipe(params: dict) -> str:
    base_path = os.path.join(_REPO, "learning", "polytwin", "outputs", "bo_best_recipe_top.json")
    try:
        recipe = json.load(open(base_path, encoding="utf-8"))
    except Exception:
        recipe = {}
    recipe.update({
        "recipe_id": "ui_queue_job", "source": "PolyTwin console (queue)",
        "target_contact_force_n": float(params.get("force", 5.6)),
        "rpm": float(params.get("rpm", 3000)),
        "feed_speed_mm_s": float(params.get("feed_mm_s", 5.65)),
        "step_over_spacing_ratio": max(0.05, min(1.0, 1.0 - float(params.get("overlap", 40)) / 100.0)),
        "n_passes": int(recipe.get("n_passes", 2)),
    })
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "ui_recipe.json")
    json.dump(recipe, open(p, "w", encoding="utf-8"), indent=1)
    return p


def launch(params: dict, feed_path: str, fake: bool, isaac_py: str) -> subprocess.Popen:
    for f in (feed_path, os.path.join(OUT, "last_run.json")):
        try: os.remove(f)
        except FileNotFoundError: pass
    log = open(os.path.join(OUT, "sim_run.log"), "w")
    rec_path = params.get("_record_path") or ""
    if fake:
        cmd = [sys.executable, os.path.join(_HERE, "feed_demo.py"), str(params.get("fake_seconds", 40)), feed_path]
        if rec_path: cmd.append(rec_path)
        return subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    recipe = write_recipe(params)
    env = dict(os.environ)
    env.update({
        "POLISH_RL": "1", "POLISH_MONITOR_FEED": feed_path, "POLISH_RL_RECIPE_TOP": recipe,
        "POLISH_RL_RECIPE_SIDE": recipe, "POLISH_RL_OUT": os.path.join(OUT, "ui_cells.csv"),
        "POLISH_RENDER_EVERY": "10", "POLISH_ROS_PUBLISH": "0", "POLISH_ROS_CAMERAS": "0",
        "MAX_SIM_STEPS": str(int(params.get("max_steps", 6000))), "POLISH_EXIT_WHEN_DONE": "1",
        "POLISH_PHYSICAL_CONTACT": "1" if params.get("physical") else "0",
    })
    if rec_path: env["POLISH_RECORD"] = rec_path
    return subprocess.Popen([isaac_py, "polishing_v5.py", "--obj_name", "car", "--headless"],
                            cwd=os.path.join(_REPO, "scripts"), env=env, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)


class RunUploader:
    """SimRecorder sqlite 를 따라가며 새 청크/이벤트/셀을 서버에 올린다 (지연 재생·리플레이용)."""
    def __init__(self, args, job_id: int, path: str):
        self.args = args; self.job_id = job_id; self.path = path
        self.run_id = None; self.seq = 0; self.ev = 0; self.cell = 0; self.reader = None

    def _open(self):
        if self.reader is not None or not os.path.exists(self.path):
            return
        from learning.ui_bridge.sim_recorder import SimReader
        try:
            self.reader = SimReader(self.path)
            meta = self.reader.meta()
            r = api(self.args.server, self.args.token, "/api/sim/runs",
                    {"job_id": self.job_id, "name": f"job {self.job_id} " + time.strftime("%Y-%m-%d %H:%M"), "meta": meta})
            self.run_id = r.get("run_id")
            print(f"[worker] 기록 업로드 시작 run_id={self.run_id}", flush=True)
        except Exception as exc:
            self.reader = None
            print(f"[worker] 기록 열기 실패(재시도): {exc}", flush=True)

    def tick(self, final: bool = False, result=None, status: str = "done"):
        self._open()
        if self.reader is None or self.run_id is None:
            return
        import base64
        try:
            ch = self.reader.chunks_after(self.seq)
            for i in range(0, len(ch), 60):
                part = ch[i:i + 60]
                api(self.args.server, self.args.token, f"/api/sim/runs/{self.run_id}/chunks",
                    {"chunks": [{"seq": c[0], "t0": c[1], "t1": c[2], "n": c[3], "data": base64.b64encode(c[4]).decode("ascii")} for c in part]},
                    timeout=30)
                self.seq = part[-1][0]
            ev = [e for i, e in enumerate(self.reader.events(), 1) if i > self.ev]
            if ev:
                api(self.args.server, self.args.token, f"/api/sim/runs/{self.run_id}/events",
                    {"events": [{"id": self.ev + i + 1, "t": e[0], "robot": e[1], "level": e[2], "msg": e[3]} for i, e in enumerate(ev)]})
                self.ev += len(ev)
            cells = self.reader.cells_after(self.cell)
            if cells:
                api(self.args.server, self.args.token, f"/api/sim/runs/{self.run_id}/cells",
                    {"cells": [{"id": c[0], "t": c[1], "data": base64.b64encode(c[2]).decode("ascii")} for c in cells]}, timeout=30)
                self.cell = cells[-1][0]
            if final:
                meta = self.reader.meta()
                api(self.args.server, self.args.token, f"/api/sim/runs/{self.run_id}/meta", {"meta": meta})
                api(self.args.server, self.args.token, f"/api/sim/runs/{self.run_id}/finish",
                    {"status": status, "result": result if result is not None else self.reader.result()})
                print(f"[worker] 기록 업로드 완료 run_id={self.run_id} (청크 {self.seq})", flush=True)
        except Exception as exc:
            print(f"[worker] 기록 업로드 실패(계속): {exc}", flush=True)


def run_job(job: dict, args) -> None:
    jid = job["id"]; params = dict(job.get("params") or {})
    feed_path = os.path.join(OUT, "monitor_feed.json")
    rec_path = os.path.join(OUT, f"run_job{jid}_{time.strftime('%Y%m%d_%H%M%S')}.sqlite")
    params["_record_path"] = rec_path
    print(f"[worker] job {jid} 시작 params={params}", flush=True)
    proc = launch(params, feed_path, args.fake, args.isaac)
    uploader = RunUploader(args, jid, rec_path)
    stop = False; last_ts = None; last_up = 0.0
    while True:
        code = proc.poll()
        if time.time() - last_up >= args.upload_interval:
            uploader.tick(); last_up = time.time()
        # 피드 전달
        try:
            with open(feed_path, encoding="utf-8") as f:
                feed = json.load(f)
            if feed.get("ts") != last_ts:
                last_ts = feed.get("ts")
                r = api(args.server, args.token, f"/api/sim/jobs/{jid}/feed", {"feed": feed})
                if r.get("stopRequested") and not stop:
                    stop = True
                    print(f"[worker] job {jid} 정지 요청 → 프로세스 종료", flush=True)
                    try: os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    except Exception: proc.terminate()
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        except urllib.error.URLError as exc:
            print(f"[worker] 피드 전송 실패: {exc}", flush=True)
        if code is None and not stop:
            # 정지 플래그만 확인 (피드가 아직 없을 때)
            try:
                st = api(args.server, args.token, f"/api/sim/jobs/{jid}/state")
                if (st.get("job") or {}).get("stopRequested"):
                    stop = True
                    try: os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    except Exception: proc.terminate()
            except Exception:
                pass
        if code is not None:
            break
        time.sleep(args.interval)
    # 결과
    result = None
    try:
        result = json.load(open(os.path.join(OUT, "last_run.json"), encoding="utf-8"))
    except Exception:
        result = None
    if result is not None:
        try: api(args.server, args.token, f"/api/sim/jobs/{jid}/result", {"result": result})
        except Exception as exc: print(f"[worker] 결과 전송 실패: {exc}", flush=True)
    status = "stopped" if stop else ("done" if code == 0 else "failed")
    uploader.tick(final=True, result=result, status="failed" if code not in (0, None) and not stop else "done")
    try:
        api(args.server, args.token, f"/api/sim/jobs/{jid}/exit", {"exitCode": code, "status": status})
    except Exception as exc:
        print(f"[worker] 종료 보고 실패: {exc}", flush=True)
    print(f"[worker] job {jid} {status} (exit {code}, result={'있음' if result else '없음'})", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True, help="UI2 서버 (예: https://app.vercel.app 또는 http://127.0.0.1:8000)")
    ap.add_argument("--token", default=os.environ.get("PT_WORKER_TOKEN", ""), help="PT_WORKER_TOKEN")
    ap.add_argument("--name", default=os.environ.get("HOSTNAME", "gpu"))
    ap.add_argument("--poll", type=float, default=1.0, help="작업 폴링 주기(s)")
    ap.add_argument("--interval", type=float, default=0.7, help="피드 전송 주기(s)")
    ap.add_argument("--upload_interval", type=float, default=2.0, help="기록 청크 업로드 주기(s) — 지연 재생 지연 ≈ 이 값 + 1 s")
    ap.add_argument("--isaac", default=os.path.expanduser("~/isaacsim/python.sh"))
    ap.add_argument("--fake", action="store_true", help="Isaac 대신 합성 피드(feed_demo.py) — 연결 검증용")
    ap.add_argument("--once", action="store_true", help="작업 하나만 처리하고 종료")
    args = ap.parse_args()
    if not args.token:
        sys.exit("워커 토큰이 없습니다 (--token 또는 PT_WORKER_TOKEN)")
    print(f"[worker] {args.name} → {args.server} 폴링 시작 (fake={args.fake})", flush=True)
    while True:
        try:
            r = api(args.server, args.token, f"/api/sim/jobs/next?worker={args.name}")
            job = r.get("job")
        except Exception as exc:
            print(f"[worker] 서버 연결 실패: {exc}", flush=True); job = None
        if job:
            run_job(job, args)
            if args.once:
                break
        time.sleep(args.poll)


if __name__ == "__main__":
    main()
