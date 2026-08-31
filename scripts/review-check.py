# -*- coding: utf-8 -*-
"""문구·그림 0차 기계 점검.

사람 눈을 쓰기 전에 스크립트로 잡히는 것만 털어낸다.

    python scripts/review-check.py            # 콘솔 출력
    python scripts/review-check.py --md       # 추가로 review-report.md 기록

여기서 잡는 것은 '틀린 것'이 아니라 '봐야 할 것'이다.
판단은 사람이 한다 — 그래서 전부 근거(파일:행)를 붙인다.
"""
import os, re, sys
from collections import defaultdict, Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMGDIR = os.path.join(ROOT, 'assets', 'img')

# 검수 대상. 번들 3장은 결과물이 아니라 소스를 본다 (repack.py 로 되돌아간다)
TARGETS = [
    ('index.html',   'index.html'),
    ('sub.html',     'sub.html'),
    ('monitor.html', 'monitor.html'),
    ('1사전설정',    os.path.join('console-src', 'template.html')),
    ('4라이브러리',  os.path.join('library-src', 'template.html')),
    ('3저장',        os.path.join('save-src', 'template.html')),
]


def read(rel):
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as f:
        return f.read()


FILES = [(n, r, read(r)) for n, r in TARGETS]
FILES = [(n, r, t) for n, r, t in FILES if t is not None]

OUT = []


def emit(s=''):
    OUT.append(s)


def head(n, title, note=''):
    emit()
    emit('=' * 74)
    emit(n + '. ' + title)
    if note:
        emit('   ' + note)
    emit('=' * 74)


def lineno(text, pos):
    return text.count('\n', 0, pos) + 1


# ══════════════════════════════════════════════════════════════
# A. 이미지 — 참조 / 실물 / 선언 해상도
# ══════════════════════════════════════════════════════════════
sub = dict((r, t) for _, r, t in FILES).get('sub.html', '')

dim_block = re.search(r'const DIM = \{(.*?)\n\};', sub, re.S)
DECL = {}
if dim_block:
    for m in re.finditer(r"'([^']+\.(?:webp|jpg|jpeg|png))'\s*:\s*\[(\d+)\s*,\s*(\d+)\]",
                         dim_block.group(1)):
        DECL[m.group(1)] = (int(m.group(2)), int(m.group(3)))

REFS = [(m.group(1), m.group(2), lineno(sub, m.start()))
        for m in re.finditer(r"IMG\(\s*'([^']+)'\s*,\s*'((?:[^'\\]|\\.)*)'\s*\)", sub)]
VIDS = [(m.group(1), m.group(2), lineno(sub, m.start()))
        for m in re.finditer(r"VID\(\s*'([^']+)'\s*,\s*'((?:[^'\\]|\\.)*)'", sub)]
PHS = [(m.group(1), lineno(sub, m.start()))
       for m in re.finditer(r"PH\(\s*'((?:[^'\\]|\\.)*)'\s*\)", sub)]
FIGS = [(m.group(1), m.group(2), lineno(sub, m.start()))
        for m in re.finditer(r"FIG\(\s*'([^']+)'\s*,\s*'((?:[^'\\]|\\.)*)'\s*\)", sub)]

used = sorted(set(f for f, _, _ in REFS))

head('A', '이미지 파일 — 참조 / 실물 / 선언 해상도',
     '참조 %d건 · 고유 파일 %d개 · DIM 선언 %d개' % (len(REFS), len(used), len(DECL)))

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    emit('  ! Pillow 없음 — 실측 해상도 대조 생략')

miss, dimbad, nodecl = [], [], []
for f in used:
    p = os.path.join(IMGDIR, f)
    if not os.path.exists(p):
        miss.append(f)
        continue
    if f not in DECL:
        nodecl.append(f)
        continue
    if HAS_PIL:
        with Image.open(p) as im:
            real = im.size
        if real != DECL[f]:
            dimbad.append((f, DECL[f], real))

if miss:
    emit('  [파일 없음] %d건 — 화면에서 깨진다' % len(miss))
    for f in miss:
        emit('    - ' + f)
if nodecl:
    emit('  [DIM 선언 없음] %d건 — 로드 중 레이아웃이 튄다(CLS)' % len(nodecl))
    for f in nodecl:
        emit('    - ' + f)
if dimbad:
    emit('  [해상도 불일치] %d건 — 선언값과 실제 픽셀이 다르다' % len(dimbad))
    for f, d, r in dimbad:
        emit('    - %s  선언 %dx%d  실측 %dx%d' % (f, d[0], d[1], r[0], r[1]))
if not (miss or nodecl or dimbad):
    emit('  이상 없음')

# ── 미참조(고아) 이미지
head('A2', '미참조 이미지 — 저장소에 있는데 아무 화면도 안 쓴다')
allimg = []
for d in ('assets/img', 'assets/new_img', 'assets/icons'):
    dp = os.path.join(ROOT, d)
    if not os.path.isdir(dp):
        continue
    for fn in sorted(os.listdir(dp)):
        if fn.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.svg', '.gif')):
            allimg.append((d, fn, os.path.getsize(os.path.join(dp, fn))))

alltext = '\n'.join(t for _, _, t in FILES)
orphan = defaultdict(list)
for d, fn, sz in allimg:
    if fn not in alltext:
        orphan[d].append((fn, sz))
for d in sorted(orphan):
    tot = sum(s for _, s in orphan[d]) / 1048576.0
    emit('  %s/ — %d개 · %.1f MB' % (d, len(orphan[d]), tot))
    for fn, sz in orphan[d][:8]:
        emit('    - %s  (%.0f KB)' % (fn, sz / 1024.0))
    if len(orphan[d]) > 8:
        emit('    … 외 %d개' % (len(orphan[d]) - 8))
if not orphan:
    emit('  없음')

# ── 빈 자리
head('A3', 'PH() 빈 자리 — 채울지 말지 결정 필요', '%d건' % len(PHS))
for cap, ln in PHS:
    emit('  sub.html:%d  %s' % (ln, cap))


# ══════════════════════════════════════════════════════════════
# B. 캡션 = alt 텍스트
# ══════════════════════════════════════════════════════════════
head('B', '캡션 점검', 'sub.html 의 alt 는 캡션에서 자동 생성된다 — 캡션이 곧 접근성이다')

caps = [(c, 'IMG ' + f, ln) for f, c, ln in REFS] \
     + [(c, 'FIG ' + k, ln) for k, c, ln in FIGS] \
     + [(c, 'VID ' + f, ln) for f, c, ln in VIDS]

empty = [(c, k, ln) for c, k, ln in caps if not c.strip()]
if empty:
    emit('  [빈 캡션] %d건' % len(empty))
    for c, k, ln in empty:
        emit('    sub.html:%d  %s' % (ln, k))

bysrc = defaultdict(set)
for f, c, ln in REFS:
    bysrc[f].add(c)
multi = dict((f, cs) for f, cs in bysrc.items() if len(cs) > 1)
if multi:
    emit('  [한 이미지 · 여러 캡션] %d건 — 의도적 재사용인지 확인' % len(multi))
    for f in sorted(multi):
        emit('    ' + f)
        for c in sorted(multi[f]):
            emit('      · ' + c)

dupcap = [c for c, n in Counter(c for c, _, _ in caps if c.strip()).items() if n > 1]
if dupcap:
    emit('  [중복 캡션] %d건 — 다른 그림이 같은 설명을 달고 있다' % len(dupcap))
    for c in dupcap:
        where = ['%s@%d' % (k, ln) for cc, k, ln in caps if cc == c]
        emit('    "%s"' % c)
        emit('      ' + ' / '.join(where))

longcap = [(c, k, ln) for c, k, ln in caps if len(c) > 90]
if longcap:
    emit('  [긴 캡션 90자 초과] %d건 — 스크린리더가 통째로 읽는다' % len(longcap))
    for c, k, ln in longcap:
        emit('    sub.html:%d  (%d자) %s…' % (ln, len(c), c[:70]))
if not (empty or multi or dupcap or longcap):
    emit('  이상 없음')


# ══════════════════════════════════════════════════════════════
# C. 금지 카피 — CLAUDE.md
# ══════════════════════════════════════════════════════════════
head('C', '금지 카피 — CLAUDE.md "형용사 나열 카피"')
BANNED = ['혁신적', '직관적', '강력한', '손쉽게', '간편하게', '최첨단', '차세대',
          '완벽한', '놀라운', '스마트한', '획기적',
          'seamless', 'Seamless', 'powerful', 'Powerful',
          'intuitive', 'Intuitive', 'revolutionary', 'cutting-edge',
          '✨', '🚀', '⚡', '💡', '🔥']
hits = 0
for name, rel, text in FILES:
    for w in BANNED:
        for m in re.finditer(re.escape(w), text):
            ln = lineno(text, m.start())
            ctx = text[max(0, m.start() - 45):m.start() + 45].replace('\n', ' ')
            emit('  %s:%d  「%s」  …%s…' % (rel, ln, w, ctx.strip()))
            hits += 1
if not hits:
    emit('  이상 없음')


# ══════════════════════════════════════════════════════════════
# D. 핵심 수치 대조
# ══════════════════════════════════════════════════════════════
head('D', '핵심 수치 대조', '같은 항목의 값이 화면마다 갈리는지 본다. 판단은 사람이 한다')

KEYS = [
    ('웨이포인트',        r'웨이포인트'),
    ('접촉력',            r'접촉력'),
    ('사이클 타임',       r'사이클\s*타임|72\s*→\s*48|72→48'),
    ('깊이카메라 시점',   r'\d+\s*시점'),
    ('운영비 절감',       r'절감'),
    ('구독료',            r'구독'),
    ('리포트 단가',       r'건당'),
    ('설비투자·회수',     r'설비\s*투자|투자\s*회수'),
    ('TAM/SAM/SOM',       r'TAM|SAM|SOM'),
    ('로깅 열 수',        r'로깅'),
    ('CAGR',              r'CAGR'),
    ('ISO/TS 15066',      r'15066|65\s*N'),
]
NUM = re.compile(r'\d[\d,]*(?:\.\d+)?\s*(?:%|N|초|개|열|시점|배|억|만\s*원|만원|p|MB|kg|mm)?')

for label, pat in KEYS:
    found = defaultdict(list)
    for name, rel, text in FILES:
        for m in re.finditer(pat, text):
            ls = text.rfind('\n', 0, m.start()) + 1
            le = text.find('\n', m.start())
            le = le if le > 0 else len(text)
            line = text[ls:le]
            if len(line) > 300:
                a = max(0, m.start() - ls - 110)
                line = line[a:m.start() - ls + 110]
            for n in NUM.finditer(line):
                v = n.group().strip()
                if len(v) > 1:
                    found[v].append('%s:%d' % (rel, lineno(text, m.start())))
    if not found:
        continue
    vals = sorted(found.items(), key=lambda kv: -len(kv[1]))[:8]
    emit('  ── ' + label)
    for v, where in vals:
        uniq = sorted(set(where))[:3]
        emit('     %12s   x%-3d %s' % (v, len(where), ', '.join(uniq)))


# ══════════════════════════════════════════════════════════════
# E. 표기 통일
# ══════════════════════════════════════════════════════════════
head('E', '표기 통일', '섞여 있으면 하나로 정한다')


# 표기 통일은 '화면에 뜨는 글자'만 본다. 주석 안의 좌표 메모(-> 같은)를
# 세면 매번 오탐이 나온다 — 2026-08-31 확인하고 걷어냄.
def strip_comments(text):
    text = re.sub(r'<!--.*?-->', ' ', text, flags=re.S)
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', ' ', text)


BODY = [(n, r, strip_comments(t)) for n, r, t in FILES]


def count_all(pat, src=None):
    tot, where = 0, []
    for name, rel, text in (src or FILES):
        c = len(re.findall(pat, text))
        if c:
            tot += c
            where.append('%s(%d)' % (rel, c))
    return tot, where


STYLE = [
    ('단위 띄움  (3 N)',   r'\d\sN(?![a-zA-Z])'),
    ('단위 붙임  (3N)',    r'\dN(?![a-zA-Z])'),
    ('물결표     (3~8)',   r'\d\s*~\s*\d'),
    ('en dash    (3–8)',   r'\d\s*–\s*\d'),
    ('퍼센트 붙임 (82%)',  r'\d%'),
    ('퍼센트 띄움 (82 %)', r'\d\s%'),
    ('화살표 →',           r'→'),
    ('화살표 ->',          r'(?<!-)->(?!\s*[\{\(])'),
]
for label, pat in STYLE:
    tot, where = count_all(pat, BODY)
    if tot:
        emit('  %-22s %5d회   %s' % (label, tot, ' '.join(where[:4])))


# ══════════════════════════════════════════════════════════════
# F. CLAUDE.md 필수 규칙
# ══════════════════════════════════════════════════════════════
head('F', 'CLAUDE.md 필수 규칙')
RULES = [
    ('tabular-nums',           r'font-variant-numeric:\s*tabular-nums'),
    ('word-break: keep-all',   r'word-break:\s*keep-all'),
    (':focus-visible',         r':focus-visible'),
    ('prefers-reduced-motion', r'prefers-reduced-motion'),
    ('transition: all (금지)', r'transition:\s*all'),
]
for label, pat in RULES:
    tot, where = count_all(pat)
    mark = ' 없음 <—' if tot == 0 else '%5d회' % tot
    emit('  %-24s %s   %s' % (label, mark, ' '.join(where[:5])))


# ── 출력 ──────────────────────────────────────────────────────
report = '\n'.join(OUT)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
print(report)
if '--md' in sys.argv:
    with open(os.path.join(ROOT, 'review-report.md'), 'w', encoding='utf-8') as f:
        f.write('# 문구·그림 0차 기계 점검\n\n```\n' + report + '\n```\n')
    print('\n→ review-report.md 기록')
