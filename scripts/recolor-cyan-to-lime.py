# -*- coding: utf-8 -*-
"""
그림 속 청록(구 --accent #3E9DBE / #4FC3F7 계열)을 브랜드 연두(#9BC33A)로 옮긴다.

색상환에서 통째로 돌리지 않는다. 그러면 회청색 패널 테두리·ANSYS 컬러맵·
'등록' 초록 체크까지 같이 끌려간다. 대신
  · 색상각 168–214° 안에서만
  · 채도·명도로 가중치를 매겨(경계 화소는 거의 손대지 않는다)
  · 목표 색상각 78° 로 압축 이동하고 명도를 0.80 배 한다
       — 같은 명도에서 연두는 청록보다 밝게 보인다. 안 낮추면 선이 굵어 보인다.
결과: #4FC3F7 → 약 #9CC64A (브랜드 #9BC33A 와 사실상 같은 자리)

원본은 assets/img/_precyan_2026-08-31/ 에 있다.
"""
import sys, os, glob
import numpy as np
from PIL import Image

H_LO, H_HI = 168.0, 214.0     # 손대는 색상각 구간
H_TGT      = 78.0             # 목표(브랜드 연두)
H_SPREAD   = 0.25             # 원본 색상 변화를 얼마나 남길지
S_LO, S_HI = 0.24, 0.38       # 이 사이에서 서서히 적용 (경계 흐림)
V_LO, V_HI = 0.16, 0.28
S_MUL, V_MUL = 0.92, 0.80

SKIP = {
    'crop_ansys.webp',   # ANSYS 접촉압 컬러맵 — 무지개 스케일이라 건드리면 데이터가 거짓말이 된다
    'wide_docs.webp',    # 사실상 무채색
}

def smooth(x, lo, hi):
    t = np.clip((x - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)

def rgb2hsv(a):
    mx = a.max(2); mn = a.min(2); d = mx - mn
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    h = np.zeros_like(mx)
    m = d > 1e-6
    i = m & (mx == r); h[i] = (60 * ((g - b)[i] / d[i])) % 360
    i = m & (mx == g); h[i] = 60 * (2 + (b - r)[i] / d[i])
    i = m & (mx == b); h[i] = 60 * (4 + (r - g)[i] / d[i])
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0.0)
    return h, s, mx

def hsv2rgb(h, s, v):
    h = np.mod(h, 360.0)
    c = v * s
    x = c * (1 - np.abs(np.mod(h / 60.0, 2) - 1))
    m = v - c
    z = np.zeros_like(h)
    seg = (h / 60).astype(np.int32)
    r = np.select([seg == 0, seg == 1, seg == 2, seg == 3, seg == 4, seg == 5], [c, x, z, z, x, c], z)
    g = np.select([seg == 0, seg == 1, seg == 2, seg == 3, seg == 4, seg == 5], [x, c, c, x, z, z], z)
    b = np.select([seg == 0, seg == 1, seg == 2, seg == 3, seg == 4, seg == 5], [z, z, x, c, c, x], z)
    return np.stack([r + m, g + m, b + m], axis=-1)

def recolor(path, out):
    im = Image.open(path)
    alpha = im.getchannel('A') if im.mode in ('RGBA', 'LA') else None
    a = np.asarray(im.convert('RGB'), dtype=np.float32) / 255.0
    h, s, v = rgb2hsv(a)

    band = (h >= H_LO) & (h <= H_HI)
    # 구간 양 끝에서 부드럽게 빠지게 — 경계에서 색이 뚝 끊기면 그게 더 눈에 띈다
    edge = np.minimum(smooth(h, H_LO, H_LO + 8), 1 - smooth(h, H_HI - 8, H_HI))
    w = np.where(band, edge, 0.0) * smooth(s, S_LO, S_HI) * smooth(v, V_LO, V_HI)

    h2 = H_TGT + (h - (H_LO + H_HI) / 2) * H_SPREAD
    s2 = s * S_MUL
    v2 = v * V_MUL
    nh = np.where(w > 0, h2, h)
    ns = s + (s2 - s) * w
    nv = v + (v2 - v) * w
    if w.mean() < 2e-4:
        return None   # 옮길 화소가 없다. 괜히 재인코딩하면 세대 손실만 남는다
    out_rgb = hsv2rgb(nh, ns, nv)
    # 가중치로 원본과 섞는다 (색상은 위에서 이미 갈아탔으므로 여기서 최종 보간)
    blended = a + (out_rgb - a) * w[..., None]
    res = Image.fromarray(np.clip(blended * 255 + 0.5, 0, 255).astype(np.uint8), 'RGB')
    if alpha is not None:
        res.putalpha(alpha)
    res.save(out, 'WEBP', quality=86, method=6)
    return w.mean() * 100

if __name__ == '__main__':
    files = sorted(glob.glob('assets/img/*.webp'))
    for f in files:
        name = os.path.basename(f)
        if name in SKIP:
            print("%-24s skip" % name); continue
        before = os.path.getsize(f)
        src = os.path.join('assets/img/_precyan_2026-08-31', name)
        touched = recolor(src, f)
        if touched is None:
            print("%-24s 청록 없음, 그대로 둠" % name); continue
        after = os.path.getsize(f)
        print("%-24s %5.2f%% 화소 이동  %6.1fKB -> %6.1fKB" % (name, touched, before/1024, after/1024))
