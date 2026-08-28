"""로봇 팔 시연 — 기준 제어(action=0) vs BC 챔피언을 같은 스크래치 표면에서 나란히.

    ~/isaacsim/python.sh learning/rl/demo_arm.py            # GUI
    python learning/rl/demo_arm.py --headless # 검증 실행

구성 (env 2개, 좌=baseline / 우=BC 정책):
  · M0609 + 폴리셔 (usd/env/Collected_m0609_with_polisher — 상대경로 수집본. 원본 wrapper 는
    /home/rokey/... 절대참조가 깨져 있어 사용 불가)
  · 표면 patch 는 로봇 앞 바닥의 회색 판. 스크래치는 얇은 막대 마커 —
    잔여 깊이에 따라 빨강(깊음)→노랑→초록(제거됨)으로 변한다.
  · 팔은 DifferentialIK 로 패드 목표(경로점 + 어드미턴스 z_offset)를 추종한다.
    접촉력·품질은 검증된 해석 모델(contact.py + LiteraturePolishingModel)이 계산한다 —
    원 시뮬도 강체 충돌 OFF 였으므로(A안) 팔은 시각·기구 검증 역할이다.
"""
import argparse
import sys

import os as _os
_REPO_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
sys.path.insert(0, _REPO_ROOT)

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--checkpoint", type=str,
                    default=None,
                    help="기본: <repo>/learning/rl/champion/model_bc.pt")
parser.add_argument("--surface_seed", type=int, default=1000)
parser.add_argument("--max_seconds", type=float, default=None,
                    help="시뮬 시간 상한 (기본: 에피소드 완주까지)")
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
if args.checkpoint is None:
    args.checkpoint = _os.path.join(_REPO_ROOT, "learning", "rl", "champion",
                                    "model_terminal_ppo_it400.pt")   # 2026-08-28 챔피언 교체
app = AppLauncher(args).app

from importlib import metadata  # noqa: E402

import numpy as np  # noqa: E402
import torch  # noqa: E402

import isaaclab.sim as sim_utils  # noqa: E402
from isaaclab.actuators import ImplicitActuatorCfg  # noqa: E402
from isaaclab.assets import Articulation, ArticulationCfg  # noqa: E402
from isaaclab.controllers import DifferentialIKController, DifferentialIKControllerCfg  # noqa: E402
from isaaclab.markers import VisualizationMarkers, VisualizationMarkersCfg  # noqa: E402
from isaaclab.scene import InteractiveScene, InteractiveSceneCfg  # noqa: E402
from isaaclab.sim import SimulationContext  # noqa: E402
from isaaclab.utils.configclass import configclass  # noqa: E402
from isaaclab.utils.math import subtract_frame_transforms  # noqa: E402

from learning.polytwin import config as PC  # noqa: E402
from learning.polytwin.gloss_proxy import LiteratureGlossProxyModel  # noqa: E402
from learning.polytwin.path_executor import load_calibrated_config, raster_waypoints  # noqa: E402
from learning.polytwin.polishing_model import ContactState, LiteraturePolishingModel  # noqa: E402
from learning.polytwin.surface_state import make_flat_patch  # noqa: E402
from learning.rl.env.contact import VirtualPadContact  # noqa: E402
from learning.rl.env.polish_env import _load_recipe  # noqa: E402
from learning.rl.env.polish_env_cfg import PolishEnvCfg  # noqa: E402

ROBOT_USD = _os.path.join(_REPO_ROOT, "usd", "env", "Collected_m0609_with_polisher",
                          "m0609_with_polisher.usd")
PATCH_SIZE = (0.20, 0.20)   # 시연용 확대 — 학습/판정은 0.12 (정책은 국소 관측이라 무관)
PATCH_CENTER = (0.45, 0.0)          # 로봇 베이스 기준 앞쪽 45cm (M0609 도달반경 내)
E = 2                               # 0=baseline, 1=BC


@configclass
class DemoSceneCfg(InteractiveSceneCfg):
    robot: ArticulationCfg = ArticulationCfg(
        prim_path="{ENV_REGEX_NS}/Robot",
        spawn=sim_utils.UsdFileCfg(usd_path=ROBOT_USD),
        init_state=ArticulationCfg.InitialStateCfg(
            joint_pos={"joint_1": 0.0, "joint_2": -1.05, "joint_3": 1.45,
                       "joint_4": 0.0, "joint_5": 1.15, "joint_6": 0.0, "pad_joint": 0.0},
        ),
        actuators={
            "arm": ImplicitActuatorCfg(joint_names_expr=["joint_[1-6]"],
                                       stiffness=10000.0, damping=500.0),
            # ⚠ pad_joint 는 위치제어로 고정한다. 강성 0(자유 관절)이면 tool0 의 회전을
            #   관절이 그대로 흡수해 원판 자세가 따라오지 않는다 — 실측: IK 는 명령을 0.3° 로
            #   달성하는데 패드면 법선은 홈값 그대로였다 (필요 회전축과 pad_joint 축이 일치).
            "pad": ImplicitActuatorCfg(joint_names_expr=["pad_joint"],
                                       stiffness=2000.0, damping=100.0),
        },
    )


def main():
    sim = SimulationContext(sim_utils.SimulationCfg(dt=1 / 60))
    scene_cfg = DemoSceneCfg(num_envs=E, env_spacing=2.5)
    scene = InteractiveScene(scene_cfg)
    sim_utils.GroundPlaneCfg().func("/World/ground", sim_utils.GroundPlaneCfg())
    light = sim_utils.DomeLightCfg(intensity=2500.0)
    light.func("/World/Light", light)

    # 작업대(회색) 위에 차 도장 패널(네이비) — 팔이 자연스러운 자세로 작업하는 허리 높이
    WORK_TOP = 0.40
    pedestal = sim_utils.CuboidCfg(
        size=(PATCH_SIZE[0] + 0.06, PATCH_SIZE[1] + 0.06, WORK_TOP - 0.05),
        visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.35, 0.35, 0.38)))
    plate = sim_utils.CuboidCfg(
        size=(PATCH_SIZE[0] + 0.04, PATCH_SIZE[1] + 0.04, 0.05),
        visual_material=sim_utils.PreviewSurfaceCfg(
            diffuse_color=(0.05, 0.12, 0.35), roughness=0.15, metallic=0.6))
    for i in range(E):
        pedestal.func(f"/World/envs/env_{i}/Pedestal", pedestal,
                      translation=(PATCH_CENTER[0], PATCH_CENTER[1], (WORK_TOP - 0.05) / 2))
        plate.func(f"/World/envs/env_{i}/Workpiece", plate,
                   translation=(PATCH_CENTER[0], PATCH_CENTER[1], WORK_TOP - 0.025))

    sim.reset()
    try:
        sim.set_camera_view(eye=(0.75, -0.35, 0.62), target=(0.45, 0.0, 0.42))
    except Exception:
        pass
    robot: Articulation = scene["robot"]

    # ★ 수동 씬에서는 기본 관절상태(홈 자세)를 명시적으로 써야 한다 — 안 쓰면 0-자세(수직)로
    #   시작해 기준 방향 캡처가 오염되고 IK 가 불가능 명령을 받는다 (ik_diag 로 실측 확인).
    robot.write_joint_state_to_sim(robot.data.default_joint_pos.torch.clone(),
                                   robot.data.default_joint_vel.torch.clone())
    robot.reset()
    for _ in range(60):    # 1초 안정화
        robot.set_joint_position_target_index(
            target=robot.data.default_joint_pos.torch.clone(),
            joint_ids=list(range(robot.num_joints)))
        scene.write_data_to_sim(); sim.step(render=False); scene.update(1 / 60)

    # ── 팔 IK 세팅 (튜토리얼 run_diff_ik 패턴) ──
    arm_joints = [robot.joint_names.index(f"joint_{k}") for k in range(1, 7)]
    pad_joint = robot.joint_names.index("pad_joint")
    pad_body = robot.body_names.index("sander_pad")   # (숨김 대상 중복본 — 로깅용 아님)
    # ★ IK 대상은 tool0 — sander_pad 는 pad_joint 로 3000 rpm 회전하는 링크라 그 자세를
    #   IK 로 고정하려 하면 스핀과 싸운다 (실측: 명령해도 패드면 법선 ·down = −0.399).
    #   원판 법선은 스핀축과 같아 회전에 불변이므로, 비회전 링크 tool0 을 제어하면 된다.
    # ★ IK 대상 = link_6. 화면에 보이는 샌더는 link_6/quick_mount/sanding_kit 에 달려 있다
    #   (자산에 샌더 메쉬가 두 벌: sander_pad 아래 복사본은 팔을 따라오지 않아 숨긴다).
    ee_body = robot.body_names.index("link_6")
    ik = DifferentialIKController(
        DifferentialIKControllerCfg(command_type="pose", use_relative_mode=False, ik_method="dls"),
        num_envs=E, device=sim.device)
    ee_jacobi_idx = ee_body - 1 if robot.is_fixed_base else ee_body

    PAD_HALF_THICKNESS = 0.0115   # 실측: sander_pad 링크프레임 extent Y = 0.023 m

    # ── 폴리싱 로직 (PolishEnv 와 동일 구성 요소) ──
    env_cfg = PolishEnvCfg()
    recipe = _load_recipe(env_cfg.recipe_json_path)
    from dataclasses import replace as _dc_replace
    recipe = _dc_replace(recipe, n_passes=1)     # 시연용 — 판정 숫자는 eval_ppo(2pass) 기준
    contact = VirtualPadContact(E, sim.device, dt=1 / 60, lag_offset=0.0)
    is_side = torch.zeros(E, dtype=torch.bool, device=sim.device)
    contact.reset(is_side=is_side)
    cal = load_calibrated_config()
    model = LiteraturePolishingModel(cal)
    gloss = LiteratureGlossProxyModel()
    # 같은 seed → 두 로봇이 같은 상처를 가진 표면을 닦는다
    surfaces = [make_flat_patch(PATCH_SIZE, 0.002, seed=args.surface_seed, with_scratches=True)
                for _ in range(E)]
    scratch_specs = _extract_scratch_segments(surfaces[0])

    spacing = recipe.step_over_spacing_ratio * PC.PAD_DIAMETER_M
    lines = raster_waypoints(PATCH_SIZE, spacing)
    line_len = np.array([float(np.hypot(p1[0] - p0[0], p1[1] - p0[1])) for p0, p1, _ in lines])
    path_len = float(line_len.sum()) * recipe.n_passes

    def pos_at_arc(a):
        one = float(line_len.sum())
        a = a % one if a < path_len else one - 1e-9
        for (p0, p1, _), L in zip(lines, line_len):
            if a <= L:
                t = a / L
                return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)
            a -= L
        return lines[-1][1]

    # ★ 패드 자세·오프셋 — 원 프로젝트 규약 + 실측
    #   agent.py `_ee_orientation`: EE 의 패드 접촉축을 −normal(표면 안쪽)에 정렬한다.
    #   실측 (BBoxCache.ComputeRelativeBound, link_6 프레임, 최하단 메쉬 57개):
    #     패드 중심 XY = (0.0000, −0.0156),  접촉면 Z = −0.0902,  지름 ≈ 0.070 m
    #   → 접촉축은 link_6 로컬 −Z. 수평 패널이면 −Z 가 세계 −Z 를 향하면 되므로 자세는 항등.
    PAD_OFFSET_LINK6 = np.array([0.0, -0.0156, -0.0902])

    def _quat_to_R(q):                      # q = (w, x, y, z)
        w, x, y, z = [float(v) for v in q]
        return np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])

    quat_cmd_world = torch.zeros(E, 4, device=sim.device); quat_cmd_world[:, 0] = 1.0
    tool_offset_world = PAD_OFFSET_LINK6.copy()      # 자세가 항등이라 그대로 세계 오프셋
    _root0 = robot.data.root_pose_w.torch
    _, quat_ref_b = subtract_frame_transforms(
        _root0[:, 0:3], _root0[:, 3:7], _root0[:, 0:3], quat_cmd_world)
    quat_ref_b = quat_ref_b.clone()
    print(f"[demo] link_6 → 패드접촉면 오프셋 {np.round(tool_offset_world, 4)} m, 목표자세 항등")

    # ── BC 정책 로드 (env 1 전용) ──
    policy = _load_policy(args.checkpoint, sim.device)

    # ── 스크래치 마커: 잔여 비율별 색 프로토타입 5단계 ──
    colors = [(0.9, 0.1, 0.1), (0.95, 0.5, 0.1), (0.95, 0.85, 0.1),
              (0.55, 0.9, 0.2), (0.1, 0.85, 0.3)]
    proto = {f"lv{k}": sim_utils.CuboidCfg(
        size=(1.0, 0.004, 0.002),
        visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=c, emissive_color=tuple(0.3*x for x in c)))
        for k, c in enumerate(colors)}
    markers = VisualizationMarkers(VisualizationMarkersCfg(prim_path="/Visuals/scratches", markers=proto))

    # ★ CAD 샌더 비주얼은 숨기고 접촉 원판을 직접 그린다.
    #   이 자산은 tool0 자세를 90° 바꿔도 sander_pad 법선이 따라오지 않는다 (실측: 자동보정
    #   4회 모두 오차 90°). 접촉력·제거량은 해석 모델이 계산하므로 물리 결과와 무관하고,
    #   시각만 바로잡으면 된다.
    try:
        import omni.usd
        from pxr import UsdGeom as _UG
        _stg = omni.usd.get_context().get_stage()
        _hidden = 0
        for _pr in _stg.Traverse():
            # ⚠ 이 자산은 샌더 메쉬를 **두 벌** 갖고 있다 (실측):
            #     sander_pad/pad_visual/...   ← 팔을 따라오지 않는다. 이것만 숨긴다.
            #     link_6/quick_mount/sanding_kit/...  ← 실제로 보이는 엔드이펙터. 유지.
            #   둘이 겹쳐 보이던 것이 "엉킨 느낌"의 원인이었다.
            if _pr.GetPath().name == "pad_visual":
                _UG.Imageable(_pr).MakeInvisible(); _hidden += 1
        print(f"[demo] CAD 샌더 비주얼 숨김: {_hidden}개")
    except Exception as _e:
        print(f"[demo] 비주얼 숨김 실패: {_e}")

    arc = torch.zeros(E, device=sim.device)
    prev_force = torch.zeros(E, device=sim.device)
    prev_action = torch.zeros(E, 2, device=sim.device)
    sim_t = 0.0
    control_n = 0
    force_cmd = torch.full((E,), recipe.target_contact_force_n, device=sim.device)
    feed_cmd = torch.full((E,), recipe.feed_speed_mm_s / 1000.0, device=sim.device)

    print(f"[demo] recipe {recipe} | path {path_len:.2f} m | env0=baseline env1=BC")
    force_accum = torch.zeros(E, device=sim.device)
    sub = 0
    while app.is_running():
        # ── 20Hz control step (3 substep 마다) ──
        if sub % 3 == 0 and sub > 0:
            f_mean = force_accum / 3.0
            force_accum.zero_()
            # 품질 갱신 + 관측 구성 (PolishEnv 와 동일 의미)
            obs = _build_obs(surfaces, arc, f_mean, feed_cmd, prev_force, prev_action,
                             pos_at_arc, path_len, force_cmd, env_cfg, sim.device)
            for i in range(E):
                uv = pos_at_arc(float(arc[i]))
                model.step(surfaces[i], ContactState(uv, float(f_mean[i]), recipe.rpm,
                                                     float(feed_cmd[i])), 0.05, sim_t)
            prev_force = f_mean.clone()
            # 행동: env0 = 0, env1 = BC
            a = torch.zeros(E, 2, device=sim.device)
            if policy is not None:
                a[1] = policy(obs[1:2])[0].clamp(-1, 1)
            prev_action = a.clone()
            force_cmd = recipe.target_contact_force_n * (1 + a[:, 0] * env_cfg.force_ratio_limit)
            feed_cmd = (recipe.feed_speed_mm_s / 1000.0) * (1 + a[:, 1] * env_cfg.feed_ratio_limit)
            control_n += 1
            if control_n % 40 == 0:   # 2초마다 스크래치 마커 갱신
                _update_markers(markers, scratch_specs, surfaces, scene.env_origins)

        # ── 60Hz physics substep ──
        f = contact.step(force_cmd, is_side)
        force_accum += f
        arc += feed_cmd * (1 / 60)
        sim_t += 1 / 60

        # 패드 목표: 경로점 + z = clearance (팔이 어드미턴스 압입을 그대로 재현)
        targets = torch.zeros(E, 7, device=sim.device)
        for i in range(E):
            uv = pos_at_arc(float(arc[i]))
            targets[i, 0] = uv[0] - PATCH_SIZE[0] / 2 + PATCH_CENTER[0]
            targets[i, 1] = uv[1] - PATCH_SIZE[1] / 2 + PATCH_CENTER[1]
            targets[i, 2] = WORK_TOP + float(contact.actual_clearance[i].clamp(min=-0.003))
        # 접촉면 목표 → tool0 원점 목표 (자세가 고정이므로 상수 오프셋)
        targets[:, 0] -= float(tool_offset_world[0])
        targets[:, 1] -= float(tool_offset_world[1])
        targets[:, 2] -= float(tool_offset_world[2])
        # world → base frame, 자세는 홈 기준 고정
        root = robot.data.root_pose_w.torch
        ident = torch.zeros(E, 4, device=sim.device); ident[:, 0] = 1.0
        tgt_b_pos, _ = subtract_frame_transforms(
            root[:, 0:3], root[:, 3:7], targets[:, 0:3] + scene.env_origins, ident)
        ik.set_command(torch.cat([tgt_b_pos, quat_ref_b], dim=1))

        jac = robot.data.body_link_jacobian_w.torch[:, ee_jacobi_idx, :, :][:, :, arm_joints]
        ee_w = robot.data.body_pose_w.torch[:, ee_body]
        ee_b_pos, ee_b_quat = subtract_frame_transforms(
            root[:, 0:3], root[:, 3:7], ee_w[:, 0:3], ee_w[:, 3:7])
        q = robot.data.joint_pos.torch[:, arm_joints]
        q_des = ik.compute(ee_b_pos, ee_b_quat, jac, q)
        robot.set_joint_position_target_index(target=q_des, joint_ids=arm_joints)
        # ⚠ 시연에서 패드 스핀은 끈다. 실측: pad_joint 의 회전축이 원판 법선과 **수직**이라
        #   3000 rpm 을 주면 원판이 레코드판이 아니라 **바퀴처럼 굴러** 순간순간 날이 아래를
        #   향한다 (패드면 법선이 XZ 평면에서 연속 회전, y성분 0 으로 관측).
        #   회전은 어차피 20 Hz 렌더에서 보이지 않고, 제거량·접촉력은 해석 모델(rpm 파라미터)이
        #   계산하므로 시각적으로 끄는 것이 물리 결과에 영향을 주지 않는다.
        robot.set_joint_position_target_index(
            target=torch.zeros((E, 1), device=sim.device), joint_ids=[pad_joint])
        scene.write_data_to_sim()
        sim.step(render=(sub % 3 == 0))          # 렌더는 20Hz — GUI 부하 1/3
        scene.update(1 / 60)
        sub += 1
        if sub % 600 == 0:                        # 10초마다 생존 로그 + 패드 자세 검증
            _ny = _quat_to_R(robot.data.body_pose_w.torch[0, ee_body, 3:7].cpu().numpy()) @ \
                  np.array([0.0, 0.0, -1.0])
            _cmd_q = quat_cmd_world[0].cpu().numpy(); _ach_q = robot.data.body_pose_w.torch[0, ee_body, 3:7].cpu().numpy()
            _dot = abs(float(np.dot(_cmd_q, _ach_q)))
            print(f"[demo] pad quat {np.round(robot.data.body_pose_w.torch[0,pad_body,3:7].cpu().numpy(),3)} "
                  f"pad_joint각 {float(robot.data.joint_pos.torch[0, pad_joint]):.3f} rad", flush=True)
            print(f"[demo] tool0 자세 명령{np.round(_cmd_q,3)} 달성{np.round(_ach_q,3)} "
                  f"각오차={np.degrees(2*np.arccos(min(_dot,1.0))):.1f}°", flush=True)
            print(f"[demo] 패드면 법선(세계) {np.round(_ny,3)}  ·down={float(-_ny[2]):.3f} "
                  f"(1.000 이면 면접촉)", flush=True)
            print(f"[demo] t={sim_t:.0f}s  진행 {min(arc.min().item()/path_len,1)*100:.0f}%  "
                  f"F={contact.filtered.max().item():.1f}N  "
                  f"추종오차={float((robot.data.body_pose_w.torch[:, ee_body, 0:3] - (targets[:, 0:3] + scene.env_origins)).norm(dim=1).max())*100:.1f}cm", flush=True)

        done = bool((arc >= path_len).all())
        over = args.max_seconds is not None and sim_t >= args.max_seconds
        if done or over:
            break

    # ── 결과 ──
    print("\n=== 시연 결과 (같은 상처, 같은 레시피) ===")
    for i, name in enumerate(["baseline", "BC 정책 "]):
        q = model.evaluate(surfaces[i])
        g = gloss.evaluate(surfaces[i])["summary"]
        print(f"  {name}: GU {g['gu_mean']:.2f} | 잔존 scratch {q['max_residual_scratch_um']:.3f} μm "
              f"| 정상부 과다제거 {q['healthy_overremoval_um']:.3f} μm")
    if sim.has_gui:
        print("[demo] GUI 유지 중 — 창을 닫으면 종료됩니다.")
        while app.is_running():
            sim.step()


# ── helpers ───────────────────────────────────────────────────────────────
def _extract_scratch_segments(surface):
    """스크래치 맵에서 마커용 선분(중심·방향·길이) 근사 추출 — 연결성분 PCA."""
    from scipy import ndimage
    labels, n = ndimage.label(surface.initial_scratch_depth_um > 0.05)
    segs = []
    for k in range(1, n + 1):
        i_idx, j_idx = np.nonzero(labels == k)     # ⚠ 배열 축 = (x, y) 순서 — 스왑 금지
        if len(i_idx) < 5:
            continue
        pts = np.stack([i_idx, j_idx], 1).astype(float) * surface.resolution_m
        c = pts.mean(0)
        d = pts - c
        w, v = np.linalg.eigh(d.T @ d / len(d))
        axis = v[:, -1]
        length = float((d @ axis).max() - (d @ axis).min())
        cells = (labels == k)
        segs.append({"center": c, "angle": float(np.arctan2(axis[1], axis[0])),
                     "length": max(length, 0.01), "cells": cells})
    return segs


def _update_markers(markers, segs, surfaces, env_origins, WORK_TOP=0.40):
    pos, quat, scale, idx = [], [], [], []
    for e, surf in enumerate(surfaces):
        remaining_map = np.clip(surf.initial_scratch_depth_um - surf.cumulative_removal_um, 0, None)
        for s in segs:
            init = surf.initial_scratch_depth_um[s["cells"]].max()
            rem = remaining_map[s["cells"]].max()
            ratio = float(rem / max(init, 1e-6))
            level = min(4, int((1.0 - ratio) * 5))         # 0=빨강(온전) → 4=초록(제거)
            ox, oy = float(env_origins[e][0]), float(env_origins[e][1])
            pos.append([s["center"][0] - PATCH_SIZE[0] / 2 + PATCH_CENTER[0] + ox,
                        s["center"][1] - PATCH_SIZE[1] / 2 + PATCH_CENTER[1] + oy, WORK_TOP + 0.003])
            half = s["angle"] / 2.0
            quat.append([np.cos(half), 0.0, 0.0, np.sin(half)])
            scale.append([s["length"], 1.0, 1.0])
            idx.append(level)
    import torch as th
    markers.visualize(translations=th.tensor(pos), orientations=th.tensor(quat),
                      scales=th.tensor(scale), marker_indices=th.tensor(idx))


def _build_obs(surfaces, arc, f_mean, feed_cmd, prev_force, prev_action,
               pos_at_arc, path_len, force_cmd, env_cfg, device):
    """PolishEnv._get_observations 와 같은 11차원 관측 (BC actor 입력)."""
    E = len(surfaces)
    stats = np.zeros((E, 4), dtype=np.float32)
    for i in range(E):
        s = surfaces[i]
        uv = pos_at_arc(float(arc[i]))
        res, R = s.resolution_m, 0.5 * PC.PAD_RADIUS_M
        i0 = max(int((uv[0] - R) / res), 0); i1 = min(int((uv[0] + R) / res) + 1, s.shape[0])
        j0 = max(int((uv[1] - R) / res), 0); j1 = min(int((uv[1] + R) / res) + 1, s.shape[1])
        sl = (slice(i0, i1), slice(j0, j1))
        remaining = np.clip(s.initial_scratch_depth_um[sl] - s.cumulative_removal_um[sl], 0, None)
        stats[i] = (remaining.mean(), remaining.max(), s.cumulative_removal_um[sl].mean(),
                    s.clearcoat_remaining_um[sl].min() - env_cfg.clearcoat_safety_limit_um)
    st = torch.as_tensor(stats, device=device)
    f = f_mean.unsqueeze(1)
    progress = (arc / path_len).clamp(0, 1).unsqueeze(1)
    return torch.cat([
        f / 10.0, (f - force_cmd.unsqueeze(1)) / 5.0, (f - prev_force.unsqueeze(1)) / 5.0,
        feed_cmd.unsqueeze(1) * 100.0, progress,
        st[:, 0:1] / 2.0, st[:, 1:2] / 2.0, st[:, 2:3] / 5.0, st[:, 3:4] / 20.0,
        prev_action,
    ], dim=1)


def _load_policy(ckpt_path, device):
    """BC actor 를 rsl_rl checkpoint(actor_state_dict)에서 직접 재구성."""
    try:
        from rsl_rl.models.mlp_model import MLPModel
        from tensordict import TensorDict

        dummy = TensorDict({"policy": torch.zeros(1, 11, device=device)}, batch_size=[1])
        actor = MLPModel(dummy, {"actor": ["policy"]}, "actor", 2,
                         hidden_dims=[128, 128], activation="elu", obs_normalization=True,
                         distribution_cfg={"class_name": "GaussianDistribution",
                                           "init_std": 0.3, "std_type": "scalar"}).to(device)
        ck = torch.load(ckpt_path, map_location=device, weights_only=False)
        actor.load_state_dict(ck["actor_state_dict"])
        actor.eval()

        def _policy(obs_tensor):
            td = TensorDict({"policy": obs_tensor}, batch_size=[len(obs_tensor)])
            with torch.no_grad():
                return actor(td)          # deterministic mean
        print(f"[demo] BC policy loaded: {ckpt_path}")
        return _policy
    except Exception as exc:
        print(f"[demo] ⚠ 정책 로드 실패 ({exc}) — env1 도 baseline 으로 동작")
        return None


if __name__ == "__main__":
    main()
    app.close()
