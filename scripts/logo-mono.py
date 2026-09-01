# -*- coding: utf-8 -*-
"""① 차종 선택의 제조사 마크 — 누끼 + 톤 정규화.

    python scripts/logo-mono.py

원본(`frontend/assets/icons/_orig/`)은 흰 바탕에 원색이라 어두운 패널에
그대로 못 얹는다:

  · Benz 는 JPG 라 알파가 아예 없다 — 흰 사각형이 그대로 보인다
  · 현대는 남색이라 #0C0F13 배경에 묻힌다
  · 페라리는 노란 방패가 패널에서 제일 밝은 덩어리가 된다
  · 현대 원본에는 「HYUNDAI」 워드마크가 붙어 있다 — 카드 아래 이름과
    중복이고 26px 에서는 읽히지도 않는다

네 단계를 거친다.

  1. 흰 배경 -> 알파. 채도가 있으면 무조건 잉크로 보고, 무채색은 밝기로
     부드럽게 깎는다(안티에일리어싱 가장자리를 살린다).
     BMW 흰 사분면처럼 로고 *안쪽* 흰색도 같이 뚫린다 — 어두운 배경에서는
     그게 맞다. BMW 공식 다크 로고가 정확히 그 모양이다.
  2. 회색조. 브랜드 원색을 그대로 두면 이 패널에만 색 체계가 넷 더 생기고
     DESIGN.md 「액센트 1개」 원칙이 깨진다.
  3. 잉크 평균 밝기를 TARGET 으로 감마 보정. 넷의 밝기를 맞춘다.
     잉크가 어두운 것(페라리·현대)은 먼저 반전한다. 페라리는 반전하면
     방패 바닥이 배경으로 가라앉고 윤곽·말·SF 만 남아 26px 에서 더 잘 읽힌다.
  4. optical — 바운딩박스가 아니라 눈에 보이는 덩어리로 크기를 맞춘다.
     넓은 타원(현대)은 같은 폭이면 커 보이고, 세로형(페라리)은 작아 보인다.

결과는 LA(회색조+알파) PNG 128px. 넷 합쳐 35KB 다.
CSS 에서 filter 를 또 걸지 마라 — 톤은 파일에 구워져 있다.
"""
from PIL import Image
import numpy as np
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, 'frontend', 'assets', 'icons', '_orig')
OUT = os.path.join(HERE, 'frontend', 'assets', 'icons')

#          원본           결과           반전   위쪽밴드만  광학배율
JOBS = [
    ('bmw.png',     'bmw.png',     False, False, 1.00),
    ('Benz.jpg',    'benz.png',    False, False, 1.00),
    ('ferrari.png', 'ferrari.png', True,  False, 1.06),
    ('hyundai.png', 'hyundai.png', True,  True,  0.90),
]

CANVAS = 128      # 26px 로 그리므로 레티나까지 여유
PAD = 4
TARGET = 0.80     # 잉크 평균 밝기 목표
                  # 2026-09-01 0.55 -> 0.80. 26px 에 --text-lo 카드 위라
                  # 0.55 는 안 보였다. --text-mid(#A8B0BA, 약 0.66) 를
                  # 넘겨 선택 상태에서 이름보다 먼저 읽히게 한다.


def top_band(alpha):
    """완전 투명한 행으로 갈라지는 덩어리 중 가장 높은 것만 남긴다.
    현대 원본에서 엠블럼만 떼어내는 데 쓴다(아래 워드마크를 버린다)."""
    rows = alpha.max(1) > 8
    bands, start = [], None
    for i, on in enumerate(rows):
        if on and start is None:
            start = i
        elif not on and start is not None:
            bands.append((start, i))
            start = None
    if start is not None:
        bands.append((start, len(rows)))
    return max(bands, key=lambda b: b[1] - b[0]) if bands else (0, len(rows))


def run():
    total = 0
    for src, dst, invert, band, optical in JOBS:
        im = Image.open(os.path.join(SRC, src)).convert('RGBA')
        a = np.asarray(im).astype(np.float32)
        rgb, a0 = a[..., :3], a[..., 3]
        mx, mn = rgb.max(2), rgb.min(2)
        lum = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]) / 255.0
        sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)

        soft = np.clip((0.99 - lum) / 0.05, 0, 1)
        alpha = np.clip(np.where(sat >= 0.08, 1.0, soft) * (a0 / 255.0), 0, 1)

        if band:
            y0, y1 = top_band(alpha * 255)
            alpha, lum = alpha[y0:y1], lum[y0:y1]

        g = 1.0 - lum if invert else lum
        ink = alpha > 0.5
        mean = float(g[ink].mean())
        gamma = float(np.clip(np.log(TARGET) / np.log(max(mean, 1e-3)), 0.35, 1.4))
        g = np.clip(g, 0, 1) ** gamma

        ys, xs = np.where(alpha > 0.02)
        sl = (slice(ys.min(), ys.max() + 1), slice(xs.min(), xs.max() + 1))
        g, alpha = g[sl], alpha[sl]

        lay = Image.merge('LA', (
            Image.fromarray((g * 255).astype(np.uint8), 'L'),
            Image.fromarray((alpha * 255).astype(np.uint8), 'L'),
        ))
        box = (CANVAS - 2 * PAD) * optical
        w, h = lay.size
        sc = min(box / w, box / h)
        lay = lay.resize((max(1, round(w * sc)), max(1, round(h * sc))), Image.LANCZOS)

        out = Image.new('LA', (CANVAS, CANVAS), (0, 0))
        out.paste(lay, ((CANVAS - lay.width) // 2, (CANVAS - lay.height) // 2))
        path = os.path.join(OUT, dst)
        out.save(path, optimize=True)
        size = os.path.getsize(path)
        total += size
        print('%-12s -> %-12s 반전=%-5s gamma=%.2f optical=%.2f  %dx%d  %5d B'
              % (src, dst, invert, gamma, optical, lay.width, lay.height, size))
    print('합계 %d B' % total)


if __name__ == '__main__':
    run()
