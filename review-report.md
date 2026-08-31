# 문구·그림 0차 기계 점검

```

==========================================================================
A. 이미지 파일 — 참조 / 실물 / 선언 해상도
   참조 35건 · 고유 파일 24개 · DIM 선언 24개
==========================================================================
  이상 없음

==========================================================================
A2. 미참조 이미지 — 저장소에 있는데 아무 화면도 안 쓴다
==========================================================================
  assets/new_img/ — 25개 · 33.4 MB
    - ChatGPT Image 2026년 8월 30일 오후 01_37_36.png  (1887 KB)
    - ChatGPT Image 2026년 8월 30일 오후 01_41_35.png  (1925 KB)
    - ChatGPT Image 2026년 8월 30일 오후 01_43_32.png  (1741 KB)
    - ChatGPT Image 2026년 8월 30일 오후 01_48_28.png  (1635 KB)
    - ChatGPT Image 2026년 8월 30일 오후 02_03_30.png  (1654 KB)
    - ChatGPT Image 2026년 8월 30일 오후 02_05_17.png  (1129 KB)
    - ChatGPT Image 2026년 8월 30일 오후 02_06_40.png  (1128 KB)
    - ChatGPT Image 2026년 8월 30일 오후 02_08_32.png  (2062 KB)
    … 외 17개

==========================================================================
A3. PH() 빈 자리 — 채울지 말지 결정 필요
   6건
==========================================================================
  sub.html:1691  디버링 실행 — 로드맵 4단계 · 힘 제어 모듈은 폴리싱과 공유
  sub.html:1694  잔여 버 리포트 — 로드맵 4단계 · 리포트 형식은 폴리싱과 공유
  sub.html:1709  입도 단계별 연마 — 로드맵 4단계 · 샌딩 킷 3D 자산만 준비됨
  sub.html:1712  영역 단위 품질 판정 — 로드맵 4단계 · 판정 로직은 폴리싱과 공유
  sub.html:1721  위치·자세 추정 — 스캔 파이프라인 재사용, 이송 전용 캡처는 미제작
  sub.html:1730  사이클 타임 계측 — 이송 포함 전체 사이클, 캡처 미제작

==========================================================================
B. 캡션 점검
   sub.html 의 alt 는 캡션에서 자동 생성된다 — 캡션이 곧 접근성이다
==========================================================================
  [한 이미지 · 여러 캡션] 7건 — 의도적 재사용인지 확인
    crop_ansys.webp
      · Ansys 사전 검증
      · 기획서 — Ansys 사전 검증
    crop_force.webp
      · 03 힘 제어 — 접촉력 추종 (x축: 초기 실행 984점)
      · 접촉력 추종 — 목표 1.5 N (x축: 초기 실행 984점)
      · 힘 제어 — 접촉력 유지 (x축: 초기 실행 984점)
    crop_path.webp
      · 02 경로 — 국소 평면·법선 추정
      · 국소 평면·법선 추정 — 영역별 경로의 기준면
      · 차체 국소 평면·법선 추정
    crop_rl_asset.webp
      · 04 자산화
      · 통과 정책만 자산으로 등록
    crop_rl_eval.webp
      · 03 전문가 평가
      · 기획서 — 전문가 평가 단계
    crop_scan.webp
      · 01 스캔 — 3D 포인트 클라우드
      · 스캔 · 영역 분할 — 스캔 파이프라인은 폴리싱과 공유
      · 스캔 — 3D 포인트 클라우드
      · 스캔 파이프라인 — 폴리싱과 공유
    crop_security.webp
      · 기획서 — 로그 이원화 설계
      · 로그 이원화

==========================================================================
C. 금지 카피 — CLAUDE.md "형용사 나열 카피"
==========================================================================
  이상 없음

==========================================================================
D. 핵심 수치 대조
   같은 항목의 값이 화면마다 갈리는지 본다. 판단은 사람이 한다
==========================================================================
  ── 웨이포인트
              813   x4   sub.html:1211, sub.html:1492, sub.html:1591
             813개   x3   sub.html:1410, sub.html:1601, sub.html:1666
           150 mm   x2   sub.html:1601, sub.html:1666
              40%   x2   sub.html:1601, sub.html:1666
              8 N   x1   sub.html:1410
              9시점   x1   sub.html:1492
  ── 접촉력
              8 N   x6   monitor.html:291, sub.html:1189, sub.html:1212
            15066   x5   sub.html:1248, sub.html:1262, sub.html:1835
            1.5 N   x5   sub.html:1264, sub.html:1489, sub.html:1605
               65   x4   sub.html:1248
              1.5   x4   sub.html:1248, sub.html:1593, sub.html:1658
              500   x3   console-src\template.html:228, library-src\template.html:161, sub.html:1489
              984   x3   sub.html:1605, sub.html:1673, sub.html:1765
             100%   x3   library-src\template.html:175, library-src\template.html:277
  ── 사이클 타임
               72   x1   sub.html:1592
               48   x1   sub.html:1592
              33%   x1   sub.html:1592
              48개   x1   sub.html:1782
           150 mm   x1   sub.html:1871
              40%   x1   sub.html:1871
             0.09   x1   sub.html:1871
             0.05   x1   sub.html:1871
  ── 깊이카메라 시점
              9시점   x6   sub.html:1492, sub.html:1597, sub.html:1598
              813   x1   sub.html:1492
              48개   x1   sub.html:1780
  ── 운영비 절감
              30%   x1   sub.html:1136
               82   x1   sub.html:1622
  ── 구독료
           396만 원   x2   sub.html:1299, sub.html:1619
            33만 원   x1   sub.html:1299
               33   x1   sub.html:1619
              4.3   x1   sub.html:1624
               2억   x1   sub.html:1633
               5억   x1   sub.html:1633
  ── 리포트 단가
           250만 원   x1   sub.html:1300
  ── 설비투자·회수
             0.2%   x4   sub.html:1347, sub.html:1617, sub.html:1626
              18억   x2   sub.html:1347, sub.html:1617
           372001   x1   sub.html:1627
             2026   x1   sub.html:1627
               1개   x1   sub.html:1627
              30%   x1   sub.html:1886
           250만 원   x1   sub.html:1886
  ── TAM/SAM/SOM
               25   x5   sub.html:1386, sub.html:1550
            31.8억   x4   sub.html:1384, sub.html:1550
             3.5억   x4   sub.html:1385, sub.html:1550
             2026   x3   sub.html:1550
            0.07%   x2   sub.html:1386
               5%   x2   sub.html:1386
  ── 로깅 열 수
              17열   x2   sub.html:1491, sub.html:1572
               17   x1   sub.html:1594
  ── ISO/TS 15066
            15066   x15  sub.html:1235, sub.html:1237, sub.html:1244
             65 N   x8   sub.html:1255, sub.html:1257, sub.html:1258
               65   x4   sub.html:1248, sub.html:1255, sub.html:1257
             2016   x4   sub.html:1266, sub.html:1835
              29개   x2   sub.html:1258, sub.html:1834
              8 N   x2   sub.html:1258, sub.html:1833
             12.3   x2   sub.html:1825
              1.5   x1   sub.html:1248

==========================================================================
E. 표기 통일
   섞여 있으면 하나로 정한다
==========================================================================
  단위 띄움  (3 N)              37회   index.html(1) sub.html(31) monitor.html(3) save-src\template.html(2)
  물결표     (3~8)              2회   monitor.html(1) console-src\template.html(1)
  en dash    (3–8)          32회   index.html(2) sub.html(26) monitor.html(1) library-src\template.html(3)
  퍼센트 붙임 (82%)             166회   index.html(42) sub.html(57) monitor.html(16) console-src\template.html(16)
  화살표 →                     30회   sub.html(25) console-src\template.html(3) library-src\template.html(2)
  화살표 ->                     2회   monitor.html(1) console-src\template.html(1)

==========================================================================
F. CLAUDE.md 필수 규칙
==========================================================================
  tabular-nums                54회   index.html(1) sub.html(19) monitor.html(1) console-src\template.html(16) library-src\template.html(16)
  word-break: keep-all        38회   index.html(2) sub.html(14) monitor.html(1) console-src\template.html(10) library-src\template.html(10)
  :focus-visible              11회   index.html(2) sub.html(2) monitor.html(1) console-src\template.html(1) library-src\template.html(1)
  prefers-reduced-motion      14회   index.html(7) sub.html(2) monitor.html(2) console-src\template.html(1) library-src\template.html(1)
  transition: all (금지)      없음 <—   
```
