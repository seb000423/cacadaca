# -*- coding: utf-8 -*-
"""① 사전 설정 화면(PolyTwin Console.html)을 다시 싼다.

`PolyTwin Console.html` 은 번들러가 뱉은 결과물이라 직접 고칠 수 없다.
편집은 이 폴더의 두 파일에서 하고, 이 스크립트로 되돌려 넣는다.

    console-src/template.html   ->  402행 __bundler/template   (JSON 문자열)
    console-src/viewport.js     ->  391행 __bundler/manifest    (gzip + base64)

    python console-src/repack.py

풀어낼 때는 반대로 하면 된다 — 두 payload 를 JSON 으로 읽고,
viewport 는 base64 디코드 후 gunzip 한다.

주의: 원본 JSON 은 '/' 를 '\\/' 로 escape 한다. </script> 가 문자열 안에
그대로 들어가면 브라우저가 스크립트 블록을 거기서 끝내 버리기 때문이다.
그 규칙을 지켜야 바이트가 맞는다.
"""
import io, json, base64, gzip, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUNDLE = os.path.join(ROOT, "PolyTwin Console.html")
VP_UUID = "79b1de60-ed4e-4e8e-88e9-89de853dfefc"   # 매니페스트 안의 뷰포트 모듈

MANIFEST_LINE = 390        # 0-based
TEMPLATE_LINE = 401

lines = io.open(BUNDLE, encoding="utf-8").read().split("\n")

man = json.loads(lines[MANIFEST_LINE])
if VP_UUID not in man:
    sys.exit("매니페스트에 뷰포트 모듈이 없다 — 번들 구조가 바뀌었는지 확인하라")

js = io.open(os.path.join(HERE, "viewport.js"), encoding="utf-8").read().encode("utf-8")
entry = man[VP_UUID]
if entry.get("compressed"):
    # mtime=0. 안 그러면 내용이 같아도 구울 때마다 바이트가 달라진다
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(js)
    blob = buf.getvalue()
else:
    blob = js
entry["data"] = base64.b64encode(blob).decode("ascii")
lines[MANIFEST_LINE] = json.dumps(man, ensure_ascii=False, separators=(",", ":"))

tpl = io.open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
enc = json.dumps(tpl, ensure_ascii=False).replace("</", "<\\/")
lines[TEMPLATE_LINE] = '  <script type="__bundler/template">' + enc + "</script>"

io.open(BUNDLE, "w", encoding="utf-8", newline="").write("\n".join(lines))
print("repacked -> %s\n  template %d chars\n  viewport %d bytes (gz %d)"
      % (os.path.basename(BUNDLE), len(tpl), len(js), len(blob)))
