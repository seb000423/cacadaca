#!/usr/bin/env python3
# ══════════════════════════════════════════════════════════════
#  ① 콘솔 · ② 공정 모니터링 · ④ 라이브러리에서
#  사전에 없는 한국어를 찾는다.
#
#  세 화면은 생김새가 다르다:
#    · monitor.html          평범한 HTML. 그대로 읽는다.
#    · PolyTwin Console/Library.html
#      번들러 아티팩트. 실제 문서는 <script type="__bundler/template"> 안에
#      JSON 문자열로 들어 있다. 꺼내서 읽는다 — 원본은 건드리지 않는다.
#
#  두 가지를 본다.
#    1. 노드 하나가 통째로 사전에 있는가          → PT_DICT_APP
#    2. 값과 이어 붙는 자리는 토막이 등록됐는가   → PT_PHRASES_APP
#
#    python scripts/i18n-app-check.py            # 누락 목록
#    python scripts/i18n-app-check.py --phrases  # 위험한 토막 점검
# ══════════════════════════════════════════════════════════════
import io
import json
import os
import re
import sys

# 정적 파일은 frontend/ 아래로 내려갔다 (2026-09-01 폴더 정리).
# 저장소 루트가 아니라 프론트 루트를 기준으로 잡는다.
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
HANGUL = re.compile('[가-힣]')
TAG = re.compile('<[^>]*>')
BIND = re.compile(r'\{\{.*?\}\}')
ATTR = re.compile(r'(?:aria-label|alt|title|placeholder|aria-valuetext)="([^"]*)"')
OPEN = '<script type="__bundler/template">'

# 화면 글자가 아니다 — 경로·셰이더 안 주석.
IGNORE = (
    '데이터셋/seg_best_kpi.json',
    '데이터셋/quality_kpi.json',
)
CODEISH = re.compile(r'\b(?:float|vec[234]|gl_[A-Za-z]|uniform|varying)\b')

# 소스에는 토막으로 흩어져 있지만 화면에서는 숫자와 함께 한 노드가 되는 것들.
# 그 노드는 PT_PHRASES_APP 의 정규식이 잡는다 — 소스만 보면 확인이 안 되므로
# 여기 적어 둔다. 새로 추가할 때는 실제로 정규식이 잡는지 먼저 확인해라.
REVIEWED = {
    '행': "화면에서는 '1,204행' — /(\\d)\\s*행/ 가 잡는다",
    '행 ·': "화면에서는 '1,204행 · …' — 같은 정규식",
    '스텝': "화면에서는 '#과압_12스텝' — /(\\d)\\s*스텝/ 가 잡는다",
    '초기': "화면에서는 '초기 0.0975 대비 감소' — 어순이 반대라 정규식 하나가 통째로 뒤집는다",
    '대비 감소': '위와 같은 정규식',
}


def document(fname):
    """번들이면 템플릿을 꺼내고, 아니면 파일 그대로 낸다."""
    src = io.open(os.path.join(ROOT, fname), encoding='utf-8').read()
    if OPEN not in src:
        return src
    i = src.index(OPEN) + len(OPEN)
    j = src.index('</script>', i)
    return json.loads(src[i:j].strip())


# ── 자바스크립트 리터럴 ───────────────────────────────────────

def strip_comments(js):
    out, i, n = [], 0, len(js)
    while i < n:
        c = js[i]
        if c in ('"', "'", '`'):
            j = i + 1
            while j < n:
                if js[j] == '\\':
                    j += 2
                    continue
                if js[j] == c:
                    break
                if js[j] == '\n' and c != '`':
                    break
                j += 1
            out.append(js[i:j + 1])
            i = j + 1
            continue
        if js.startswith('//', i):
            j = js.find('\n', i)
            i = n if j < 0 else j
            continue
        if js.startswith('/*', i):
            j = js.find('*/', i)
            i = n if j < 0 else j + 2
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def end_of_subst(s, i):
    j, depth, n = i + 2, 1, len(s)
    while j < n and depth:
        c = s[j]
        if c == '\\':
            j += 2
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        j += 1
    return j


def literals(js):
    """(내용) — 템플릿의 ${...} 는 \\x00 으로 남긴다."""
    out, i, n = [], 0, len(js)
    while i < n:
        ch = js[i]
        if ch in ('"', "'", '`'):
            j, buf = i + 1, []
            while j < n:
                c = js[j]
                if c == '\\':
                    buf.append({'n': '\n', 't': ' '}.get(js[j + 1], js[j + 1]) if j + 1 < n else '')
                    j += 2
                    continue
                if ch == '`' and js.startswith('${', j):
                    buf.append('\x00')
                    j = end_of_subst(js, j)
                    continue
                if c == ch or (c == '\n' and ch != '`'):
                    break
                buf.append(c)
                j += 1
            if j < n and js[j] == ch:
                out.append(''.join(buf))
                i = j + 1
                continue
        i += 1
    return out


# ── 마크업 텍스트 노드 ────────────────────────────────────────

def nodes(html):
    out, buf, i, n, intag = [], [], 0, len(html), False
    while i < n:
        c = html[i]
        if c == '<' and not intag and re.match(r'</?[A-Za-z!]', html[i:i + 3]):
            if buf:
                out.append(''.join(buf))
                buf = []
            intag = True
        elif c == '>' and intag:
            intag = False
        elif not intag:
            buf.append(c)
        i += 1
    if buf:
        out.append(''.join(buf))
    return out


def collect(fname):
    """(통째로 맞춰야 하는 것, 토막으로 맞춰야 하는 것)"""
    doc = document(fname)
    whole, glued = set(), set()

    # 스크립트 밖 마크업. {{ 바인딩 }} 은 런타임 값이다.
    markup = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', doc, flags=re.S)
    for raw in nodes(markup):
        t = ' '.join(BIND.sub('\x00', raw).replace('&nbsp;', ' ').replace('&amp;', '&').split())
        if not HANGUL.search(t):
            continue
        (glued if '\x00' in t else whole).add(t)
    for a in ATTR.findall(markup):
        a = ' '.join(BIND.sub('\x00', a).split())
        if HANGUL.search(a) and '\x00' not in a:
            whole.add(a)

    # 스크립트 안 리터럴
    for m in re.finditer(r'<script[^>]*>(.*?)</script>', doc, flags=re.S):
        for lit in literals(strip_comments(m.group(1))):
            if not HANGUL.search(lit):
                continue
            for piece in (TAG.split(lit) if '<' in lit else [lit]):
                t = ' '.join(piece.split())
                if not HANGUL.search(t) or t in IGNORE or CODEISH.search(t):
                    continue
                (glued if '\x00' in t else whole).add(t)
    return whole, glued


# ── 사전 ──────────────────────────────────────────────────────
KEY = re.compile(r"^\s*'((?:[^'\\]|\\.)*)':", re.M)
PAIR = re.compile(r"^\s*\[\s*'((?:[^'\\]|\\.)*)'\s*,", re.M)


def js(name):
    return io.open(os.path.join(ROOT, 'assets', 'js', name), encoding='utf-8').read()


def dicts():
    app = js('i18n-app.js')
    # 머리말 주석에도 이름이 나온다 — 대입문을 찾아야 한다
    cut = app.index('window.PT_PHRASES_APP')
    keys = set(KEY.findall(app[:cut])) | set(KEY.findall(js('i18n.js')))
    tail = app[cut:]
    phrases = [p for p in PAIR.findall(tail) if HANGUL.search(p)]
    # 정규식 토막. 여기 쓰는 문법은 파이썬에서도 같은 뜻이라 그대로 옮긴다.
    rx = [re.compile(p) for p in re.findall(r'^\s*\[/(.+?)/g\s*,', tail, re.M)]
    if len(keys) < 100 or len(phrases) < 20:
        raise SystemExit('사전을 제대로 읽지 못했다 (키 %d · 토막 %d) — 정규식을 확인해라'
                         % (len(keys), len(phrases)))
    return keys, phrases, rx


def covered(s, keys, phrases, rx):
    """토막들을 빼고 나면 한국어가 남지 않는가.

    소스에서 뽑은 문자열은 앞뒤 공백이 깎여 있고 토막은 공백을 품고 있다.
    실제 노드에서는 붙어 있으므로 깎은 형태로도 맞춰 본다."""
    if s in keys or s in REVIEWED:
        return True
    rest = s
    for p in sorted(phrases, key=len, reverse=True):
        rest = rest.replace(p, ' ').replace(p.strip(), ' ')
    for r in rx:
        rest = r.sub(' ', rest)
    return not HANGUL.search(rest)


# 언어 상자를 끼울 자리. i18n-app.js 의 ANCHORS 와 같은 순서여야 한다.
# 여기서는 그 선택자가 각 화면에 실제로 있는지만 본다 — 없으면 상자가 안 뜬다.
ANCHOR_SIGN = [
    ('.pt-hdr__end', re.compile(r'class="pt-hdr__end"')),
]


def anchors():
    bad = 0
    for f in ['PolyTwin Console.html', 'monitor.html', 'PolyTwin Library.html']:
        doc = document(f)
        hit = [name for name, rx_ in ANCHOR_SIGN if rx_.search(doc)]
        print('── %-24s %s' % (f, hit[0] if hit else '붙일 자리가 없다'))
        if not hit:
            bad = 1
    if bad:
        print('   i18n-app.js 의 ANCHORS 를 고쳐라 — 자리가 없으면 언어 상자가 안 뜬다.')
    return bad


def main():
    keys, phrases, rx = dicts()

    if '--anchors' in sys.argv:
        return anchors()

    if '--phrases' in sys.argv:
        # 짧은 토막이 다른 문장 안을 파고들면 반쪽짜리 영어가 된다.
        bad = []
        for p in phrases:
            inside = [k for k in keys if k != p and p in k]
            if inside:
                bad.append((p, inside))
        print('토막 %d개 · 사전 문장 안에 들어 있는 토막 %d개' % (len(phrases), len(bad)))
        for p, ins in bad:
            print("   '%s'  ⊂  %s" % (p, ins[0][:60]))
        print('   (사전이 먼저 통째로 맞추므로 위 목록은 대개 문제가 아니다.')
        print('    다만 사전에 없는 새 문장에 같은 토막이 들어 있으면 반쪽이 된다.)')
        return 0

    bad = 0
    for f in ['PolyTwin Console.html', 'monitor.html', 'PolyTwin Library.html']:
        whole, glued = collect(f)
        miss = sorted(s for s in whole
                      if s not in keys and not covered(s, keys, phrases, rx))
        gmiss = sorted(s for s in glued
                       if not covered(s.replace('\x00', '1'), keys, phrases, rx))
        print('── %-24s 노드 %3d · 이어 붙는 자리 %2d' % (f, len(whole), len(glued)))
        if miss:
            bad = 1
            print('   사전에 없다 (%d):' % len(miss))
            for s in miss:
                print('      -', s[:96])
        if gmiss:
            bad = 1
            print('   토막이 모자라다 (%d):' % len(gmiss))
            for s in gmiss:
                print('      ~', s.replace('\x00', '${}')[:96])
        if not miss and not gmiss:
            print('   누락 없음')
    return bad


if __name__ == '__main__':
    sys.exit(main())
