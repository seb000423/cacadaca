# -*- coding: utf-8 -*-
# ══════════════════════════════════════════════════════════════
#  i18n-figures.py 가 읽는 사양. 좌표는 원본 픽셀에서 실측한 값이다 —
#  밝은 픽셀의 가로 띠를 뽑아서 쟀다. 눈대중 상자를 쓰면 카드 테두리나
#  레이더 차트 선까지 같이 지워진다.
#
#  erase: (x0, y0, x1, y1[, th[, grow]])
#         상자 안에서 밝기 th 를 넘는 픽셀만 글자로 보고 grow 만큼 부풀려
#         그 픽셀만 메운다. 발광(glow)이 있는 글자는 th 를 낮춰라.
#  text : at=(x, y) 는 세로 중앙 기준. a='l' 이면 x 가 왼쪽 끝.
#         max 를 넘으면 크기를 줄인다 — 영문은 한글보다 길다.
#
#  ⚠ Pretendard 서브셋에는 ASCII 밖 문자가 없다. 가운뎃점·따옴표·화살표를
#    쓰면 두부(□)가 된다. i18n-figures.py 의 check() 가 막는다.
#
#  영문 낱말은 assets/js/i18n.js 사전과 맞춘다 —
#  본문에서 Coverage 라 부르는 것을 그림에서 Area 라 부르면 안 된다.
# ══════════════════════════════════════════════════════════════

W   = '#FFFFFF'          # 제목
T   = (226, 237, 251)    # 본문·라벨
GR  = (175, 206, 123)    # 숙련공(연두)
OR  = (250, 180, 135)    # 실행 결과(주황)
OR2 = (232, 196, 155)    # ⑤ 재설정 라벨
PT  = (231, 244, 253)    # wide_path 캡션
PA  = (186, 206, 220)    # wide_path 차트 축 라벨
RH  = (216, 231, 237)    # rl 부제
RG  = (110, 228, 162)    # rl 판정 · 등록
RR  = (244, 153, 166)    # rl 판정 · 제외
SL  = (196, 206, 214)    # wide_result 보조 라벨
SV  = (236, 243, 249)    # wide_result 표 값
SY  = (190, 210, 228)    # wide_system 본문
SY2 = (160, 184, 204)    # wide_system 보조(표·목록)
SYG = (70, 205, 130)     # wide_system 유사 표시
BK  = (17, 17, 17)       # 말풍선 글자

def seg(x, y, parts, s=18, w=500, mx=None, a='c'):
    d = dict(at=(x, y), segs=parts, s=s, w=w, a=a)
    if mx: d['max'] = mx
    return d

TITLE = dict(w=700, s=26, c=W, a='l')
CAP   = dict(w=300, s=20, c=T, a='c')
LBL   = dict(w=500, s=17, c=T, a='c')

def title(x, y, t, mx, s=26, c=W, a='l'):
    return dict(TITLE, at=(x, y), t=t, max=mx, s=s, c=c, a=a)
def cap(x, y, ls, lh, mx, s=20, c=T, a='c'):
    return dict(CAP, at=(x, y), t=ls, lh=lh, max=mx, s=s, c=c, a=a)
def lbl(x, y, t, s=17, c=T, a='c', mx=None, w=500):
    d = dict(LBL, at=(x, y), t=t, s=s, c=c, a=a, w=w)
    if mx: d['max'] = mx
    return d

# 레이더 축 다섯. 두 차트가 나란히 서는 ④ 가 제일 좁아서 낱말 하나로 줄였다.
# 풀네임(contact force, feed speed …)은 ③ 캡션이 적는다.
AX = ['Force', 'Speed', 'Time', 'Coverage', 'Contact']
R4 = 13     # ④ 는 차트 두 개가 붙어 있어 ③ 보다 작게 쓴다

SPECS = {
  'wide_loop': dict(
    src='wide_loop.webp', out='wide_loop.en.webp', th=120, grow=3,
    erase=[
      # ① UI 파라미터 설정
      (153, 43, 400, 80), (65, 229, 140, 357),
      (354, 285, 379, 303, 55), (354, 338, 410, 356, 55),
      (76, 369, 428, 424),
      # ② 폴리트윈 공정 실행
      (712, 43, 990, 80), (697, 336, 940, 422),
      # ③ 결과값 측정 및 분석
      (1286, 44, 1560, 80),
      (1362, 94, 1415, 118), (1198, 177, 1302, 207),
      (1474, 177, 1562, 206), (1258, 293, 1334, 316),
      (1460, 293, 1529, 316), (1246, 336, 1511, 422),
      # ④ 숙련공 데이터와 비교
      (144, 504, 407, 540),
      (122, 555, 172, 577), (39, 598, 102, 634),
      (200, 602, 272, 628), (47, 698, 111, 720),
      (184, 699, 244, 720),
      (346, 555, 393, 577), (261, 598, 319, 634),
      (421, 602, 478, 628), (269, 699, 334, 720),
      (400, 699, 466, 720),
      (96, 725, 200, 753, 55, 4), (306, 725, 430, 753, 55, 4),
      (129, 772, 358, 876),
      # ⑤ 오차 역추적 및 보정
      (716, 504, 962, 540), (741, 732, 909, 757, 55, 4),
      (651, 772, 966, 878),
      # ⑥ 결과 저장 (기술 보존)
      (1279, 504, 1560, 540), (1241, 772, 1521, 876),
    ],
    text=[
      # ① ─────────────────────────────────────────────
      title(156, 61, 'UI parameter setup', 340),
      lbl(69, 241, 'Path mode', a='l', mx=100),
      lbl(69, 267, 'Force (N)', a='l', mx=100),
      lbl(69, 293, 'Robots',    a='l', mx=100),
      lbl(69, 319, 'Work area', a='l', mx=100),
      lbl(69, 346, 'Target',    a='l', mx=100),
      lbl(357, 293, '3',     s=15, a='l', mx=50),
      lbl(357, 346, 'Panel', s=15, a='l', mx=50),
      cap(251, 397, ['The user sets path mode, force (N), robot',
                     'count, work area and target.'], 27, 420),
      # ② ─────────────────────────────────────────────
      title(715, 62, 'PolyTwin process run', 340),
      cap(818, 380, ['The robot generates the path',
                     'and runs polishing from the',
                     'parameters that were set.'], 29, 330),
      # ③ ─────────────────────────────────────────────
      title(1291, 62, 'Measurement and analysis', 355),
      lbl(1388, 106, AX[0]), lbl(1518, 191, AX[1]),
      lbl(1494, 304, AX[2]), lbl(1294, 304, AX[3]),
      lbl(1249, 191, AX[4]),
      cap(1378, 380, ['Contact force, feed speed, cycle time,',
                      'coverage and surface contact are',
                      'measured and analysed.'], 29, 350),
      # ④ ─────────────────────────────────────────────
      title(149, 522, 'Compare with veteran data', 345),
      lbl(148, 566, AX[0], s=R4), lbl(230, 615, AX[1], s=R4),
      lbl(215, 709, AX[2], s=R4), lbl( 78, 709, AX[3], s=R4),
      lbl( 71, 616, AX[4], s=R4),
      lbl(370, 566, AX[0], s=R4), lbl(450, 615, AX[1], s=R4),
      lbl(434, 709, AX[2], s=R4), lbl(302, 709, AX[3], s=R4),
      lbl(290, 616, AX[4], s=R4),
      lbl(148, 739, 'Veteran data', c=GR),
      lbl(368, 739, 'Run result',   c=OR),
      cap(245, 824, ['Compared against the veteran',
                     'result, error and deviation',
                     'are quantified.'], 38, 300),
      # ⑤ ─────────────────────────────────────────────
      title(719, 522, 'Error trace-back and fix', 340),
      lbl(826, 744, 'Path / force / speed reset', c=OR2, mx=190),
      cap(806, 825, ['Trace back the segments with the',
                     'largest error, find the cause, and',
                     'correct path / force / speed.'], 39, 340),
      # ⑥ ─────────────────────────────────────────────
      title(1282, 522, 'Save result (technique kept)', 365),
      cap(1377, 824, ['When the result comes close to',
                      'the veteran data, it is saved',
                      'as technique data.'], 38, 330),
    ]),

  # ── 경로 생성 6단계 ── 제목·캡션만 한글이다. min/Max·J1–J6·눈금은 영문 ──
  'wide_path': dict(
    src='wide_path.webp', out='wide_path.en.webp', th=120, grow=3,
    erase=[
      (89, 43, 284, 71),    (61, 376, 453, 403), (163, 416, 349, 443),
      (609, 43, 884, 71),   (573, 377, 958, 402), (561, 416, 972, 443),
      (1115, 43, 1231, 71), (1111, 379, 1423, 405),
      (89, 526, 328, 553),  (66, 860, 457, 887),
      (606, 526, 852, 553), (590, 861, 932, 888), (605, 899, 909, 926),
      (1114, 526, 1282, 553), (1074, 861, 1491, 888), (1122, 899, 1422, 926),
      (543, 573, 602, 596), (693, 801, 778, 823),
    ],
    text=[
      title(92, 56, 'Robot arm reach', 395, s=24),
      cap(256, 409, ['The working range is set from the',
                     "arm's minimum and maximum reach."], 40, 440, s=21, c=PT),
      title(612, 56, 'Local plane and normal', 390, s=24),
      cap(765, 409, ['A KDTree defines the local plane so the',
                     'tool meets the surface at a right angle.'], 40, 440, s=21, c=PT),
      title(1118, 56, 'Path continuity', 385, s=24),
      cap(1266, 391, ['Path holds after the robot moves on the rail.'], 40, 450, s=21, c=PT),
      title(92, 539, 'Path inside the boundary', 395, s=24),
      cap(261, 873, ['The path must stay inside the vehicle boundary.'], 40, 450, s=21, c=PT),
      title(609, 539, 'Joint rotation range', 390, s=24),
      cap(758, 893, ['Check that every joint can reach the',
                     'target angle at each path point.'], 38, 440, s=21, c=PT),
      title(1117, 539, 'Collision check', 385, s=24),
      cap(1277, 893, ['Every part of the robot must stay outside',
                      'the vehicle; inside means a collision.'], 38, 450, s=21, c=PT),
      lbl(546, 584, 'Angle (deg)', s=17, c=PA, a='l', mx=110),
      lbl(735, 811, 'Waypoint',    s=18, c=PA, mx=110),
    ]),

  # ── 스캔 1회 → 학습 환경 48개 ── 이 그림이 제일 빽빽하다.
  #    Expert Evaluation · Agent · J·숫자·%·N 은 원래 영문이라 건드리지 않는다 ──
  'wide_rl_overview': dict(
    src='wide_rl_overview.webp', out='wide_rl_overview.en.webp', th=120, grow=3,
    erase=[
      (390, 12, 1416, 60), (618, 73, 1184, 104),
      # ① 환경 생성
      (189, 149, 304, 182), (81, 194, 395, 218), (90, 246, 163, 271),
      (281, 241, 400, 266), (255, 296, 428, 322), (273, 348, 408, 372),
      (50, 433, 201, 456), (50, 461, 202, 482), (273, 448, 407, 472),
      (89, 571, 409, 606),
      # ② 정책 학습
      (666, 149, 781, 182), (536, 194, 876, 218), (682, 234, 739, 258),
      (565, 274, 628, 298), (767, 275, 878, 299), (800, 305, 846, 328),
      (643, 367, 777, 391), (668, 411, 750, 435), (552, 442, 866, 464),
      (540, 591, 878, 615),
      # ③ 전문가 평가
      (1110, 149, 1253, 183), (1042, 195, 1290, 218),
      (1247, 284, 1327, 305), (1247, 321, 1327, 342),
      (1247, 359, 1327, 380), (1247, 397, 1312, 418),
      (1052, 473, 1317, 497), (1177, 535, 1257, 559), (1179, 562, 1259, 586),
      # ④ 자산화 — 판정 칸의 체크·엑스 표시(x<1691)는 남긴다
      (1581, 149, 1664, 183), (1474, 195, 1727, 218),
      (1467, 238, 1503, 261), (1552, 239, 1640, 261), (1692, 239, 1726, 261),
      (1692, 276, 1739, 298), (1692, 314, 1739, 336), (1692, 352, 1737, 374),
      (1692, 390, 1738, 412), (1692, 428, 1738, 450),
      (1465, 524, 1729, 552), (1465, 563, 1729, 587),
      # 하단 되먹임 띠
      (394, 712, 1172, 736),
    ],
    text=[
      title(902, 35, 'One scan grows into 48 RL datasets', 1300, s=49, a='c'),
      cap(900, 88, ['No extra scan; changing the conditions alone keeps the datasets growing.'],
          30, 1000, s=26, c=RH),
      # ① ─────────────────────────────────────────────
      title(192, 165, 'Environment build', 270, s=26),
      cap(237, 205, ['One scan expands to 48 training environments'], 26, 400, s=19),
      lbl(126, 258, 'One scan', s=19),
      seg(340, 253, [('Path patterns  ', W), ('3', GR)], s=18, w=700, mx=180),
      lbl(344, 307, 'Orbital / Spiral / Linear', s=13, mx=180),
      seg(340, 359, [('Feed speed  ', W), ('4 steps', GR)], s=18, w=700, mx=180),
      seg(340, 460, [('Press force  ', W), ('4 steps', GR)], s=18, w=700, mx=180),
      cap(125, 458, ['Depth camera, 9 views', 'point cloud registration'], 28, 165, s=14),
      seg(250, 588, [('3 x 4 x 4 = ', W), ('48', GR), (' environments', W)],
          s=26, w=700, mx=400),
      # ② ─────────────────────────────────────────────
      title(669, 165, 'Policy training', 270, s=26),
      cap(705, 205, ['Maximise reward across the 48 environments'], 26, 400, s=19),
      lbl(710, 245, 'Action a', s=18),
      lbl(596, 285, 'Policy',   s=18),
      lbl(822, 286, 'PolyTwin env', s=18, mx=115),
      lbl(822, 316, '48 types', s=17),
      lbl(709, 378, 'state s / reward r', s=17, mx=150),
      lbl(708, 422, 'Reward function', s=18, w=700, mx=160),
      seg(708, 452, [('R', GR), (' = contact force + roughness target - cycle time', T)],
          s=15, mx=390),
      cap(708, 602, ['Validation error falls as training runs'], 26, 380, s=19),
      # ③ ─────────────────────────────────────────────
      title(1113, 165, 'Expert review', 260, s=26),
      cap(1165, 206, ['A veteran scores the polishing result'], 26, 380, s=19),
      lbl(1250, 294, 'Path fit',   s=16, a='l', mx=100),
      lbl(1250, 331, 'Uniformity', s=16, a='l', mx=100),
      lbl(1250, 369, 'Stability',  s=16, a='l', mx=100),
      lbl(1250, 407, 'Quality',    s=16, a='l', mx=100),
      lbl(1184, 484, 'Could we raise the contact force?', s=17, c=(248, 253, 255), mx=270),
      cap(1216, 560, ['Raising the', 'press force.'], 27, 82, s=15, c=(248, 253, 255)),
      # ④ ─────────────────────────────────────────────
      title(1584, 165, 'Asset registry', 200, s=26),
      cap(1600, 206, ['Only policies that pass become assets'], 26, 330, s=19),
      lbl(1470, 249, 'Combo',        s=17, a='l', mx=80),
      lbl(1595, 249, 'Expert score', s=17, mx=110),
      lbl(1694, 249, 'Verdict',      s=17, a='l', mx=80),
      lbl(1701, 287, 'Kept',    s=15, c=RG, a='l', mx=80),
      lbl(1701, 325, 'Kept',    s=15, c=RG, a='l', mx=80),
      lbl(1701, 363, 'Dropped', s=15, c=RR, a='l', mx=80),
      lbl(1701, 401, 'Kept',    s=15, c=RG, a='l', mx=80),
      lbl(1701, 439, 'Kept',    s=15, c=RG, a='l', mx=80),
      title(1596, 538, 'Per-process policy DB', 290, s=23, a='c'),
      cap(1596, 575, ['Reusable digital assets'], 26, 290, s=21),
      # 하단 ─────────────────────────────────────────
      seg(782, 723, [('Expert feedback -> ', T),
                     ('tune parameters, redesign reward', GR),
                     (' -> retrain to close the gap', T)], s=17, mx=790),
    ]),

  # ── 결과 분석 ── 1,800 rpm · 30 N · 숫자·2:31 은 원래 영문이라 그대로 둔다 ──
  'wide_result': dict(
    src='wide_result.webp', out='wide_result.en.webp', th=120, grow=3,
    erase=[
      # 범례: 칩은 204..227 에서 끝나고 흰 글자는 241 에서 시작한다.
      # 밝기 띠로 재면 주황 칩이 글자로 잡힌다 — 무채색 흰 픽셀로 다시 쟀다.
      (87, 533, 126, 563), (237, 533, 276, 563), (387, 533, 443, 563),
      (1729, 243, 1765, 266),
      (875, 329, 1013, 356),
      (853, 430, 961, 453), (996, 431, 1114, 453), (1164, 431, 1238, 453),
      (856, 541, 957, 563), (1010, 541, 1101, 564), (1169, 541, 1233, 563),
      (1351, 329, 1478, 356),
      (1326, 380, 1364, 403), (1554, 379, 1618, 403),
      (1326, 417, 1404, 440), (1326, 454, 1363, 477), (1326, 491, 1404, 514),
      (1326, 527, 1381, 551), (1326, 564, 1364, 587),
      (1554, 490, 1639, 514), (1555, 527, 1657, 551), (1555, 563, 1591, 587),
    ],
    text=[
      lbl(91, 548, 'Reached', s=17, c=SV, a='l', mx=105),
      lbl(241, 548, 'Partial', s=17, c=SV, a='l', mx=105),
      lbl(391, 548, 'Missed',  s=17, c=SV, a='l', mx=105),
      lbl(1732, 254, 'Low', s=17, c=SV, a='l', mx=55),
      # ③ 예상 공정 시간
      title(878, 342, 'Estimated cycle time', 380, s=23),
      lbl(907, 441,  'Total cycle (min)', s=15, c=SL, mx=132),
      lbl(1055, 441, 'Robot work (min)',  s=15, c=SL, mx=138),
      lbl(1201, 441, 'Reach rate (%)',    s=15, c=SL, mx=130),
      lbl(906, 552,  'Estimated start',   s=15, c=SL, mx=132),
      lbl(1055, 552, 'Coverage (%)',      s=15, c=SL, mx=138),
      lbl(1201, 552, 'Mean CPI',          s=15, c=SL, mx=130),
      # ④ 권장 파라미터
      title(1354, 342, 'Recommended parameters', 420, s=23),
      lbl(1329, 391, 'Item',        s=18, c=SL, a='l', mx=200),
      lbl(1557, 391, 'Recommended', s=18, c=SL, a='l', mx=200),
      lbl(1329, 428, 'Spindle speed', s=20, c=SV, a='l', mx=200),
      lbl(1329, 465, 'Pressure',      s=20, c=SV, a='l', mx=200),
      lbl(1329, 502, 'Pad type',      s=20, c=SV, a='l', mx=200),
      lbl(1329, 538, 'Abrasive',      s=20, c=SV, a='l', mx=200),
      lbl(1329, 575, 'Passes',        s=20, c=SV, a='l', mx=200),
      lbl(1558, 501, 'Medium foam', s=21, c=SV, a='l', mx=200),
      lbl(1558, 538, 'Compound A', s=21, c=SV, a='l', mx=200),
      lbl(1558, 574, '3',           s=21, c=SV, a='l', mx=200),
    ]),

  # ── 전체 구성 ── Web UI 와 가상 작업장. 이 그림이 글줄이 제일 많다.
  #    20.0 · 150 mm · 19% · 04:12 · ROS 2 · Isaac Sim · Y(m) 은 원문이 영문이다 ──
  'wide_system': dict(
    src='wide_system.webp', out='wide_system.en.webp', th=120, grow=3,
    erase=[
      # ── 왼쪽: 작업자 화면 ──
      (102, 20, 332, 53), (103, 53, 371, 76), (77, 98, 207, 124),
      (240, 121, 282, 141), (232, 150, 281, 167), (232, 178, 281, 195),
      (232, 206, 314, 222), (232, 228, 304, 245), (232, 250, 325, 267),
      (231, 275, 315, 292), (232, 300, 314, 317), (232, 326, 284, 343),
      (300, 121, 332, 141), (300, 150, 368, 167), (300, 178, 456, 195),
      (342, 326, 394, 343),
      (35, 287, 190, 306), (35, 309, 226, 327), (35, 330, 184, 349),
      (77, 395, 223, 421), (84, 478, 158, 497),
      (308, 426, 360, 443), (309, 453, 373, 470), (308, 479, 376, 497),
      (34, 517, 80, 537), (221, 517, 288, 537), (389, 520, 455, 537),
      (79, 611, 235, 637), (293, 634, 360, 651), (381, 655, 437, 678),
      (294, 683, 376, 700), (350, 653, 380, 680),
      (295, 703, 467, 722), (295, 721, 458, 739),
      (295, 742, 453, 759), (295, 762, 426, 779),
      (38, 798, 152, 824), (313, 796, 400, 822),
      # ── 오른쪽: 가상 작업장 ──
      (638, 22, 982, 55), (1361, 22, 1618, 55),
      (632, 96, 762, 128), (996, 96, 1082, 128), (1372, 96, 1488, 128),
      (739, 343, 873, 382), (1386, 343, 1584, 382),
      (900, 414, 1108, 436), (900, 441, 1069, 463), (1230, 418, 1276, 444),
      (639, 611, 839, 638), (1009, 611, 1189, 638),
      (1358, 617, 1486, 639), (1358, 642, 1558, 664),
      (1358, 723, 1509, 745), (1358, 748, 1433, 770),
      (710, 863, 1381, 888),
    ],
    text=[
      # ── 왼쪽 ──
      title(102, 37, 'Operator screen / Web UI', 400, s=24),
      cap(103, 64, ['Change the values and run again'], 24, 400, s=20, c=SY, a='l'),
      title(80, 111, 'Set work conditions', 420, s=23),
      # 드롭다운 라벨은 오른쪽 정렬(279), 슬라이더 라벨은 왼쪽(232)
      lbl(279, 131, 'Model',     s=13, c=SY, a='r', mx=95),
      lbl(279, 158, 'Mode',      s=13, c=SY, a='r', mx=95),
      lbl(279, 186, 'Area',      s=13, c=SY, a='r', mx=95),
      lbl(279, 334, 'Objective', s=13, c=SY, a='r', mx=95),
      lbl(232, 214, 'Path: parallel',      s=13, c=SY, a='l', mx=120),
      lbl(232, 236, 'Normal load (N)',     s=13, c=SY, a='l', mx=125),
      lbl(232, 258, 'Polish speed (mm/s)', s=13, c=SY, a='l', mx=125),
      lbl(232, 283, 'Pad dia. (mm)',       s=13, c=SY, a='l', mx=125),
      lbl(232, 308, 'Work area (mm)',      s=13, c=SY, a='l', mx=125),
      lbl(300, 131, 'Sedan A',             s=11, c=SY, a='l', mx=170),
      lbl(300, 158, 'Auto path generation', s=11, c=SY, a='l', mx=170),
      lbl(300, 186, 'Whole car (hood, roof, sides, trunk)', s=11, c=SY, a='l', mx=195),
      lbl(342, 334, 'Global optimum',      s=11, c=SY, a='l', mx=130),
      cap(35, 317, ['The user sets polishing',
                    'parameters - path mode, force,',
                    'robot count, area, objective.'], 21, 192, s=14, c=SY, a='l'),
      title(80, 408, 'Live monitoring', 420, s=23),
      lbl(120, 487, 'Progress now', s=16, c=SY, mx=140),
      lbl(308, 434, 'Normal deviation', s=14, c=SY2, a='l', mx=140),
      lbl(308, 461, 'Path fulfilment',  s=14, c=SY2, a='l', mx=140),
      lbl(308, 487, 'Work efficiency',  s=14, c=SY2, a='l', mx=140),
      lbl(34, 526,  'Normal force',  s=13, c=SY, a='l', mx=105),
      lbl(221, 526, 'Lateral force', s=13, c=SY, a='l', mx=92),
      lbl(389, 526, 'Multi force',   s=13, c=SY, a='l', mx=64),
      title(82, 623, 'Result report', 420, s=23),
      lbl(293, 642, 'All points',       s=14, c=SY2, a='l', mx=150),
      lbl(353, 666, 'done',             s=13, c=SY,  a='l', mx=30),
      lbl(294, 691, 'Main issue areas', s=14, c=SY2, a='l', mx=150),
      cap(295, 740, ['Hood centre deviation (12.4%)',
                     '- Left front area deviation (16.2%)',
                     '- Trunk top (height gap 8.6%)',
                     '- Trunk lid (error 4%)'], 20, 222, s=14, c=SY2, a='l'),
      lbl(38, 810,  'Final result (summary)', s=15, c=SY, a='l', mx=190),
      lbl(316, 808, 'Cycle time',            s=15, c=SY, a='l', mx=110),
      # ── 오른쪽 ──
      title(638, 38, 'Virtual work cell / NVIDIA Isaac Sim', 690, s=24),
      cap(1361, 38, ['Reproduced under real physics'], 24, 300, s=21, c=SY, a='l'),
      title(636, 111, 'Body shape scan', 290, s=23),
      title(1000, 111, 'Path generation', 285, s=23),
      title(1376, 111, 'Force-controlled polish', 268, s=23),
      title(743, 361, 'Veteran inspection', 430, s=23),
      title(1390, 361, 'Save result (kept)', 245, s=23),
      title(643, 623, 'Re-polish (tuning loop)', 262, s=23),
      title(1013, 623, 'Error trace-back and fix', 280, s=23),
      cap(900, 438, ['This spot needs a bit more force',
                     'and several more passes.'], 27, 213, s=16, c=SY, a='l'),
      lbl(1252, 430, 'Similar', s=22, c=SYG, w=700, mx=110),
      cap(1358, 640, ['Commands and readings',
                      'over a real-time network'], 25, 280, s=17, c=SY, a='l'),
      cap(1358, 746, ['A virtual environment',
                      'with a physics engine'], 25, 280, s=17, c=SY, a='l'),
      seg(1044, 875, [('Expert feedback -> ', SY),
                      ('tune parameters -> redesign reward', GR),
                      (' -> retrain to close the gap', SY)], s=16, mx=670),
    ]),

  # ── 팀 사진 말풍선 ── 흰 바탕에 검은 글씨라 th 를 음수로 준다.
  #    이름은 국립국어원 로마자 표기를 따른다 ──
  'pdf_20': dict(
    src='pdf_20_1746x1361.jpg', out='pdf_20_1746x1361.en.jpg', th=-140, grow=4, q=82,
    erase=[
      (58, 107, 846, 170),
      (1077, 117, 1663, 180),
      (517, 711, 1270, 781), (517, 782, 1009, 845),
      (90, 938, 1176, 1002),
    ],
    text=[
      lbl(64, 138, "Jeong Yong-jun: All-in to the end!", s=44, c=BK, a='l', mx=820),
      lbl(1083, 148, 'Shin Hyeon-ho: Dreams come true!!', s=44, c=BK, a='l', mx=590),
      cap(523, 779, ['Bu Seung-eon: Good people, good',
                     'experience - enjoying it to the end.'], 68, 750, s=44, c=BK, a='l'),
      lbl(96, 969, "Kim Du-yong: Someday I'll try this on a real arm.",
          s=44, c=BK, a='l', mx=1075),
    ]),
}
