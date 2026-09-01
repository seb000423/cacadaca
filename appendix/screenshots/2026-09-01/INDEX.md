# PolyTwin UI 화면 캡처 — 2026-09-01

로컬 서버(`node backend/server.js`, `http://127.0.0.1:8000`)를 관리자 세션으로
띄워 Chromium 으로 캡처했다. 뷰포트 1600×1000 · DPR 2 (실제 이미지 3200×2000),
언어 KR.

| 파일 | 화면 | 상태 |
|---|---|---|
| `00-landing.png` | ⓪ 랜딩 `/index.html` | 히어로 |
| `00-landing-s02.png` ~ `s06.png` | ⓪ 랜딩 | 아래로 1000px 씩 굴리며 섹션별 (리빌 애니메이션 실행됨) |
| `01-console.png` | ① 사전 설정 `/PolyTwin Console.html` | 초기 · BMW Z4 · 로봇 1대 |
| `01-console-scroll.png` | ① 사전 설정 | 파라미터 패널 하단까지 스크롤 |
| `02-monitor.png` | ② 공정 모니터링 `/monitor.html` | 공정 시작 직후 (0.3%) |
| `02-monitor-run.png` | ② 공정 모니터링 | 진행 35% |
| `02-monitor-run2.png` | ② 공정 모니터링 | 진행 75% · 히트맵·이벤트 채워짐 |
| `02-monitor-done.png` | ② 공정 모니터링 | 진행 99% |
| `02-monitor-end.png` | ② 공정 모니터링 | 완료 직후 |
| `03-save.png` | ③ 결과 분석 `/PolyTwin Save.html` | 지표 6종 · 히트맵 · AHP 쌍대비교 |
| `03-save-scroll.png` | ③ 결과 분석 | 좌측 파라미터 목록 하단까지 |
| `04-library.png` | ④ 라이브러리 `/PolyTwin Library.html` | 그리드 · 품질순 · 15건 |
| `04-library-scroll.png` | ④ 라이브러리 | 목록 하단까지 |
| `05-admin.png` | 계정 관리 `/admin.html` | 상단 |
| `05-admin-full.png` | 계정 관리 | 전체 페이지 |
| `06-sub.png` | 솔루션 상세 `/sub.html` | 상단 |
| `06-sub-s02.png` ~ `s07.png` | 솔루션 상세 | 섹션별 |

## 캡처 방식 메모

- `.html` 은 `/` `/index.html` 을 뺀 전부가 서버에서 302 로 막힌다.
  `POST /api/login` 으로 받은 `pt_sid` 쿠키를 브라우저 컨텍스트에 심어서 열었다.
  모든 페이지 응답 200 · 리다이렉트 없음을 확인했다.
- ①③④ 는 문서 높이가 뷰포트와 같고(고정 레이아웃) 패널만 내부 스크롤한다.
  그래서 `fullPage` 대신 내부 스크롤 컨테이너를 끝까지 내려 한 장 더 찍었다.
- ② 는 **헤드리스에서 1 fps** 밖에 안 나온다(소프트웨어 GL, 3200×2000).
  공정이 진행되지 않아 GPU 창(headed)으로 다시 돌렸다. 실제 GPU 에서는
  30 fps · 약 2분 50초에 완주한다. 헤드리스로 ② 를 찍으려 하면 안 된다.
- 콘솔 오류·404 없음.
