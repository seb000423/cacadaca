"""결과 리플레이용 오프라인 IK — URDF FK + 차체 점군 충돌 페널티로 관절 궤적을 계산한다 (콘솔은 관절만 따라감).

target: 패드 중심이 셀 표면점, 툴 축(link_6 z)이 −법선(표면을 누름). 링크 표본점이 스캔 점군에 7 cm 이내면 페널티.
Isaac python(scipy) 로 실행: ~/isaacsim/python.sh learning/ui_bridge/make_car_replay.py
"""
import numpy as np
from scipy.optimize import minimize
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation as R

# rmpflow/m0609_isaac_sim.urdf — joint origin xyz/rpy, 축 z
_J = [((0, 0, 0.1345), (0, 0, 0)), ((0, 0.0062, 0), (0, -1.571, -1.571)), ((0.411, 0, 0), (0, 0, 1.571)),
      ((0, -0.368, 0), (1.571, 0, 0)), ((0, 0, 0), (-1.571, 0, 0)), ((0, -0.121, 0), (1.571, 0, 0))]
_ORG = [np.block([[R.from_euler('xyz', rpy).as_matrix(), np.array(xyz, float).reshape(3, 1)], [np.zeros((1, 3)), np.ones((1, 1))]]) for xyz, rpy in _J]
LIMITS = np.array([[-6.28, 6.28], [-6.28, 6.28], [-2.618, 2.618], [-6.28, 6.28], [-6.28, 6.28], [-6.28, 6.28]])
PAD_Z = 0.06      # link_6 원점 → 패드 접촉면 (m)


def fk(q, T_base):
    """관절 위치 목록(7: base..link6 원점)과 패드 포즈(위치, 툴 z 축) — 월드."""
    T = T_base.copy(); pts = [T[:3, 3].copy()]
    for i in range(6):
        T = T @ _ORG[i]
        c, s_ = np.cos(q[i]), np.sin(q[i])
        Rz = np.array([[c, -s_, 0, 0], [s_, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        T = T @ Rz
        pts.append(T[:3, 3].copy())
    z = T[:3, 2]
    pad = T[:3, 3] + z * PAD_Z
    return np.array(pts), pad, z


def base_T(pos, quat_wxyz):
    T = np.eye(4); T[:3, :3] = R.from_quat([quat_wxyz[1], quat_wxyz[2], quat_wxyz[3], quat_wxyz[0]]).as_matrix(); T[:3, 3] = pos
    return T


class ArmIK:
    def __init__(self, car_points: np.ndarray, clearance: float = 0.07):
        self.tree = cKDTree(car_points); self.clear = clearance

    def _cost(self, q, T_base, target, normal, seed, w_clear):
        pts, pad, z = fk(q, T_base)
        e_pos = float(np.sum((pad - target) ** 2))
        e_dir = float((1.0 + np.dot(z, normal)) ** 2)          # z 가 −normal 이면 0
        # 충돌: 링크 2~6 원점 + 중점 (패드/툴 끝은 제외)
        samp = list(pts[2:7]) + [(pts[i] + pts[i + 1]) / 2 for i in range(2, 6)]
        d, _ = self.tree.query(np.array(samp))
        e_col = float(np.sum(np.clip(self.clear - d, 0, None) ** 2))
        e_reg = float(np.sum((q - seed) ** 2))
        return 20.0 * e_pos + 1.5 * e_dir + w_clear * e_col + 0.01 * e_reg

    def solve(self, T_base, target, normal, seed, w_clear=200.0):
        best = None
        for q0 in (seed, seed + np.array([0, 0.3, -0.3, 0, 0, 0]), seed + np.array([0, -0.3, 0.3, 0, 0, 0])):
            r = minimize(self._cost, np.clip(q0, LIMITS[:, 0], LIMITS[:, 1]), args=(T_base, target, normal, seed, w_clear),
                         method='L-BFGS-B', bounds=LIMITS, options={'maxiter': 120})
            if best is None or r.fun < best.fun: best = r
        pts, pad, z = fk(best.x, T_base)
        samp = list(pts[2:7]) + [(pts[i] + pts[i + 1]) / 2 for i in range(2, 6)]
        dmin = float(self.tree.query(np.array(samp))[0].min())
        return best.x, float(np.linalg.norm(pad - target)), dmin
