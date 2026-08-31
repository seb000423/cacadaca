# -*- coding: utf-8 -*-
"""④ 라이브러리(PolyTwin Library.html)를 다시 싼다.

번들러 결과물이라 직접 못 고친다. 편집은 `library-src/template.html` 에서 하고
이 스크립트로 되돌려 넣는다.

    python library-src/repack.py

콘솔과 달리 매니페스트에는 React 만 들어 있어 손댈 것이 없다 —
템플릿 한 줄만 갈아 끼운다.

주의: 원본 JSON 은 '/' 를 '\\/' 로 escape 한다. </script> 가 문자열 안에
그대로 들어가면 브라우저가 스크립트 블록을 거기서 끝내기 때문이다.
"""
import io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUNDLE = os.path.join(ROOT, "PolyTwin Library.html")
TEMPLATE_LINE = 402        # 0-based. 403행이 템플릿이다

lines = io.open(BUNDLE, encoding="utf-8").read().split("\n")
head = '  <script type="__bundler/template">'
if not lines[TEMPLATE_LINE].strip().startswith(head.strip()):
    sys.exit("템플릿 행이 %d 이 아니다 — 번들 구조가 바뀌었는지 확인하라" % (TEMPLATE_LINE + 1))

tpl = io.open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
enc = json.dumps(tpl, ensure_ascii=False).replace("</", "<\\/")
lines[TEMPLATE_LINE] = head + enc + "</script>"

io.open(BUNDLE, "w", encoding="utf-8", newline="").write("\n".join(lines))
print("repacked -> %s  (template %d chars)" % (os.path.basename(BUNDLE), len(tpl)))
