# -*- coding: utf-8 -*-
"""③ 데이터 저장(PolyTwin Save.html)을 다시 싼다.

번들러 결과물이라 직접 못 고친다. 편집은 `save-src/template.html` 에서 하고
이 스크립트로 되돌려 넣는다.

    python save-src/repack.py

주의: 이 번들의 escape 규칙은 콘솔·라이브러리와 다르다.
콘솔·라이브러리는 '</' 를 '<\\/' 로 쓰는데 이쪽은 '<\\u002F' 로 쓴다.
둘 다 브라우저가 문자열 안의 </script> 에서 블록을 끊는 것을 막는 장치다 —
규칙을 섞으면 diff 가 통째로 흔들리므로 원본 방식을 그대로 따른다.
"""
import io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUNDLE = os.path.join(ROOT, "PolyTwin Save.html")
TEMPLATE_LINE = 403        # 0-based. 404행이 페이로드다 (403행은 여는 태그)
SLASH = "<" + chr(92) + "u002F"

lines = io.open(BUNDLE, encoding="utf-8").read().split("\n")
# 콘솔·라이브러리와 달리 여는 태그와 페이로드가 별도 행이다
if lines[TEMPLATE_LINE - 1].strip() != '<script type="__bundler/template">':
    sys.exit("템플릿 행이 %d 이 아니다. 번들 구조가 바뀌었는지 확인하라" % (TEMPLATE_LINE + 1))

tpl = io.open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
enc = json.dumps(tpl, ensure_ascii=False).replace("</", SLASH)
lines[TEMPLATE_LINE] = enc

io.open(BUNDLE, "w", encoding="utf-8", newline="").write("\n".join(lines))
print("repacked -> %s  (template %d chars)" % (os.path.basename(BUNDLE), len(tpl)))
