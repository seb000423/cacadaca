
/* ══════════════════════════════════════════════════════════════
   구간 선택 도구. sub.html 은 미디어 프래그먼트(#t=start,end)로
   구간을 재생하므로, 여기서 고른 초 값을 그대로 쓰면 된다.
   ══════════════════════════════════════════════════════════════ */

const VIDEOS = [
  ['assets/video/polishing.webm', '폴리싱 — sub.html?p=polishing'],
  ['assets/video/pick-place.mp4', '이송 — sub.html?p=pickplace'],
  ['assets/video/hero.mp4',       '히어로 — index.html'],
];

const $ = (id) => document.getElementById(id);
const v = $('v');
const fmt = (t) => (t == null || !isFinite(t)) ? '—' : t.toFixed(1) + 's';

let IN = null, OUT = null;

/* ── 소스 선택 ───────────────────────────────── */
VIDEOS.forEach(([url, label], i) => {
  const o = document.createElement('option');
  o.value = url; o.textContent = label;
  $('src').appendChild(o);
});
function load(url) {
  IN = OUT = null;
  $('sheet').textContent = '';
  v.src = url;
  paint();
}
$('src').addEventListener('change', (e) => load(e.target.value));

/* ── 메타데이터 ──────────────────────────────── */
v.addEventListener('loadedmetadata', () => {
  $('k-dur').textContent = fmt(v.duration);
  $('k-res').textContent = v.videoWidth + '×' + v.videoHeight;
  $('track').setAttribute('aria-valuemax', v.duration.toFixed(1));
  paint();
});

/* ── 시간 표시 · 구간 반복 ───────────────────── */
v.addEventListener('timeupdate', () => {
  /* 값은 즉시 갱신한다. 이징을 넣으면 현재값을 읽을 수 없다 */
  $('clock').innerHTML = v.currentTime.toFixed(1) + '<small>s</small> / ' +
                         (v.duration || 0).toFixed(1) + '<small>s</small>';
  $('head').style.left = pct(v.currentTime) + '%';
  $('track').setAttribute('aria-valuenow', v.currentTime.toFixed(1));

  if ($('loop').dataset.on === '1' && IN != null && OUT != null) {
    if (v.currentTime >= OUT || v.currentTime < IN - 0.05) v.currentTime = IN;
  }
});

const pct = (t) => v.duration ? (t / v.duration) * 100 : 0;

/* ── 트랙 스크럽 ─────────────────────────────── */
$('track').addEventListener('click', (e) => {
  if (!v.duration) return;
  const r = e.currentTarget.getBoundingClientRect();
  v.currentTime = ((e.clientX - r.left) / r.width) * v.duration;
});
$('track').addEventListener('keydown', (e) => {
  const step = e.shiftKey ? 5 : 1;
  if (e.key === 'ArrowRight') { v.currentTime = Math.min(v.duration, v.currentTime + step); e.preventDefault(); }
  if (e.key === 'ArrowLeft')  { v.currentTime = Math.max(0, v.currentTime - step);          e.preventDefault(); }
});

/* ── IN / OUT ───────────────────────────────── */
$('mark-in').addEventListener('click', () => {
  IN = round(v.currentTime);
  if (OUT != null && OUT <= IN) OUT = null;
  paint();
});
$('mark-out').addEventListener('click', () => {
  OUT = round(v.currentTime);
  if (IN != null && IN >= OUT) IN = null;
  paint();
});
const round = (t) => Math.round(t * 10) / 10;

$('loop').addEventListener('click', (e) => {
  const on = e.currentTarget.dataset.on === '1' ? '0' : '1';
  e.currentTarget.dataset.on = on;
  e.currentTarget.setAttribute('aria-pressed', on === '1');
  if (on === '1' && IN != null) v.currentTime = IN;
});

function paint() {
  $('k-in').textContent  = fmt(IN);
  $('k-out').textContent = fmt(OUT);
  $('k-len').textContent = (IN != null && OUT != null) ? fmt(OUT - IN) : '—';

  const s = $('sel');
  if (IN != null && OUT != null) {
    s.style.left  = pct(IN) + '%';
    s.style.width = (pct(OUT) - pct(IN)) + '%';
  } else {
    s.style.width = '0';
  }

  const file = (v.currentSrc || v.src || '').split('/').pop().split('#')[0];
  $('out').textContent = (IN != null && OUT != null)
    ? `video: VID('${file}', '가상 작업장 폴리싱 실행', { start: ${IN}, end: ${OUT} }),`
    : '구간을 지정하면 여기 나온다';

  document.querySelectorAll('.thumb').forEach((t) => {
    const at = parseFloat(t.dataset.t);
    t.dataset.in = (IN != null && OUT != null && at >= IN && at <= OUT) ? '1' : '0';
  });
}

$('copy').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText($('out').textContent);
    $('msg').textContent = '복사했다.';
  } catch (err) {
    $('msg').textContent = '복사 실패 — 직접 긁어라. ' + err.message;
  }
});

/* ── 컨택트 시트 ────────────────────────────────
   숨긴 비디오를 한 지점씩 seek 해 캔버스로 굽는다.
   동시에 여러 지점을 요청하면 seek 이 서로를 덮어쓴다 — 순차로 돈다. */
$('shoot').addEventListener('click', shoot);

async function shoot() {
  if (!v.duration) { $('msg').textContent = '영상 길이를 아직 못 읽었다.'; return; }
  const btn = $('shoot');
  btn.disabled = true;
  $('msg').textContent = '';
  $('sheet').textContent = '';

  /* 3분짜리 기준 약 8초 간격. 짧은 영상은 촘촘하게 */
  const N = Math.min(36, Math.max(8, Math.round(v.duration / 8)));
  const step = v.duration / N;

  const probe = document.createElement('video');
  probe.src = v.currentSrc || v.src;
  probe.muted = true; probe.preload = 'auto'; probe.crossOrigin = 'anonymous';
  await once(probe, 'loadedmetadata');

  const cv = document.createElement('canvas');
  const scale = 240 / probe.videoWidth;
  cv.width = 240;
  cv.height = Math.round(probe.videoHeight * scale);
  const cx = cv.getContext('2d');

  for (let i = 0; i < N; i++) {
    const t = Math.min(v.duration - 0.05, i * step + step / 2);
    probe.currentTime = t;
    try { await once(probe, 'seeked', 4000); } catch (e) { continue; }
    cx.drawImage(probe, 0, 0, cv.width, cv.height);

    let url;
    try {
      url = cv.toDataURL('image/jpeg', 0.72);
    } catch (e) {
      $('msg').textContent = '캔버스가 오염됐다 — file:// 이 아니라 http 서버로 열어라.';
      break;
    }
    addThumb(url, t);
    btn.textContent = `컨택트 시트 ${i + 1}/${N}`;
  }

  btn.textContent = '컨택트 시트';
  btn.disabled = false;
  paint();
}

function addThumb(url, t) {
  const b = document.createElement('button');
  b.className = 'thumb';
  b.dataset.t = t;
  b.type = 'button';
  b.innerHTML = `<img src="${url}" alt="${t.toFixed(1)}초 지점"><figcaption>${t.toFixed(1)}s</figcaption>`;
  b.addEventListener('click', () => { v.currentTime = t; });
  $('sheet').appendChild(b);
}

function once(el, ev, ms = 8000) {
  return new Promise((res, rej) => {
    const id = setTimeout(() => { el.removeEventListener(ev, on); rej(new Error('timeout')); }, ms);
    const on = () => { clearTimeout(id); el.removeEventListener(ev, on); res(); };
    el.addEventListener(ev, on);
  });
}

load(VIDEOS[0][0]);
