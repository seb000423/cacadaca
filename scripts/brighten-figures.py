# -*- coding: utf-8 -*-
"""
다크 리메이크 그림이 너무 어둡다.
실측(2026-08-31): 23장 중 22장의 밝기 중앙값이 0.02–0.09.
페이지 배경 --bg-void(#08090B)가 0.003 이니 그림판이 배경과 같은 검정이고,
그림이 페이지 위에 얹힌 물체로 안 읽힌다. 선과 글자도 같이 가라앉는다.

밝기를 곱하지 않는다. 곱셈(= CSS brightness)은 0.10 을 1.3배 해봐야 0.13 이다.
감마로 아래쪽을 들어올린다.

    v' = v ** (1/GAMMA)          v = HSV 의 V (= RGB 최대 채널)

  · RGB 셋을 같은 배율(v'/v)로 민다 → HSV 의 H·S 가 정확히 보존된다.
    ANSYS 무지개 컬러맵도 값이 색상각에 있으므로 데이터가 거짓말이 되지 않는다.
  · 배율의 기준이 최대 채널이라 v' ≤ 1 인 한 어떤 채널도 클리핑되지 않는다.
  · 감마 곡선은 1.0 에 붙어 있어 흰 글자·하이라이트가 날아가지 않는다.
  · 바닥을 보호하지 않는 것이 핵심이다. 그림판이 --bg-void 에서 --bg-raised
    한 단계 위로 올라와야 그림이 페이지에서 떠오른다
    (CLAUDE.md — "다크 UI의 깊이는 그림자가 아니라 선으로, 배경 한 단계").

GAMMA 를 1.9 이상 올리면 채도가 그대로인 채 명도만 올라가 파르스름하게 뜬다.
1.35(약) / 1.55(기본) / 1.7(강) 안에서 고를 것.

이미 밝은 그림(중앙값 > SKIP_MED)은 건드리지 않는다.

원본은 assets/img/_prebright_2026-08-31/ 에 있다. 항상 원본에서 다시 굽기 때문에
멱등이다 — 세기를 바꾸려면 인자만 바꿔 다시 돌리면 되고, 누적되지 않는다.

    python scripts/brighten-figures.py [GAMMA]
"""
import sys, os, glob
import numpy as np
from PIL import Image

SRC_DIR  = 'assets/img/_prebright_2026-08-31'
OUT_DIR  = 'assets/img'
GAMMA    = 1.55
SKIP_MED = 0.35


def brighten(path, out, gamma):
    im = Image.open(path)
    alpha = im.getchannel('A') if im.mode in ('RGBA', 'LA') else None
    a = np.asarray(im.convert('RGB'), dtype=np.float32) / 255.0

    v = a.max(2)
    if float(np.median(v)) > SKIP_MED:
        return None

    nv = np.power(np.clip(v, 0.0, 1.0), 1.0 / gamma)
    gain = np.where(v > 1e-4, nv / np.maximum(v, 1e-4), 1.0)
    res_a = np.clip(a * gain[..., None], 0.0, 1.0)

    res = Image.fromarray(np.clip(res_a * 255 + 0.5, 0, 255).astype(np.uint8), 'RGB')
    if alpha is not None:
        res.putalpha(alpha)
    res.save(out, 'WEBP', quality=86, method=6)

    lum = lambda x: float(np.median(0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]))
    return lum(a), lum(res_a)


if __name__ == '__main__':
    gamma = float(sys.argv[1]) if len(sys.argv) > 1 else GAMMA
    if not os.path.isdir(SRC_DIR):
        sys.exit('원본 백업이 없다: %s' % SRC_DIR)
    print('감마 %.2f  (원본: %s)\n' % (gamma, SRC_DIR))
    total_before = total_after = 0
    for src in sorted(glob.glob(os.path.join(SRC_DIR, '*.webp'))):
        name = os.path.basename(src)
        dst = os.path.join(OUT_DIR, name)
        before = os.path.getsize(dst) if os.path.exists(dst) else 0
        r = brighten(src, dst, gamma)
        if r is None:
            print('%-24s 이미 밝다, 그대로 둠' % name); continue
        after = os.path.getsize(dst)
        total_before += before; total_after += after
        print('%-24s 밝기 중앙값 %.3f -> %.3f   %6.1fKB -> %6.1fKB'
              % (name, r[0], r[1], before / 1024, after / 1024))
    print('\n합계  %.2fMB -> %.2fMB' % (total_before / 1048576, total_after / 1048576))
