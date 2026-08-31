#!/usr/bin/env python3
# ══════════════════════════════════════════════════════════════
#  그림 안에 구워진 한글을 영문으로 다시 굽는다 — <name>.en.webp 생성
#
#  원본은 건드리지 않는다. 한글이 있는 자리만 패널 배경으로 덮고
#  같은 자리에 Pretendard 로 영문을 그린다. 차체 와이어프레임·로봇·
#  레이더 차트 같은 렌더는 원본 픽셀 그대로 남는다.
#
#  글꼴은 assets/fonts/Pretendard-{300,500,700}.full-ko.woff2 에서
#  fontTools 로 풀어 쓴다 (PIL 은 woff2 를 못 읽는다).
#
#    python scripts/i18n-figures.py            # 전체
#    python scripts/i18n-figures.py wide_loop  # 한 장
#    python scripts/i18n-figures.py wide_loop --debug   # 지울 자리 빨간 상자
# ══════════════════════════════════════════════════════════════
import io, sys, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from fontTools.ttLib import TTFont

# 정적 파일은 frontend/ 아래로 내려갔다 (2026-09-01 폴더 정리).
# 저장소 루트가 아니라 프론트 루트를 기준으로 잡는다.
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
IMG  = os.path.join(ROOT, 'assets', 'img')
FONT = os.path.join(ROOT, 'assets', 'fonts')

# ── 글꼴 ─────────────────────────────────────────────────────
_cache = {}
def font(weight, size):
    key = (weight, size)
    if key in _cache: return _cache[key]
    if weight not in _cache:
        f = TTFont(os.path.join(FONT, 'Pretendard-%d.full-ko.woff2' % weight))
        f.flavor = None
        buf = io.BytesIO(); f.save(buf); _cache[weight] = buf.getvalue()
    _cache[key] = ImageFont.truetype(io.BytesIO(_cache[weight]), size)
    return _cache[key]

# ── 지우기 ────────────────────────────────────────────────────
#  사각형째 덮으면 상자를 가로지르는 레이더 선·카드 테두리가 같이 뭉갠다.
#  그래서 상자 안에서 「밝은 픽셀 = 글자」만 마스크로 뽑아 부풀린 뒤,
#  그 픽셀만 주변 배경으로 메운다. 차트 선은 마스크 밖이라 그대로 남는다.
def donor(val, m, r, start, step, n=3):
    """가장자리 픽셀 하나만 쓰면 그 한 점의 잡티가 그대로 번진다.
       마스크 밖으로 최대 세 픽셀을 모아 중앙값을 쓴다."""
    W = m.shape[1]
    got = []
    x = start
    while 0 <= x < W and len(got) < n:
        if not m[r, x]:
            got.append(val[r, x])
        x += step
    if not got:
        return None
    return np.median(np.stack(got), axis=0)


def erase(im, box, th=150, grow=3, iters=40):
    x0, y0, x1, y1 = box
    P = grow + 2                                  # 바깥 여백 — 메울 재료
    W, H = im.size
    px0, py0 = max(0, x0 - P), max(0, y0 - P)
    px1, py1 = min(W, x1 + P), min(H, y1 + P)

    sub = np.asarray(im.crop((px0, py0, px1, py1)), dtype=np.float32)
    lum = sub.mean(2)

    m = np.zeros(lum.shape, bool)
    a, b = y0 - py0, y1 - py0
    c, d = x0 - px0, x1 - px0
    # th 가 음수면 밝은 바탕 위의 어두운 글자다 (흰 말풍선 안 검은 글씨)
    sel = lum[a:b, c:d] < -th if th < 0 else lum[a:b, c:d] > th
    m[a:b, c:d] = sel                                # 글자는 상자 안에서만 찾는다
    if not m.any():
        return False
    if grow:
        mi = Image.fromarray((m * 255).astype(np.uint8))
        mi = mi.filter(ImageFilter.MaxFilter(grow * 2 + 1))
        m = np.asarray(mi) > 127
        # 부풀린 마스크가 상자 밖으로 새면 옆의 그림(드롭다운 화살표 같은)을
        # 같이 먹는다. 상자가 곧 허가 범위다 — 여백은 상자에 넣어라.
        keep = np.zeros_like(m); keep[a:b, c:d] = True
        m &= keep

    val = sub.copy()
    todo = m.copy()

    # ① 같은 줄에서 좌우로 보간한다.
    #    사방으로 번지게 두면 상자 밖(드롭다운 밖 패널 배경 같은)의 다른 색이
    #    끌려 들어와 얼룩이 된다. 글자 좌우는 거의 언제나 같은 배경이다.
    for r in range(m.shape[0]):
        row = m[r]
        if not row.any():
            continue
        i = 0
        n = row.size
        while i < n:
            if not row[i]:
                i += 1; continue
            j = i
            while j < n and row[j]:
                j += 1
            L = donor(val, m, r, i - 1, -1)
            R = donor(val, m, r, j, +1)
            if L is None and R is None:
                i = j; continue
            if L is None: L = R
            if R is None: R = L
            # 한쪽 기증 픽셀이 훨씬 밝으면 배경이 아니라 다른 글자·아이콘의
            # 가장자리다(드롭다운 화살표 같은). 어두운 쪽을 배경으로 본다.
            if abs(L.mean() - R.mean()) > 25:
                pick = max if th < 0 else min      # 바탕은 글자 반대쪽 밝기다
                L = R = L if L.mean() == pick(L.mean(), R.mean()) else R
            span = j - i
            for k in range(span):
                t = (k + 1) / (span + 1)
                val[r, i + k] = L + (R - L) * t
            todo[r, i:j] = False
            i = j

    # ② 줄 전체가 마스크라 좌우가 없던 자리만 확산으로 마무리한다
    if todo.any():
        known = ~todo
        k = known.astype(np.float32)
        v = val * known[..., None]
        for _ in range(iters):
            if known.all():
                break
            vs = np.zeros_like(v); ks = np.zeros_like(k)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    vs += np.roll(np.roll(v, dy, 0), dx, 1)
                    ks += np.roll(np.roll(k, dy, 0), dx, 1)
            fill = (ks > 0) & ~known
            with np.errstate(invalid='ignore', divide='ignore'):
                avg = vs / np.maximum(ks, 1e-6)[..., None]
            v[fill] = avg[fill]; k[fill] = 1.0
            known = known | fill
        val[todo] = v[todo]

    # 보간은 매끈해서 원본의 미세한 얼룩과 결이 다르다. 마스크 자리만
    # 아주 옅게 흐려 경계를 지운다.
    sm = Image.fromarray(np.clip(val, 0, 255).astype(np.uint8))
    sm = sm.filter(ImageFilter.GaussianBlur(0.6))
    val = np.where(m[..., None], np.asarray(sm, dtype=np.float32), val)

    out = np.clip(val, 0, 255).astype(np.uint8)
    im.paste(Image.fromarray(out), (px0, py0))
    return True

# ── 그리기 ────────────────────────────────────────────────────
_cmap = None
def check(item, name):
    """폰트에 없는 문자는 두부(□)로 나온다. 조용히 나가면 나중에 발견한다."""
    global _cmap
    if _cmap is None:
        f = TTFont(os.path.join(FONT, 'Pretendard-500.full-ko.woff2'))
        _cmap = set(f.getBestCmap())
    if 'segs' in item:
        lines = [''.join(t for t, _ in item['segs'])]
    else:
        lines = item['t'] if isinstance(item['t'], (list, tuple)) else [item['t']]
    bad = sorted({c for l in lines for c in l if ord(c) not in _cmap})
    if bad:
        raise SystemExit('%s: 폰트에 없는 문자 %s — %r' %
                         (name, [hex(ord(c)) for c in bad], lines[0]))


def draw_segs(d, item, name=''):
    """한 줄 안에서 색이 바뀌는 글(강조 숫자 같은). 조각을 이어 그린다."""
    x, y = item['at']
    weight, size = item.get('w', 500), item['s']
    cap = item.get('max')
    segs = item['segs']
    while size > 8:
        f = font(weight, size)
        if not cap or sum(f.getlength(t) for t, _ in segs) <= cap:
            break
        size -= 1
    if size != item['s']:
        print('   · %s: %r 폭 초과 → %d → %dpx' % (name, segs[0][0][:20], item['s'], size))
    f = font(weight, size)
    total = sum(f.getlength(t) for t, _ in segs)
    cx = x - total / 2 if item.get('a', 'c') == 'c' else x
    for t, col in segs:
        d.text((cx, y), t, font=f, fill=col, anchor='lm')
        cx += f.getlength(t)


def draw_text(d, item, name=''):
    """anchor: 'c' 중앙 · 'l' 왼쪽 · 'r' 오른쪽 (모두 세로 중앙 기준)
       max 를 주면 그 폭에 들어갈 때까지 크기를 줄인다 — 영문은 한글보다 길다."""
    x, y = item['at']
    if 'segs' in item:
        return draw_segs(d, item, name)
    lines = item['t'] if isinstance(item['t'], (list, tuple)) else [item['t']]
    weight, size = item.get('w', 500), item['s']
    cap = item.get('max')
    if cap:
        while size > 8:
            f = font(weight, size)
            if max(f.getlength(l) for l in lines) <= cap: break
            size -= 1
        if size != item['s']:
            print('   · %s: %r 폭 초과 → %d → %dpx' % (name, lines[0][:24], item['s'], size))
    f = font(weight, size)
    lh = item.get('lh', int(size * 1.55))
    fill = item.get('c', '#FFFFFF')
    anc = {'c': 'mm', 'l': 'lm', 'r': 'rm'}[item.get('a', 'c')]
    y0 = y - (len(lines) - 1) * lh / 2
    for i, ln in enumerate(lines):
        d.text((x, y0 + i * lh), ln, font=f, fill=fill, anchor=anc)

def build(name, spec, debug=False):
    src = os.path.join(IMG, spec['src'])
    im = Image.open(src).convert('RGB')
    th, grow = spec.get('th', 150), spec.get('grow', 3)
    if debug:
        d = ImageDraw.Draw(im)
        for b in spec['erase']:
            d.rectangle(tuple(b[:4]), outline=(255, 60, 60), width=2)
        out = os.path.join(IMG, '_debug_%s.png' % name)
        im.save(out); print('debug →', out); return
    for b in spec['erase']:
        bx = tuple(b[:4])
        bt = b[4] if len(b) > 4 else th
        bg = b[5] if len(b) > 5 else grow
        if not erase(im, bx, bt, bg):
            print('   · %s: %s 에서 지울 글자를 못 찾았다' % (name, bx))
    d = ImageDraw.Draw(im)
    for it in spec['text']:
        check(it, name)
        draw_text(d, it, name)
    out = os.path.join(IMG, spec['out'])
    if out.lower().endswith(('.jpg', '.jpeg')):
        im.save(out, 'JPEG', quality=spec.get('q', 88), subsampling=0, optimize=True)
    else:
        im.save(out, 'WEBP', quality=spec.get('q', 88), method=6)
    print('%-26s %s  %d KB' % (spec['out'], im.size, os.path.getsize(out) // 1024))

def audit(name, spec, th=100, E=12):
    """상자가 글자를 다 덮는지 본다.
       글자 획 하나가 상자 밖으로 삐져나가면 지운 자리 옆에 부스러기가 남는다 —
       상자 안의 밝은 픽셀에서 이어지는 덩어리가 상자를 넘는지 검사한다."""
    im = Image.open(os.path.join(IMG, spec['src'])).convert('RGB')
    W, H = im.size
    a = np.asarray(im, dtype=np.float32).mean(2)
    bad = 0
    for b in spec['erase']:
        x0, y0, x1, y1 = b[:4]
        ex0, ey0 = max(0, x0 - E), max(0, y0 - E)
        ex1, ey1 = min(W, x1 + E), min(H, y1 + E)
        bt = b[4] if len(b) > 4 else th
        sub = a[ey0:ey1, ex0:ex1] < -bt if bt < 0 else a[ey0:ey1, ex0:ex1] > bt
        seed = np.zeros_like(sub)
        seed[y0 - ey0:y1 - ey0, x0 - ex0:x1 - ex0] = sub[y0 - ey0:y1 - ey0, x0 - ex0:x1 - ex0]
        # 4방향 확장으로 상자 안 획과 이어진 픽셀을 전부 모은다
        cur = seed.copy()
        for _ in range(E * 2):
            nxt = cur.copy()
            nxt[1:, :] |= cur[:-1, :]; nxt[:-1, :] |= cur[1:, :]
            nxt[:, 1:] |= cur[:, :-1]; nxt[:, :-1] |= cur[:, 1:]
            nxt &= sub
            if (nxt == cur).all():
                break
            cur = nxt
        out = cur.copy()
        out[y0 - ey0:y1 - ey0, x0 - ex0:x1 - ex0] = False
        if out.any():
            ys, xs = np.nonzero(out)
            print('   ! %s 상자 %s 밖으로 %d px : x %d..%d  y %d..%d 까지 이어진다'
                  % (name, (x0, y0, x1, y1), out.sum(),
                     ex0 + xs.min(), ex0 + xs.max(), ey0 + ys.min(), ey0 + ys.max()))
            bad += 1
    print('%s: 상자 %d개 중 %d개가 글자를 다 못 덮는다' % (name, len(spec['erase']), bad))


SPECS = {}
def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    debug = '--debug' in sys.argv
    names = args or list(SPECS)
    for n in names:
        if n not in SPECS: sys.exit('알 수 없는 이름: %s' % n)
        if '--audit' in sys.argv:
            audit(n, SPECS[n])
        else:
            build(n, SPECS[n], debug)

if __name__ == '__main__':
    from figspec import SPECS as S      # 사양은 옆 파일에 둔다 — 길다
    SPECS.update(S)
    main()
