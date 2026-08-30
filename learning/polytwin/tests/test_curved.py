"""Gate 4 — 곡면 patch 생성 단위시험 (Isaac 불필요, 순수 numpy)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import numpy as np
from learning.polytwin.surface_state import make_curved_patch, make_flat_patch
from learning.polytwin.roughness_metrics import ra_um

ok = []
def check(name, cond, detail=""):
    ok.append(bool(cond))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

# 1) 법선 단위길이 + 중앙 법선 ≈ +z
for kind in ("cylinder", "sphere"):
    st = make_curved_patch(kind, 0.6, seed=3)
    norms = np.linalg.norm(st.normal_xyz, axis=-1)
    check(f"{kind}: 법선 단위길이", np.allclose(norms, 1.0, atol=1e-9))
    c = st.normal_xyz[st.shape[0]//2, st.shape[1]//2]
    check(f"{kind}: 중앙 법선 ≈ +z", c[2] > 0.999, f"nz={c[2]:.5f}")

# 2) 곡률 반경 복원 (원통: z(u) 로부터 R 역산)
st = make_curved_patch("cylinder", 0.6, seed=3)
cu = st.nominal_surface_xyz_m[..., 0][:, 0] - 0.06
z = -st.nominal_surface_xyz_m[..., 2][:, 0]
R_est = (cu[0]**2 - cu[-1]**2) / (2*(z[0]-z[-1])) if abs(z[0]-z[-1])>1e-12 else 0
# 대칭이라 끝점끼리는 상쇄 — 중앙 vs 가장자리로
R_est = (cu[0]**2) / (2*z[0])
check("cylinder: 곡률 반경 복원", abs(R_est-0.6) < 0.01, f"R_est={R_est:.4f}")

# 3) sagitta 크기 (0.12 patch, R=0.6 → ~3 mm)
sag = float((-st.nominal_surface_xyz_m[..., 2]).max())
check("sagitta 상식 범위", 0.002 < sag < 0.004, f"{sag*1000:.2f} mm")

# 4) 미세층은 평면과 동일 통계 (같은 seed → 동일 micro/scratch/clearcoat)
fl = make_flat_patch((0.12,0.12), 0.002, seed=3, with_scratches=True)
check("micro 동일(seed 고정)", np.array_equal(st.micro_height_um, fl.micro_height_um))
check("scratch 동일", np.array_equal(st.initial_scratch_depth_um, fl.initial_scratch_depth_um))
check("clearcoat 동일", np.array_equal(st.clearcoat_remaining_um, fl.clearcoat_remaining_um))

# 5) Ra 목표 유지 (detrend 가 곡률과 무관하게 micro 에서 계산됨)
check("Ra 목표 근접", abs(ra_um(st.micro_height_um) - ra_um(fl.micro_height_um)) < 1e-9)

# 6) 자세: 원통 가장자리 tilt (R=0.3, patch 0.12 → 최대 ~11.5°)
st2 = make_curved_patch("cylinder", 0.3, seed=1)
tilt = np.degrees(np.arccos(np.clip(st2.normal_xyz[..., 2], -1, 1)))
check("tilt 범위(완만 곡면 < 45°)", 5.0 < tilt.max() < 15.0, f"max tilt={tilt.max():.1f}°")

n_fail = ok.count(False)
print(f"\n{len(ok)-n_fail}/{len(ok)} 통과")
sys.exit(1 if n_fail else 0)
