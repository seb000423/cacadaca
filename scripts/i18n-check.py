#!/usr/bin/env python3
# ══════════════════════════════════════════════════════════════
#  sub.html 본문 중 사전에 없는 한국어를 찾는다.
#
#  i18n 은 「화면의 한국어 원문이 곧 키」다. 본문에 문장을 하나 추가하고
#  사전에 넣지 않으면 EN 화면의 그 문단만 한국어로 남는다 — 한 문단 안에
#  두 언어가 섞이는 게 제일 나쁘다. 본문을 고쳤으면 이걸 돌려라.
#
#    python scripts/i18n-check.py          # 누락 목록
#    python scripts/i18n-check.py --keys   # 사전에만 있고 본문에 없는 키
#
#  텍스트 노드를 흉내 내는 방식이다. 브라우저가 실제로 만드는 노드와
#  어긋나는 자리가 한 번 사고를 냈다 (2026-09-01):
#
#      <p><b>${val}</b> — ${note}</p>
#
#  런타임 노드는 「— 합성 숙련공 기준…」 하나다. 사전에는 「합성 숙련공
#  기준…」 만 있어서 맞지 않았고, 화면에서 그 줄만 한국어로 남았다.
#  값을 뽑을 때 ${...} 를 지우고 봤기 때문에 통과시켰던 것이다.
#  그래서 --glue 검사를 붙였다: 태그 경계 안에서 정적 글자와 ${} 가
#  한 노드로 붙는 자리를 찾는다. 기본 실행에도 포함된다.
# ══════════════════════════════════════════════════════════════
import os
import re
import sys

# 정적 파일은 frontend/ 아래로 내려갔다 (2026-09-01 폴더 정리).
# 저장소 루트가 아니라 프론트 루트를 기준으로 잡는다.
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
HANGUL = re.compile('[가-힣]')
TAG = re.compile('<[^>]*>')
SUBST = re.compile(r'\$\{[^{}]*\}')
ATTR = re.compile(r'(?:aria-label|alt|title|placeholder|aria-valuetext)="([^"]*)"')

# 추출기가 조각으로 내지만 브라우저에서는 다른 형태로 합쳐지는 것들.
# 사전에는 아래 오른쪽(실제 텍스트 노드)이 들어 있다.
KNOWN_SPLITS = {
    '까지 도달': ['클리어코트까지 도달', '베이스코트까지 도달', '차체 패널까지 도달'],
    '보상 함수 &nbsp;': ['보상 함수'],
    '초 구간 반복': ['20초 구간 반복'],
    # SVG 도해는 두 글자를 따로 그리지만 sr 표는 ${n}${s2} 를 한 칸에 잇는다
    '청년층': ['청년층', '청년층 15–29세'],
}

# glued() 가 잡지만 문제가 아닌 자리. 새로 생긴 것만 남기려고 여기 적어 둔다.
# 새 항목을 무심코 추가하지 마라 — 진짜 사고가 이 검사에서 나왔다.
KNOWN_GLUE = {
    '${…}까지 도달':
        '이어 붙은 형태가 그대로 사전에 있다 (KNOWN_SPLITS 참고)',
    '${…}%':
        '눈금 숫자 + % — 번역할 글자가 없다',
    # 아래는 태그 하나를 여러 템플릿으로 나눠 이어 붙이는 자리다.
    # 조각만 보면 태그 밖처럼 보이지만 실제로는 속성값이라 텍스트 노드가 아니다.
    'data-start="${…}"': '<video> 속성 조각',
    'data-end="${…}"': '<video> 속성 조각',
    'controls muted playsinline preload="metadata" aria-label="${…}">':
        '<video> 속성 조각 — aria-label 은 속성 경로로 번역된다',
    'aspect-ratio:${…}/${…};': '.vcrop style 조각',
    '--vw:${…}%;--vh:${…}%;': '.vcrop style 조각',
    '--vx:${…}%;--vy:${…}%">${…}': '.vcrop style 조각',
}


def literals(text):
    """따옴표·백틱 리터럴을 순서대로 뽑는다."""
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch in ('"', "'", '`'):
            j, buf = i + 1, []
            while j < n:
                c = text[j]
                if c == '\\':
                    buf.append(text[j:j + 2]); j += 2; continue
                if c == ch or (c == '\n' and ch != '`'):
                    break
                buf.append(c); j += 1
            if j < n and text[j] == ch:
                out.append(''.join(buf)); i = j + 1; continue
        i += 1
    return out


def pieces(v):
    """속성값을 먼저 떼고, 태그를 걷어낸 나머지에서 텍스트 조각을 낸다.

    ${...} 안에 든 따옴표 글도 화면에 나온다 — `${v ? '허용' : '차단'}` 처럼.
    치환식을 지우기만 하면 그 글이 통째로 사라지므로 먼저 건져 낸다."""
    for a in ATTR.findall(v):
        a = ' '.join(a.split())
        if HANGUL.search(a):
            yield a
    for m in SUBST.finditer(v):
        for inner in literals(m.group(0)):
            inner = ' '.join(inner.split())
            if HANGUL.search(inner):
                yield inner
    for p in TAG.split(SUBST.sub('\x00', v)):
        p = ' '.join(p.replace('\x00', ' ').split())
        if HANGUL.search(p):
            yield p


def body_strings():
    src = open(os.path.join(ROOT, 'sub.html'), encoding='utf-8').read()
    main = src[src.index('<main id="main"'):]
    seen, out = set(), []
    for lit in literals(main):
        if not HANGUL.search(lit):
            continue
        for p in pieces(lit):
            if p not in seen:
                seen.add(p); out.append(p)
    return out


def dict_keys(name):
    js = open(os.path.join(ROOT, 'assets', 'js', name), encoding='utf-8').read()
    return set(re.findall(r"^\s*'((?:[^'\\]|\\.)*)':", js, re.M))



# ── 붙어 버리는 노드 ──────────────────────────────────────────

def end_of_subst(s, i):
    """s[i:] 가 '${' 로 시작할 때, 짝이 맞는 '}' 다음 위치를 낸다.
       안에 중첩 템플릿(`…${…}…`)이 또 들어 있으므로 중괄호를 센다."""
    j, depth = i + 2, 1
    n = len(s)
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


def templates(text, base=0):
    """백틱 템플릿을 (시작 줄, 내용) 으로 낸다.

    ${...} 안에 또 템플릿이 들어 있다 — `${B.map(([k, v]) => `<p>…</p>`)}` 처럼.
    바깥 것만 보고 치환식을 통째로 건너뛰면 그 안의 마크업이 검사 밖으로
    빠진다. 실제로 그렇게 빠뜨렸다(2026-09-01). 그래서 재귀한다."""
    out, i, n = [], 0, len(text)
    while i < n:
        if text[i] == '`':
            j, depth = i + 1, 0
            while j < n:
                c = text[j]
                if c == '\\':
                    j += 2
                    continue
                if c == '`' and depth == 0:
                    break
                if text.startswith('${', j):
                    depth += 1
                    j += 2
                    continue
                if c == '}' and depth:
                    depth -= 1
                j += 1
            if j < n:
                body = text[i + 1:j]
                ln = base + text.count('\n', 0, i) + 1
                out.append((ln, body))
                k = 0
                while k < len(body):
                    if body.startswith('${', k):
                        e = end_of_subst(body, k)
                        inner_base = ln - 1 + body.count('\n', 0, k + 2)
                        out.extend(templates(body[k + 2:e - 1], inner_base))
                        k = e
                        continue
                    k += 1
                i = j + 1
                continue
        i += 1
    return out


def text_runs(tpl):
    """태그 밖 조각을 낸다. 치환식은 통째로 건너뛰고 \\x00 한 글자로 남긴다 —
       그래야 그 안의 `=>` 나 중첩 템플릿이 태그로 오해받지 않는다.
       태그 안 ${} 는 속성값이라 노드가 아니므로 버린다."""
    out, buf, i, n, intag = [], [], 0, len(tpl), False
    while i < n:
        if tpl.startswith('${', i):
            j = end_of_subst(tpl, i)
            if not intag:
                buf.append('\x00')
            i = j
            continue
        c = tpl[i]
        if c == '<' and not intag and re.match(r'</?[A-Za-z]', tpl[i:i + 3]):
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


def glued():
    """정적 글자 + ${} 가 한 노드로 붙는 자리. 사전이 절대 맞출 수 없다."""
    src = open(os.path.join(ROOT, 'sub.html'), encoding='utf-8').read()
    at = src.index('<main id="main"')
    base = src.count('\n', 0, at)          # 잘라 낸 만큼 줄 번호를 되돌린다
    hits, seen = [], set()
    for ln, tpl in templates(src[at:]):
        for r in text_runs(tpl):
            if '\x00' not in r:
                continue
            static = r.replace('\x00', '')
            if not static.strip():
                continue                      # 노드 전체가 동적값 — 그 값이 곧 키다
            if static.strip() == '&nbsp;':
                continue
            flat = ' '.join(r.replace('\x00', '${…}').split())
            if flat in KNOWN_GLUE or flat in seen:
                continue
            seen.add(flat)
            hits.append((base + ln, flat))
    return hits

def main():
    body = body_strings()
    keys = dict_keys('i18n.js') | dict_keys('i18n-sub.js')

    if '--keys' in sys.argv:
        # 본문 사전만 본다. i18n.js 는 랜딩·헤더·로그인 것이라 여기 없는 게 정상이다.
        allowed = set(body) | {v for vs in KNOWN_SPLITS.values() for v in vs}
        extra = sorted(k for k in dict_keys('i18n-sub.js')
                       if HANGUL.search(k) and k not in allowed)
        print('i18n-sub.js 에만 있고 본문에 없는 키: %d' % len(extra))
        for k in extra:
            print('   ?', k[:90])
        return 0

    missing = []
    for s in body:
        if s in keys:
            continue
        alt = KNOWN_SPLITS.get(s)
        if alt and all(a in keys for a in alt):
            continue
        missing.append(s)

    glue = glued()
    if '--glue' in sys.argv:
        print('붙어 버리는 노드: %d곳' % len(glue))
        for ln, r in glue:
            print('   sub.html:%d  %s' % (ln, r[:110]))
        return 1 if glue else 0

    print('본문 문자열 %d개 · 사전 %d개' % (len(body), len(keys)))
    bad = 0
    if missing:
        bad = 1
        print('사전에 없는 문장 %d개 — EN 에서 한국어로 남는다:' % len(missing))
        for s in missing:
            print('   -', s[:100])
    if glue:
        bad = 1
        print('정적 글자와 ${} 가 한 노드로 붙는다 %d곳 — 사전이 맞출 수 없다:' % len(glue))
        for ln, r in glue:
            print('   sub.html:%d  %s' % (ln, r[:110]))
        print('   고치는 법: 구분선을 <span class="sep"> 으로 떼어 노드를 나눈다.')
    if not bad:
        print('누락 없음')
    return bad


if __name__ == '__main__':
    sys.exit(main())
