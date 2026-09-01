"""RL 챔피언 정책 결과 → PolyTwin UI2 콘솔 데이터 계약(`data_sample.txt` 스키마) 내보내기.

UI2(polytwin_UI2 브랜치)의 품질 판정 화면은 `frontend/데이터셋/make_quality.py` 가
에피소드×타일(2 mm 셀) CSV 를 요약한 `quality_kpi.json` 을 읽는다. 지금까지 그 원본은
kinematic 실행기(레시피 고정)의 출력이었다. 이 스크립트는 같은 스키마로 **잔차 정책이
실제로 닦은** 결과를 쓴다 — 셀 하나 = 에피소드 하나 (재폴리싱 포함, 판정 파이프라인과 동일).

    ~/isaacsim/python.sh learning/ui_bridge/export_ui2_dataset.py \
        --input learning/vehicle_export/vehicle_150_cells_newcar.csv --cells 0-29 \
        --out learning/ui_bridge/out/data_rl_newcar.txt
    python3 <UI2>/frontend/데이터셋/make_quality.py <절대경로>/data_rl_newcar.txt

추가 컬럼 `thermal_damage_proxy` 를 넣는다 (make_quality.py 가 있으면 q_thermal 에 반영).
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys

import numpy as np
import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _REPO)

from learning.polytwin import config as PC                                   # noqa: E402
from learning.polytwin.export_cell_dataset import COLUMNS, local_roughness   # noqa: E402
from learning.polytwin.gloss_proxy import LiteratureGlossProxyModel           # noqa: E402
from learning.polytwin.path_executor import load_calibrated_config            # noqa: E402
from learning.polytwin.polishing_model import ContactState, LiteraturePolishingModel  # noqa: E402
from learning.polytwin.roughness_metrics import residual_scratch_depth_um     # noqa: E402
from learning.rl.env.contact import VirtualPadContact                         # noqa: E402
from learning.vehicle_export.export_vehicle_results import (                  # noqa: E402
    CLEARCOAT_SAFE_MIN_UM, DECIMATION, DEFAULT_CKPT, FEED_RATIO_LIMIT, FORCE_HARD_LIMIT_N,
    FORCE_RATIO_LIMIT, GU_PASS_MIN, MAX_CONTROL_STEPS, PHYSICS_DT, RA_PASS_MAX_UM, RECIPE_JSON,
    RZ_PASS_MAX_UM, _Path, footprint_stats, load_bc_policy, load_recipe, spatial_lookahead,
    synthesize_cell_patch)

OUT_COLUMNS = COLUMNS + ["thermal_damage_proxy"]


def parse_cells(spec: str, n: int) -> list[int]:
    if spec == "all":
        return list(range(n))
    if "-" in spec and "," not in spec:
        a, b = spec.split("-"); return [i for i in range(int(a), int(b) + 1) if i < n]
    return [int(v) for v in spec.split(",") if v.strip() and int(v) < n]


def replay_cell(row: dict, recipe, policy, cal, max_repolish: int = 2, window: int = 11):
    """export_vehicle_results.run_cell_episode 와 동일한 제어·재폴리싱 루프 + 타일 누적."""
    seed = int(float(row.get("surface_seed") or 0)) or (
        7000 + 101 * int(row["region_id"]) + int(row["cell_id"]))
    ra0, scr0, cc0 = float(row["init_ra_um"]), float(row["init_scratch_um"]), float(row["init_clearcoat_um"])
    n = np.array([float(row["normal_x"]), float(row["normal_y"]), float(row["normal_z"])]); n /= max(np.linalg.norm(n), 1e-9)
    is_side = math.degrees(math.acos(np.clip(n[2], -1.0, 1.0))) > 45.0
    n_scr = row.get("init_scratch_count")
    st = synthesize_cell_patch(seed, ra0, scr0, cc0, n_scratches=int(n_scr) if n_scr not in (None, "") else None)
    model = LiteraturePolishingModel(cal); gloss = LiteratureGlossProxyModel()

    before_micro = st.micro_height_um.copy()
    before_scr = residual_scratch_depth_um(st.micro_height_um, st.defect_mask, st.resolution_m)
    before_cc = st.clearcoat_remaining_um.copy()
    before_scr_max = float(before_scr.max())
    path = _Path(recipe)
    contact = VirtualPadContact(1, "cpu", dt=PHYSICS_DT, lag_offset=0.0)
    side_t = torch.tensor([is_side]); quality_dt = PHYSICS_DT * DECIMATION
    feed0 = recipe.feed_speed_mm_s / 1000.0
    acc_w = np.zeros(st.shape); acc_f = np.zeros(st.shape); acc_r = np.zeros(st.shape); acc_v = np.zeros(st.shape)
    n_contact = np.zeros(st.shape, dtype=np.int32)
    sim_t = 0.0; hard = False; episodes = 0; last_gu = None; passes_total = 0

    def judge():
        q = model.evaluate(st); gu = float(gloss.evaluate(st)["summary"]["gu_mean"])
        ok = (gu >= GU_PASS_MIN and q["ra_um"] <= RA_PASS_MAX_UM and q["rz_um"] <= RZ_PASS_MAX_UM
              and float(st.clearcoat_remaining_um.min()) >= CLEARCOAT_SAFE_MIN_UM
              and (before_scr_max < 0.05 or q["max_residual_scratch_um"] < before_scr_max))
        return ok, gu

    for _ep in range(1 + max_repolish):
        episodes += 1; contact.reset(is_side=side_t)
        arc = 0.0; prev_force = 0.0; prev_a = np.zeros(2, dtype=np.float32); force_mean = 0.0
        fp = (0.0, 0.0, 0.0, 20.0, PC.AMBIENT_TEMPERATURE_C, PC.AMBIENT_TEMPERATURE_C, 0.0)
        completed = False; cc_start = float(st.clearcoat_remaining_um.min())
        for _step in range(MAX_CONTROL_STEPS):
            core = [force_mean / 10.0, 0.0, (force_mean - prev_force) / 5.0, 0.0,
                    min(arc / path.total, 1.0), fp[0] / 2.0, fp[1] / 2.0, fp[2] / 5.0, fp[3] / 20.0]
            od = getattr(policy, "obs_dim", 14); tail = []
            if od in (14, 18):
                tail += [(fp[4] - PC.AMBIENT_TEMPERATURE_C) / 40.0, (fp[5] - PC.AMBIENT_TEMPERATURE_C) / 60.0,
                         fp[6] / PC.THERMAL_DAMAGE_MAX]
            if od in (15, 18):
                tail += [v / 2.0 for v in spatial_lookahead(st, path, arc)]
            obs = np.array(core + [prev_a[0], prev_a[1]] + tail, dtype=np.float32)
            obs[1] = (force_mean - recipe.target_contact_force_n * (1.0 + prev_a[0] * FORCE_RATIO_LIMIT)) / 5.0
            obs[3] = feed0 * (1.0 + prev_a[1] * FEED_RATIO_LIMIT) * 100.0
            a = policy(obs)
            force_cmd = recipe.target_contact_force_n * (1.0 + a[0] * FORCE_RATIO_LIMIT)
            feed_cmd = feed0 * (1.0 + a[1] * FEED_RATIO_LIMIT)
            f_acc = 0.0; tgt = torch.tensor([force_cmd], dtype=torch.float32)
            for _ in range(DECIMATION):
                f_acc += float(contact.step(tgt, side_t)[0]); arc += feed_cmd * PHYSICS_DT; sim_t += PHYSICS_DT
            prev_force = force_mean; force_mean = f_acc / DECIMATION
            if force_mean > FORCE_HARD_LIMIT_N: hard = True
            uv = path.pos_at(arc)
            model.step(st, ContactState(pad_center_uv_m=uv, contact_force_n=force_mean, rpm=recipe.rpm,
                                        feed_speed_m_s=feed_cmd), dt_s=quality_dt, sim_time_s=sim_t)
            sl, shape01, _w, _a = model._footprint(st, uv)
            if sl is not None:
                wdt = shape01 * quality_dt
                acc_w[sl] += wdt; acc_f[sl] += wdt * force_mean; acc_r[sl] += wdt * recipe.rpm
                acc_v[sl] += wdt * feed_cmd * 1000.0; n_contact[sl] += (shape01 > 0.0)
            fp = footprint_stats(st, uv, CLEARCOAT_SAFE_MIN_UM); prev_a = a
            if hard: break
            if arc >= path.total: completed = True; break
        passes_total += recipe.n_passes
        if hard or not completed: break
        ok, gu_now = judge()
        if ok: break
        if last_gu is not None and gu_now <= last_gu + 0.05: break
        last_gu = gu_now
        cc_now = float(st.clearcoat_remaining_um.min())
        if cc_now - 1.5 * max(cc_start - cc_now, 0.5) < CLEARCOAT_SAFE_MIN_UM: break

    # ── 타일 행 생성 (export_cell_dataset.py 와 동일 정의) ──
    ra_b, rz_b, rq_b = local_roughness(before_micro, window)
    ra_a, rz_a, rq_a = local_roughness(st.micro_height_um, window)
    after_scr = residual_scratch_depth_um(st.micro_height_um, st.defect_mask, st.resolution_m)
    denom = np.where(acc_w > 0.0, acc_w, 1.0)
    force_t = np.where(acc_w > 0.0, acc_f / denom, 0.0); rpm_t = np.where(acc_w > 0.0, acc_r / denom, 0.0)
    feed_t = np.where(acc_w > 0.0, acc_v / denom, 0.0)
    res = st.resolution_m; rows_out = []
    H, W = st.shape
    for i in range(H):
        for j in range(W):
            rows_out.append({
                "cell_id": i * W + j, "x": f"{(i + 0.5) * res:.6f}", "y": f"{(j + 0.5) * res:.6f}", "z": "0.000000",
                "surface_normal_x": f"{n[0]:.4f}", "surface_normal_y": f"{n[1]:.4f}", "surface_normal_z": f"{n[2]:.4f}",
                "force_N": f"{force_t[i, j]:.4f}", "rpm": f"{rpm_t[i, j]:.1f}", "feed_mm_s": f"{feed_t[i, j]:.4f}",
                "step_over_mm": f"{recipe.step_over_spacing_ratio * PC.PAD_DIAMETER_M * 1000:.3f}",
                "step_over_ratio": f"{recipe.step_over_spacing_ratio:.4f}", "pass_count": passes_total,
                "roughness_before": f"{rq_b[i, j]:.6f}", "roughness_after": f"{rq_a[i, j]:.6f}",
                "scratch_before": f"{before_scr[i, j]:.6f}", "scratch_after": f"{after_scr[i, j]:.6f}",
                "ra_before_um": f"{ra_b[i, j]:.6f}", "ra_after_um": f"{ra_a[i, j]:.6f}",
                "rz_before_um": f"{rz_b[i, j]:.6f}", "rz_after_um": f"{rz_a[i, j]:.6f}",
                "clearcoat_before_um": f"{before_cc[i, j]:.4f}", "clearcoat_after_um": f"{st.clearcoat_remaining_um[i, j]:.4f}",
                "clearcoat_removed_um": f"{before_cc[i, j] - st.clearcoat_remaining_um[i, j]:.6f}",
                "is_defect": int(bool(st.defect_mask[i, j])), "dwell_weighted_s": f"{acc_w[i, j]:.4f}",
                "contact_steps": int(n_contact[i, j]), "recipe_id": "rl_" + os.path.basename(getattr(policy, "ckpt", "policy")),
                "surface_seed": seed, "thermal_damage_proxy": f"{st.thermal_damage_proxy[i, j]:.6f}",
            })
    ok, gu = judge()
    return rows_out, {"cell": row["cell_id"], "region": row.get("region_name", ""), "pass": ok, "gu": gu,
                      "episodes": episodes, "time_s": sim_t, "hard": hard}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default=DEFAULT_CKPT)
    ap.add_argument("--input", default=os.path.join(_REPO, "learning", "vehicle_export", "vehicle_150_cells_newcar.csv"))
    ap.add_argument("--cells", default="0-29", help="입력 CSV 행 인덱스 범위/목록/all")
    ap.add_argument("--recipe_json", default=os.path.join(_REPO, "learning", "polytwin", "outputs", "bo_best_recipe_top.json"))
    ap.add_argument("--recipe_json_side", default=os.path.join(_REPO, "learning", "polytwin", "outputs", "bo_best_recipe_side.json"))
    ap.add_argument("--out", default=os.path.join(_HERE, "out", "data_rl_newcar.txt"))
    args = ap.parse_args()
    rows = list(csv.DictReader(open(args.input, encoding="utf-8")))
    idx = parse_cells(args.cells, len(rows))
    policy = load_bc_policy(args.checkpoint); policy.ckpt = args.checkpoint
    cal = load_calibrated_config()
    r_top, r_side = load_recipe(args.recipe_json), load_recipe(args.recipe_json_side)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    n_pass = 0
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLUMNS); w.writeheader()
        for ep, i in enumerate(idx):
            row = rows[i]
            nz = float(row["normal_z"]); is_side = math.degrees(math.acos(max(-1.0, min(1.0, nz)))) > 45.0
            tiles, summ = replay_cell(row, r_side if is_side else r_top, policy, cal)
            for t in tiles:
                t["episode_id"] = ep; w.writerow(t)
            n_pass += bool(summ["pass"])
            print(f"[ui2] ep {ep} cell {summ['cell']} {summ['region']}: pass={summ['pass']} GU {summ['gu']:.1f} "
                  f"episodes {summ['episodes']} t {summ['time_s']:.0f}s", flush=True)
    print(f"[ui2] {len(idx)} 에피소드 → {args.out} (합격 {n_pass}/{len(idx)})")


if __name__ == "__main__":
    main()
