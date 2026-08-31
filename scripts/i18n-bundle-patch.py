#!/usr/bin/env python3
# ══════════════════════════════════════════════════════════════
#  ① 콘솔 · ④ 라이브러리에 언어 전환 스크립트를 심는다.
#
#  이 두 화면은 번들러 아티팩트다. 실제 문서는
#  <script type="__bundler/template"> 안에 JSON 문자열 한 덩이로 들어 있고,
#  로더가 그것을 파싱해 document.documentElement 를 통째로 갈아 끼운다.
#
#  그래서 바깥 껍데기에 <script> 를 달면 안 된다. 갈아 끼우는 순간
#  i18n 이 붙잡고 있던 body 가 문서에서 떨어져 나간다. 템플릿 안에 넣어야
#  로더의 스크립트 재생성 루프가 새 문서에서 다시 실행해 준다.
#
#  두 번 돌려도 안전하다 — 이미 있으면 건너뛴다.
#
#  같은 두 줄을 console-src/template.html · library-src/template.html 에도
#  넣어 뒀다. 그쪽이 번들의 원본이라, repack.py 로 다시 구워도 살아남는다.
#  이 스크립트는 이미 구워진 번들을 고치는 쪽이다 — 둘 다 있어야 안전하다.
#
#    python scripts/i18n-bundle-patch.py          # 심는다
#    python scripts/i18n-bundle-patch.py --check  # 심겼는지만 본다
# ══════════════════════════════════════════════════════════════
import io
import json
import os
import sys

# 정적 파일은 frontend/ 아래로 내려갔다 (2026-09-01 폴더 정리).
# 저장소 루트가 아니라 프론트 루트를 기준으로 잡는다.
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
FILES = ['PolyTwin Console.html', 'PolyTwin Library.html']
OPEN = '<script type="__bundler/template">'

# JSON 문자열 안에 그대로 넣을 형태다. 따옴표는 \" 로, </ 는 <\/ 로 —
# <\/script> 를 안 쓰면 바깥 <script> 태그가 여기서 끝나 버린다.
MARK = 'assets/js/i18n-app.js'
INSERT = (
    '\\n<!-- \\uc5b8\\uc5b4 \\uc804\\ud658 \\u2014 scripts/i18n-bundle-patch.py \\uac00 \\uc2ec\\uc5c8\\ub2e4 -->'
    '\\n<script src=\\"assets/js/i18n-app.js\\"><\\/script>'
    '\\n<script src=\\"assets/js/i18n.js\\"><\\/script>\\n'
)
BODY_END = '<\\/body>'


def block(src):
    """템플릿 JSON 문자열의 (시작, 끝) 오프셋."""
    i = src.index(OPEN) + len(OPEN)
    j = src.index('</script>', i)
    return i, j


def patch(fname, check):
    p = os.path.join(ROOT, fname)
    src = io.open(p, encoding='utf-8').read()
    i, j = block(src)
    raw = src[i:j]

    if MARK in raw:
        print('  %-24s 이미 심겨 있다' % fname)
        return 0
    if check:
        print('  %-24s 없다 — python scripts/i18n-bundle-patch.py 를 돌려라' % fname)
        return 1

    n = raw.count(BODY_END)
    if n != 1:
        print('  %-24s </body> 가 %d개 — 손대지 않는다' % (fname, n))
        return 1

    new_raw = raw.replace(BODY_END, INSERT + BODY_END)
    # 넣고 나서도 JSON 으로 읽혀야 한다. 여기서 걸리면 아무것도 쓰지 않는다.
    doc = json.loads(new_raw.strip())
    if 'i18n-app.js' not in doc or '</body>' not in doc:
        print('  %-24s 검산 실패 — 쓰지 않는다' % fname)
        return 1

    io.open(p, 'w', encoding='utf-8', newline='').write(src[:i] + new_raw + src[j:])
    print('  %-24s 심었다 (+%d바이트)' % (fname, len(new_raw) - len(raw)))
    return 0


def main():
    check = '--check' in sys.argv
    print('언어 전환 스크립트 %s' % ('확인' if check else '심기'))
    bad = 0
    for f in FILES:
        bad |= patch(f, check)
    return bad


if __name__ == '__main__':
    sys.exit(main())
