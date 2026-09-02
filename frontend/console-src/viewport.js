const THREE = await import(window.__resources.three);

// Offline build: three.js and its addons are inlined by the bundler and handed
// to us as blob URLs, so the module graph is rewired against those.
const ADDONS = {
  'loaders/GLTFLoader.js': 'gltfLoader',
  'controls/OrbitControls.js': 'orbitControls',
  'utils/BufferGeometryUtils.js': 'bufferGeometryUtils',
};
const __modCache = new Map();
async function __resolveAddon(path) {
  if (__modCache.has(path)) return __modCache.get(path);
  const p = (async () => {
    const key = ADDONS[path];
    if (!key) throw new Error('addon not bundled: ' + path);
    let src = await (await fetch(window.__resources[key])).text();
    src = src.replace(/(from\s*|import\s*)(['"])([^'"]+)\2/g, (m, kw, q, spec) => {
      if (spec === 'three') return kw + q + window.__resources.three + q;
      const hit = Object.keys(ADDONS).find((k) => spec.endsWith(k.split('/').pop()));
      return hit ? kw + q + '@@' + hit + '@@' + q : m;
    });
    for (const dep of Object.keys(ADDONS)) {
      if (src.includes('@@' + dep + '@@')) src = src.split('@@' + dep + '@@').join(await __resolveAddon(dep));
    }
    return URL.createObjectURL(new Blob([src], { type: 'text/javascript' }));
  })();
  __modCache.set(path, p);
  return p;
}
const loadAddon = async (path) => import(await __resolveAddon(path));

const ACCENT = 0x3e9dbe;   // DESIGN.md --accent. 구 #4FC3F7 에서 채도 -22%

/* 무광 → 유광. 패드가 지나간 자리를 하이트필드 좌표계의 마스크에 찍고,
   차체 셰이더에서 roughness 를 보간한다. PolyTwin 의 가치 제안 그 자체다. */
const ROUGH_MATTE = 0.82, ROUGH_GLOSS = 0.14;
/* 기본값을 null 로 두면 안 된다. 경로선 재질은 모델이 로드되기 전에 이미
   렌더되는데, 그때 initPolish 가 아직 안 돌아 three.js 가 null 을 Vector3 로
   업로드하려다 터진다. uPolishOn 이 0 이라 값 자체는 쓰이지 않는다. */
const polishU = {
  /* 광택 마스크 3장 — 면의 법선이 향하는 축으로 고른다(트라이플래너). 위에서 본 XZ(윗면), 옆에서 본 (길이, 높이)(옆면),
     앞뒤에서 본 (폭, 높이)(앞뒤면). 한 장짜리 위 투영은 옆면·앞뒤면에 엉뚱한 광택을 만들었다. */
  uPolishTop: { value: null }, uPolishSide: { value: null }, uPolishEnd: { value: null },
  uLongSel: { value: new THREE.Vector3(0, 0, 1) },   // 월드 좌표에서 long 축을 뽑는 선택자
  uCrossSel: { value: new THREE.Vector3(1, 0, 0) },
  uTopMin: { value: new THREE.Vector2(0, 0) }, uTopSpan: { value: new THREE.Vector2(1, 1) },      // (long, cross)
  uSideMin: { value: new THREE.Vector2(0, 0) }, uSideSpan: { value: new THREE.Vector2(1, 1) },    // (long, y)
  uEndMin: { value: new THREE.Vector2(0, 0) }, uEndSpan: { value: new THREE.Vector2(1, 1) },      // (cross, y)
  uPolishOn: { value: 0 },
};

function attachPolish(mat) {
  mat.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, polishU);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vPolishPos;\nvarying vec3 vPolishN;')
      .replace('#include <worldpos_vertex>',
        '#include <worldpos_vertex>\n  vPolishPos = (modelMatrix * vec4(transformed, 1.0)).xyz;\n  vPolishN = normalize(mat3(modelMatrix) * objectNormal);');
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', [
        '#include <common>',
        'varying vec3 vPolishPos;',
        'varying vec3 vPolishN;',
        'uniform sampler2D uPolishTop;',
        'uniform sampler2D uPolishSide;',
        'uniform sampler2D uPolishEnd;',
        'uniform vec3 uLongSel;',
        'uniform vec3 uCrossSel;',
        'uniform vec2 uTopMin; uniform vec2 uTopSpan;',
        'uniform vec2 uSideMin; uniform vec2 uSideSpan;',
        'uniform vec2 uEndMin; uniform vec2 uEndSpan;',
        'uniform float uPolishOn;',
        'float polishLookup(sampler2D t, vec2 uv) { return (uv.x > 0.0 && uv.x < 1.0 && uv.y > 0.0 && uv.y < 1.0) ? texture2D(t, uv).r : 0.0; }',
      ].join('\n'))
      .replace('#include <roughnessmap_fragment>', [
        '#include <roughnessmap_fragment>',
        'float polished = 0.0;',
        'if (uPolishOn > 0.5) {',
        '  vec3 pn = normalize(vPolishN);',
        '  float ay = abs(pn.y), ax = abs(dot(pn, uCrossSel)), az = abs(dot(pn, uLongSel));',
        '  float L = dot(vPolishPos, uLongSel), C = dot(vPolishPos, uCrossSel), Y = vPolishPos.y;',
        '  if (ay >= ax && ay >= az) polished = polishLookup(uPolishTop, (vec2(L, C) - uTopMin) / uTopSpan);',
        '  else if (ax >= az)        polished = polishLookup(uPolishSide, (vec2(L, Y) - uSideMin) / uSideSpan);',
        '  else                      polished = polishLookup(uPolishEnd, (vec2(C, Y) - uEndMin) / uEndSpan);',
        '  roughnessFactor = mix(0.82, 0.14, polished);',
        '  diffuseColor.rgb *= mix(1.0, 1.45, polished);',   // 닦인 곳은 눈에 띄게 밝아진다
        '}',
      ].join('\n'))
      // 광택은 클리어코트가 만든다. 여기까지 같이 보간해야 무광->유광이 읽힌다.
      .replace('#include <lights_physical_fragment>', [
        '#include <lights_physical_fragment>',
        '#ifdef USE_CLEARCOAT',
        'if (uPolishOn > 0.5) {',
        '  material.clearcoatRoughness = mix(0.42, 0.03, polished);',
        '}',
        '#endif',
      ].join('\n'));
  };
  mat.needsUpdate = true;
  return mat;
}

/* 경로선도 같은 마스크를 본다. 계획선이 차체를 끝까지 덮고 있으면
   무광->유광이 아무리 잘 돌아도 화면에는 '줄무늬 덮인 차'만 보인다.
   지나간 자리의 선을 걷어야 닦인 도장이 드러난다. */
function attachPathFade(mat) {
  mat.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, polishU);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vPolishPos;')
      .replace('#include <begin_vertex>',
        '#include <begin_vertex>\n  vPolishPos = (modelMatrix * vec4(position, 1.0)).xyz;');
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', [
        '#include <common>',
        'varying vec3 vPolishPos;',
        'uniform sampler2D uPolishTop;',
        'uniform vec3 uLongSel;',
        'uniform vec3 uCrossSel;',
        'uniform vec2 uTopMin;',
        'uniform vec2 uTopSpan;',
        'uniform float uPolishOn;',
      ].join('\n'))
      .replace('#include <opaque_fragment>', [
        '  if (uPolishOn > 0.5) {',
        '    vec2 pUv = vec2(',
        '      (dot(vPolishPos, uLongSel) - uTopMin.x) / uTopSpan.x,',
        '      (dot(vPolishPos, uCrossSel) - uTopMin.y) / uTopSpan.y);',
        '    if (pUv.x > 0.0 && pUv.x < 1.0 && pUv.y > 0.0 && pUv.y < 1.0) {',
        // 완전히 지우지 않는다. 옅게 남겨야 '어디를 지났는지'가 읽힌다
        '      diffuseColor.a *= 1.0 - 0.88 * texture2D(uPolishTop, pUv).r;',
        '    }',
        '  }',
        '#include <opaque_fragment>',
      ].join('\n'));
  };
  mat.needsUpdate = true;
  return mat;
}

const SKIP = /environment|backdrop|^cube$|^plane$|floor|ground/i;
const CAR_LENGTH = 4.35;
// 경로선을 도장면에서 띄우는 양(m). 선이 도장면과 z-fighting 하지 않게 하려는 것이고,
// 패드는 이 값을 되빼서 도장면 자체를 짚는다.
const PATH_LIFT = 0.013;
const DEMO_SPEEDUP = 26;   // 이송속도 배속 — 실시간이면 한 패스가 2분을 넘는다
const ARM_HEIGHT = 0.86;   // m — an M0609 stands ~0.74 m folded, plus the wrist tool
const PEDESTAL = 0.72;     // m — the pillar each cell is bolted to

async function loadCar(url) {
  const { GLTFLoader } = await loadAddon('loaders/GLTFLoader.js');
  // 차체도 meshopt 로 구운 GLB 다(4.2MB -> 264KB). 디코더 없이는 로더가 거부한다.
  const { MeshoptDecoder } = await import(MESHOPT_URL);
  const gltf = await new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).loadAsync(url);
  const root = gltf.scene;
  root.updateMatrixWorld(true);

  const geos = [], mats = [];
  root.traverse((o) => {
    if (!o.isMesh) return;
    for (let p = o; p; p = p.parent) if (p.name && SKIP.test(p.name)) return;
    // 양자화된 정수 배열에 변환 결과를 도로 써 넣으면 형상이 뭉개진다.
    // dequantize 로 float 으로 풀고 나서 행렬을 먹인다.
    const g = dequantize(o.geometry.clone());
    g.applyMatrix4(o.matrixWorld);
    geos.push(g); mats.push(o.material);
  });
  if (!geos.length) throw new Error('no mesh in car model');

  const bbox = () => {
    const b = new THREE.Box3();
    geos.forEach((g) => { g.computeBoundingBox(); b.union(g.boundingBox); });
    return b;
  };
  const bake = (m) => geos.forEach((g) => g.applyMatrix4(m));
  let b = bbox(), sz = b.getSize(new THREE.Vector3());
  if (sz.x > sz.z) { bake(new THREE.Matrix4().makeRotationY(Math.PI / 2)); b = bbox(); sz = b.getSize(new THREE.Vector3()); }
  bake(new THREE.Matrix4().makeScale(...Array(3).fill(CAR_LENGTH / sz.z)));
  b = bbox();
  const c = b.getCenter(new THREE.Vector3());
  bake(new THREE.Matrix4().makeTranslation(-c.x, -b.min.y, -c.z));

  const group = new THREE.Group();
  const paintPts = [];      // 도장 면 정점(로컬) — 레인은 이 정점 근처에만 내고, 광택도 도장 재질에만
  geos.forEach((g, i) => {
    if (!g.attributes.normal) g.computeVertexNormals();
    const src = mats[i];
    const name = (src && src.name) || '';
    const lum = src && src.color ? 0.2126 * src.color.r + 0.7152 * src.color.g + 0.0722 * src.color.b : 0;
    /* 도장 판정: 재질 이름에 paint 가 있으면 도장. 이름이 없는(단일 재질) 모델은 밝은 큰 면을 도장으로 본다.
       유리·휠·그릴·트림은 도장이 아니므로 광택 셰이더를 붙이지 않는다 → 절대 닦이지 않는다. */
    const isPaint = /paint|body|carpaint|lack/i.test(name) || (!name && lum > 0.5) || (mats.length === 1);
    const base = new THREE.MeshPhysicalMaterial({
      color: lum > 0.5 ? 0x2f343b : (src && src.color ? src.color.getHex() : 0x22262c),
      metalness: 0.35, roughness: isPaint ? ROUGH_MATTE : 0.5,
      clearcoat: isPaint ? 1 : 0.3, clearcoatRoughness: 0.28, envMapIntensity: 1.4,
    });
    const mat = isPaint ? attachPolish(base) : base;
    const m = new THREE.Mesh(g, mat);
    m.userData.paint = isPaint;
    m.castShadow = true; m.receiveShadow = true;
    group.add(m);
    if (isPaint) {
      /* 도장 면을 정점이 아니라 삼각형 면 위 표본(≈5 cm 간격)으로 담는다 — 거친 메시는 큰 패널 한가운데에 정점이 없어
         정점만 쓰면 보닛·루프·도어 중앙 레인이 통째로 빠진다 */
      const a = g.attributes.position, idx = g.index;
      const nTri = idx ? idx.count / 3 : a.count / 3;
      const A = new THREE.Vector3(), B = new THREE.Vector3(), C = new THREE.Vector3();
      const STEP = 0.05;
      for (let tI = 0; tI < nTri; tI++) {
        const i0 = idx ? idx.getX(tI * 3) : tI * 3, i1 = idx ? idx.getX(tI * 3 + 1) : tI * 3 + 1, i2 = idx ? idx.getX(tI * 3 + 2) : tI * 3 + 2;
        A.set(a.getX(i0), a.getY(i0), a.getZ(i0)); B.set(a.getX(i1), a.getY(i1), a.getZ(i1)); C.set(a.getX(i2), a.getY(i2), a.getZ(i2));
        const n = Math.max(1, Math.ceil(Math.max(A.distanceTo(B), B.distanceTo(C), C.distanceTo(A)) / STEP));
        for (let u = 0; u <= n; u++) for (let v = 0; u + v <= n; v++) {
          const w0 = u / n, w1 = v / n, w2 = 1 - w0 - w1;
          paintPts.push(new THREE.Vector3(A.x * w0 + B.x * w1 + C.x * w2, A.y * w0 + B.y * w1 + C.y * w2, A.z * w0 + B.z * w1 + C.z * w2));
        }
        if (paintPts.length > 400000) break;
      }
    }
  });
  group.userData.size = bbox().getSize(new THREE.Vector3());
  group.userData.paintPts = paintPts;
  return group;
}

/* ══ 표면 필드 ══════════════════════════════════════════════════
   차체는 삼각형이 20만 개인데 가속 구조가 없다. CPU 로 격자를 쏘면
   메인 스레드가 멈춘다. GPU 로 굽는다 — 직교 카메라 한 장으로 표면의
   '깊이축 좌표'를 써 내고 한 번 읽어 온다.

   축은 세 개로 말한다.
     u  레인이 달리는 축      (차체 길이)
     v  레인 사이를 옮기는 축  (위에서 보면 폭, 옆에서 보면 높이)
     d  깊이축                (위에서 보면 Y, 옆에서 보면 폭)
   dir 은 카메라가 서 있는 쪽. +1 이면 d 가 큰 쪽에서 들여다본다.

   위에서 찍은 필드 하나로는 문짝을 낼 수 없다. 한 칸에 값이 하나뿐이라
   수직면을 담을 수 없기 때문이다. 그래서 옆에서도 두 장 굽는다. */

const AX = { x: new THREE.Vector3(1, 0, 0), y: new THREE.Vector3(0, 1, 0), z: new THREE.Vector3(0, 0, 1) };

function buildField(renderer, model, spec) {
  const { u, v, d, dir, nU, nV, u0, u1, v0, v1, keep, skip } = spec;
  const eu = AX[u], ev = AX[v], ed = AX[d];

  const target = new THREE.WebGLRenderTarget(nU, nV, {
    type: THREE.FloatType, format: THREE.RGBAFormat,
    minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, depthBuffer: true,
  });

  const mat = new THREE.ShaderMaterial({
    uniforms: { uSel: { value: ed.clone() } },
    vertexShader: `uniform vec3 uSel; varying float vD;
      void main() {
        vec4 wp = modelMatrix * vec4(position, 1.0);
        vD = dot(wp.xyz, uSel);
        gl_Position = projectionMatrix * viewMatrix * wp;
      }`,
    fragmentShader: `varying float vD;
      void main() { gl_FragColor = vec4(vD, 1.0, 0.0, 1.0); }`,
    side: THREE.DoubleSide,
  });

  const b = new THREE.Box3().setFromObject(model);
  const size = b.getSize(new THREE.Vector3());
  const back = size[d] + 4;

  const cam = new THREE.OrthographicCamera(
    (u0 - u1) / 2, (u1 - u0) / 2, (v1 - v0) / 2, (v0 - v1) / 2, 0.01, back
  );
  const mid = new THREE.Vector3();
  mid[u] = (u0 + u1) / 2;
  mid[v] = (v0 + v1) / 2;
  mid[d] = dir > 0 ? b.max[d] + 2 : b.min[d] - 2;
  cam.up.copy(ev);
  cam.position.copy(mid);
  const look = mid.clone();
  look[d] -= dir * 3;
  cam.lookAt(look);
  cam.updateMatrixWorld(true);

  /* 판독 방향은 추측하지 않는다. lookAt 이 만든 카메라 축을 직접 읽어
     u·v 가 뒤집혔는지 본다. 예전 코드는 이걸 손으로 계산하다 틀려
     후드 위에 루프 높이가 얹혔다. */
  const camX = new THREE.Vector3().setFromMatrixColumn(cam.matrixWorld, 0);
  const camY = new THREE.Vector3().setFromMatrixColumn(cam.matrixWorld, 1);
  const flipU = camX.dot(eu) < 0;
  const flipV = camY.dot(ev) < 0;

  const scene = new THREE.Scene();
  const proxy = new THREE.Group();
  model.updateMatrixWorld(true);
  model.traverse((o) => {
    if (!o.isMesh) return;
    if (skip) { for (let p = o; p; p = p.parent) if (p.name && skip.test(p.name)) return; }
    const m = new THREE.Mesh(o.geometry, mat);
    m.matrixAutoUpdate = false;
    m.matrix.copy(o.matrixWorld);
    proxy.add(m);
  });
  scene.add(proxy);

  const prevTarget = renderer.getRenderTarget();
  renderer.setRenderTarget(target);
  renderer.setClearColor(0x000000, 0);
  renderer.clear();
  renderer.render(scene, cam);
  const buf = new Float32Array(nU * nV * 4);
  renderer.readRenderTargetPixels(target, 0, 0, nU, nV, buf);
  renderer.setRenderTarget(prevTarget);
  target.dispose(); mat.dispose();

  // 경로선은 z-fighting 을 피하려고 표면에서 바깥으로 띄운다. 바깥은 dir 쪽이다.
  const h = new Float32Array(nU * nV).fill(NaN);
  for (let j = 0; j < nV; j++) {
    for (let i = 0; i < nU; i++) {
      const pi = flipU ? nU - 1 - i : i;
      const pj = flipV ? nV - 1 - j : j;
      const k = (pj * nU + pi) * 4;
      if (buf[k + 3] > 0.5 && (!keep || keep(buf[k]))) h[j * nU + i] = buf[k] + PATH_LIFT * dir;
    }
  }
  return { h, nU, nV, u0, u1, v0, v1, u, v, d, dir };
}

/** 위에서 내려찍은 필드. 연마 마스크가 이 필드의 좌표계를 쓰므로
    예전 이름(long/cross/l0..c1/nLong/nCross)도 그대로 달아 둔다. */
function buildHeightField(renderer, model, nLong = 256, nCross = 160) {
  const b = new THREE.Box3().setFromObject(model);
  const size = b.getSize(new THREE.Vector3());
  const long = size.x >= size.z ? 'x' : 'z';
  const cross = long === 'x' ? 'z' : 'x';
  const l0 = b.min[long] + size[long] * 0.05, l1 = b.max[long] - size[long] * 0.05;
  const c0 = b.min[cross] + size[cross] * 0.06, c1 = b.max[cross] - size[cross] * 0.06;
  const floor = b.min.y + size.y * 0.26;

  const f = buildField(renderer, model, {
    u: long, v: cross, d: 'y', dir: 1, nU: nLong, nV: nCross,
    u0: l0, u1: l1, v0: c0, v1: c1,
    keep: (y) => y > floor,
  });
  return Object.assign(f, { nLong, nCross, l0, l1, c0, c1, long, cross });
}

/** 옆에서 찍은 필드 두 장. 문짝·펜더처럼 위에서는 담을 수 없는 면을 낸다.
    바퀴는 뺀다 — 광택 대상이 아니고, 넣으면 팔이 타이어를 훑는다. */
const WHEEL = /wheel|tire|tyre|rim|brake|caliper|hub/i;

function buildSideFields(renderer, model, nU = 256, nV = 96) {
  const b = new THREE.Box3().setFromObject(model);
  const size = b.getSize(new THREE.Vector3());
  const long = size.x >= size.z ? 'x' : 'z';
  const cross = long === 'x' ? 'z' : 'x';
  const u0 = b.min[long] + size[long] * 0.05, u1 = b.max[long] - size[long] * 0.05;
  // 아래는 사이드실 아래를 버리고, 위는 위에서 찍은 필드가 이미 맡은 구간을 피한다
  const v0 = b.min.y + size.y * 0.05, v1 = b.max.y - size.y * 0.30;
  const cd = (b.min[cross] + b.max[cross]) / 2;

  return [1, -1].map((dir) => buildField(renderer, model, {
    u: long, v: 'y', d: cross, dir, nU, nV, u0, u1, v0, v1,
    // 창을 통해 반대편 옆면이 보이는 표본은 버린다 — 카메라 쪽 절반만 남긴다
    keep: (c) => c * dir > cd * dir,
    skip: WHEEL,
  }));
}

/** 앞·뒤에서 두 장 — 범퍼·보닛 앞끝·트렁크 뒷면. u = 폭, v = 높이, d = 길이축. */
function buildEndFields(renderer, model, nU = 160, nV = 96) {
  const b = new THREE.Box3().setFromObject(model);
  const size = b.getSize(new THREE.Vector3());
  const long = size.x >= size.z ? 'x' : 'z';
  const cross = long === 'x' ? 'z' : 'x';
  const u0 = b.min[cross] + size[cross] * 0.06, u1 = b.max[cross] - size[cross] * 0.06;
  const v0 = b.min.y + size.y * 0.12, v1 = b.max.y - size.y * 0.35;
  const cd = (b.min[long] + b.max[long]) / 2;
  return [1, -1].map((dir) => buildField(renderer, model, {
    u: cross, v: 'y', d: long, dir, nU, nV, u0, u1, v0, v1,
    keep: (c) => c * dir > cd * dir,
    skip: WHEEL,
  }));
}

// serpentine passes read off the height field at the requested lane pitch
// 필드보다 가파른 면은 패드가 법선을 따라 접근할 수 없으므로 경로를 내지 않는다.
const MAX_SLOPE = 62 * Math.PI / 180;

/** 필드 기울기에서 표면 법선을 낸다. 중앙차분, 가장자리는 편차분.
    (u, v, h) 면의 법선은 (-hu, -hv, 1) 이고 바깥쪽은 dir 쪽이다. */
function fieldNormal(field, i, j, out) {
  const { h, nU, nV, u0, u1, v0, v1, u, v, d, dir } = field;
  const du = (u1 - u0) / (nU - 1);
  const dv = (v1 - v0) / (nV - 1);
  const at = (ii, jj) => {
    if (ii < 0 || ii >= nU || jj < 0 || jj >= nV) return NaN;
    return h[jj * nU + ii];
  };
  const pick = (a, bb, c, step) => {
    // 중앙차분이 안 되면 한쪽만으로 낸다
    if (!Number.isNaN(a) && !Number.isNaN(bb)) return (bb - a) / (2 * step);
    if (!Number.isNaN(bb) && !Number.isNaN(c)) return (bb - c) / step;
    if (!Number.isNaN(a) && !Number.isNaN(c)) return (c - a) / step;
    return 0;
  };
  const gu = pick(at(i - 1, j), at(i + 1, j), at(i, j), du);
  const gv = pick(at(i, j - 1), at(i, j + 1), at(i, j), dv);
  out.set(0, 0, 0);
  out[u] = -gu * dir;
  out[v] = -gv * dir;
  out[d] = dir;
  return out.normalize();
}

function tracePath(field, spacing) {
  const { h, nU, nV, u0, u1, v0, v1, u, v, d, dir } = field;
  const span = v1 - v0;
  const du = (u1 - u0) / (nU - 1);
  // 한 스텝에서 허용할 최대 깊이차. 이걸 넘으면 단차이므로 잇지 않는다.
  const maxRise = du * Math.tan(MAX_SLOPE) * 1.6;

  const lanes = [];
  const normals = [];
  let sweep = 1;
  for (let vv = v0; vv <= v1; vv += spacing) {
    const jf = ((vv - v0) / span) * (nV - 1);
    const j = Math.max(0, Math.min(nV - 1, Math.round(jf)));
    const lane = [];
    const lnorm = [];
    const lidx = [];
    for (let i = 0; i < nU; i++) {
      const idx = sweep > 0 ? i : nU - 1 - i;
      const dv2 = h[j * nU + idx];
      if (Number.isNaN(dv2)) continue;
      const n = fieldNormal(field, idx, j, new THREE.Vector3());
      // 필드를 마주보지 않는 면은 이 방향에서 접근할 수 없다
      if (Math.acos(Math.min(1, Math.max(-1, n[d] * dir))) > MAX_SLOPE) continue;
      const p = new THREE.Vector3();
      p[d] = dv2;
      p[u] = u0 + (u1 - u0) * (idx / (nU - 1));
      p[v] = vv;
      lane.push(p);
      lnorm.push(n);
      lidx.push(idx);
    }
    if (lane.length > 2) { lanes.push(lane); normals.push(lnorm); lane.idx = lidx; }
    sweep *= -1;
  }

  const pts = [];
  lanes.forEach((l) => {
    for (let i = 1; i < l.length; i++) {
      // 표본이 인접해 있고 단차가 아닐 때만 잇는다
      const step = Math.abs(l.idx[i] - l.idx[i - 1]);
      if (step > 2) continue;
      if (Math.abs(l[i][d] - l[i - 1][d]) > maxRise * step) continue;
      pts.push(l[i - 1], l[i]);
    }
  });
  return { pts, lanes, normals };
}

function envTexture(renderer) {
  const w = 1024, h = 512;
  const cv = document.createElement('canvas');
  cv.width = w; cv.height = h;
  const g = cv.getContext('2d');
  g.fillStyle = '#0a0d12'; g.fillRect(0, 0, w, h);
  const sky = g.createLinearGradient(0, 0, 0, h * 0.5);
  sky.addColorStop(0, '#2b323d'); sky.addColorStop(1, '#0d1116');
  g.fillStyle = sky; g.fillRect(0, 0, w, h * 0.5);
  const box = (cx, cy, bw, bh, i) => {
    const rg = g.createRadialGradient(cx, cy, 0, cx, cy, Math.max(bw, bh));
    rg.addColorStop(0, `rgba(255,255,255,${i})`);
    rg.addColorStop(0.45, `rgba(220,230,245,${i * 0.45})`);
    rg.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = rg;
    g.save(); g.translate(cx, cy); g.scale(1, bh / bw);
    g.beginPath(); g.arc(0, 0, bw, 0, Math.PI * 2); g.fill(); g.restore();
  };
  box(w * 0.5, h * 0.12, 340, 150, 1.0);
  box(w * 0.12, h * 0.36, 170, 240, 0.6);
  box(w * 0.88, h * 0.34, 150, 220, 0.5);

  /* 스트립 조명 — 경계가 뚜렷한 광원.

     거칠기가 하는 일은 반사를 뭉개는 것이다. 그런데 반사할 대상이
     위의 부드러운 blob 뿐이면 뭉개나 마나 같아 보여서, 무광(0.82)과
     유광(0.14)의 차이가 화면에 안 나타난다. 실제로 재보니 완전 무광과
     완전 유광의 픽셀차가 평균 1.77/255 였다 — 셰이더는 도는데 안 보였다.

     자동차 스튜디오가 긴 스트립 조명을 쓰는 이유가 이것이다.
     무광에서는 넓고 흐린 띠로, 유광에서는 날카로운 선으로 맺힌다.
     그 대비가 곧 '닦였다'는 신호다. */
  const strip = (x0, y0, sw, sh, i) => {
    // 짧은 축만 아주 좁게 풀어 준다. 여기를 넓히면 다시 blob 이 된다
    const lg = g.createLinearGradient(0, y0, 0, y0 + sh);
    lg.addColorStop(0, 'rgba(255,255,255,0)');
    lg.addColorStop(0.10, `rgba(255,255,255,${i})`);
    lg.addColorStop(0.90, `rgba(255,255,255,${i})`);
    lg.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = lg;
    g.fillRect(x0, y0, sw, sh);
  };
  /* 위치가 중요하다. 카메라 앙각이 약 11도라, 후드·루프 같은 수평 패널이
     카메라로 되돌려 보내는 반사는 앙각 11도 부근(equirect y≈226)에서 온다.
     천장 꼭대기(y≈50)에 걸면 아무 패널에도 안 잡힌다 — 처음에 그렇게 두고
     효과가 없다고 착각했다. 곡면이 각도를 훑으므로 앙각 6~30도를 덮는다. */
  strip(w * 0.04, h * 0.345, w * 0.34, 20, 0.95);   // 앙각 ~28도
  strip(w * 0.46, h * 0.385, w * 0.30, 17, 0.90);   // ~20도
  strip(w * 0.16, h * 0.425, w * 0.46, 14, 1.00);   // ~13도 — 수평 패널이 이걸 문다
  strip(w * 0.70, h * 0.445, w * 0.26, 12, 0.80);   // ~10도

  g.fillStyle = 'rgba(200,215,235,0.4)';
  g.fillRect(0, h * 0.455, w, 5);
  const tex = new THREE.Texture(cv);
  tex.mapping = THREE.EquirectangularReflectionMapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.needsUpdate = true;
  const pm = new THREE.PMREMGenerator(renderer);
  const env = pm.fromEquirectangular(tex).texture;
  pm.dispose(); tex.dispose();
  return env;
}


/* ══════════════════════════════════════════════════════════════════
   Doosan M0609 관절 리그

   자산: assets/models/robot_arm.opt.glb — base_link·link_1…link_6·
   tool_sander 가 각각 별도 노드이고, 지오메트리는 "포즈된 상태의 월드
   좌표"로 구워져 있다.

   피벗 거리는 cacadaca/rmpflow/m0609_isaac_sim.urdf 의 링크 길이
   (어깨 0.1345 · 상완 0.411 · 전완 0.368 · 손목 0.121)로 강제했고,
   축 방향은 포즈된 형상에서 유도했다. 유도 과정은 rig-check.html 로
   검수할 수 있다.
   ══════════════════════════════════════════════════════════════════ */
// 청크가 블롭 URL 로 실행되므로 상대경로가 문서 기준으로 풀리지 않는다.
// 자산은 문서 위치를 기준으로 절대화한다.
const asset = (rel) => new URL(rel, location.href).href;
const ARM_URL = asset('assets/models/robot_arm.opt.glb');
/* 레일 폭 배율 — 받침판 폭을 여기서 역산하므로 레일 배치와 반드시 같은 값을 쓴다 */
const RAIL_SX = 0.55;
const LIFT_URL = asset('assets/models/lift.opt.glb');   // 텔레스코픽 컬럼 0.80 x 2.11 x 0.80 m
const RAIL_URL = asset('assets/models/rail.opt.glb');   // 직선 레일, 원본 길이 22.86 m
const MESHOPT_URL = asset('assets/vendor/meshopt_decoder.mjs');
// 차체는 디스크의 압축본을 쓴다. 번들에 박아 두면 HTML 하나가 6MB 가 된다 —
// CLAUDE.md 성능 예산과 '자산을 base64 로 박지 마라' 규칙 그대로다.
/* 차종 3개. 예전에는 셋이 Z4 하나를 색만 바꿔 쓰고 있었다 — 2026-09-01 에
   벤츠·페라리 실제 스캔을 넣었다. 감축 과정은 ASSETS.md 「차종 3종」 참고.
   tint 는 도장색이다. 세 모델 모두 재질이 하나뿐이라 원본 색이 의미가 없다. */
const CAR_MODELS = {
  z4:    { url: asset('assets/models/car.opt.glb'),     tint: 0x2f343b },
  coupe: { url: asset('assets/models/benz.opt.glb'),    tint: 0x3a3f47 },
  sf90:  { url: asset('assets/models/ferrari.opt.glb'), tint: 0x353a42 },
  sonata:{ url: asset('assets/models/sonata.opt.glb'),  tint: 0x3f444c },
  /* Isaac 이 쓰는 스캔 차체(BMW Z4 스캔, 미터, 길이 3.04 m) — 실제 Isaac 피드/기록을 따를 때
     setLive 가 자동 선택한다. meshopt 감축본이 아니다(4.9 MB): 셀 판정·IK 정합에 원본 정점이 필요하다. */
  scan:  { url: asset('assets/models/car_scan.glb'),    tint: 0x2f343b },
};

const RIG = {
  j1: { p: [0.000000, 0.134500, 0.000000], a: [0.000000, 1.000000, 0.000000] },
  j2: { p: [0.000000, 0.134500, 0.000000], a: [0.018108, 0.000991, -0.999836] },
  j3: { p: [-0.372969, 0.307046, -0.006584], a: [0.018108, 0.000991, -0.999836] },
  j4: { p: [-0.240990, 0.650555, -0.003853], a: [0.358637, 0.933447, 0.007420] },
  j5: { p: [-0.240990, 0.650555, -0.003853], a: [-0.024697, 0.017434, -0.999543] },
  j6: { p: [-0.120059, 0.653060, -0.007083], a: [0.761661, 0.647932, -0.007518] },
};
const RIG_ORDER = ['j1', 'j2', 'j3', 'j4', 'j5', 'j6'];
const RIG_LINK = { j1: 'link_1', j2: 'link_2', j3: 'link_3', j4: 'link_4', j5: 'link_5', j6: 'link_6' };
// URDF joint limit — 실물 가동범위를 넘기면 즉시 가짜로 보인다
const RIG_LIMITS = [[-Math.PI, Math.PI], [-Math.PI, Math.PI], [-2.72, 2.72],
                    [-Math.PI, Math.PI], [-2.27, 2.27], [-Math.PI, Math.PI]];
const PAD_OFFSET = 0.046;   // j6 → 패드 접촉면 (m), 툴 정점 26만 개에서 실측
const REACH = 0.86;         // 어깨에서 패드까지 실용 도달거리 (m)
// 관절 각속도 상한 (rad/s). IK 는 목표가 튀면 해도 튄다 — 실물처럼 한 프레임에
// 꺾이지 않게 여기서 한 번 거른다. M0609 정격 선회속도가 이 언저리다.
const JOINT_RATE = 3.2;
// 레일 대차 속도 (m/s). 지수 추종으로 두면 대차가 목표에 0.2 m 씩 뒤처지고,
// 그만큼 팔이 닿지 못해 패드가 표면에서 뜬다. 속도만 제한하고 따라붙게 한다.
const RAIL_SPEED = 1.8;

/* ── Isaac 동기화(LIVE) ─────────────────────────────────────────────
   시뮬 피드(/api/monitor)에 로봇별 관절각 q[6]·베이스 자세가 실려 오면 자체 IK 대신 그대로 따라간다.
   리그의 q=0 은 GLB 에 구워진 자세이고 리그는 URDF 의 거울상(map (−x, z, −y), det −1)이라
   q_rig = LIVE_Q_SIGN · (q_isaac − LIVE_Q_OFFSET). 값은 scratchpad/rig_calib.py 최소제곱 결과
   (피벗 오차 ≤ 41 mm). Isaac 실측으로 확정 전까지는 근사. */
const LIVE_Q_SIGN = [-1, -1, -1, -1, -1, -1];
const LIVE_Q_OFFSET = [-0.0034, 1.1651, -1.5641, -0.0116, -0.6794, 0.0];
const LIVE_LONG_FLIP = true;    // 콘솔 차체 앞(+z) = Isaac 앞(+y). false 면 앞뒤가 뒤집힌다
const LIVE_JOINT_RATE = 6.0;    // 피드는 수 Hz 라 따라붙는 속도를 공정보다 높인다 (rad/s)
// Isaac(Z-up, x 가로·y 길이·z 높이) → three(Y-up): 거울상 map (−x, z, −y)
const _LIVE_M = new THREE.Matrix3().set(-1, 0, 0, 0, 0, 1, 0, -1, 0);

/* meshopt/KHR_mesh_quantization 로 구운 GLB 는 위치·법선을 정수로 담고
   노드 스케일로 복원한다. 이 상태에서 geometry.applyMatrix4() 를 쓰면
   변환한 실수값을 정수 배열에 도로 써 넣어 형상이 뭉개진다.
   행렬을 적용하기 전에 float 으로 풀어둔다. */
function dequantize(geo) {
  for (const name of ['position', 'normal']) {
    const a = geo.attributes[name];
    if (!a || (!a.normalized && a.array.BYTES_PER_ELEMENT >= 4)) continue;
    const f = new Float32Array(a.count * a.itemSize);
    for (let i = 0; i < a.count; i++) {
      f[i * a.itemSize] = a.getX(i);
      f[i * a.itemSize + 1] = a.getY(i);
      if (a.itemSize > 2) f[i * a.itemSize + 2] = a.getZ(i);
    }
    geo.setAttribute(name, new THREE.BufferAttribute(f, a.itemSize));
  }
  return geo;
}

async function loadArmParts(url) {
  const { GLTFLoader } = await loadAddon('loaders/GLTFLoader.js');
  // meshopt 로 압축한 GLB 다. 디코더를 붙이지 않으면 로더가 거부한다.
  const { MeshoptDecoder } = await import(MESHOPT_URL);
  const gltf = await new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).loadAsync(url);
  const parts = {};
  gltf.scene.updateMatrixWorld(true);
  gltf.scene.traverse((o) => {
    if (!o.isMesh) return;
    const g = dequantize(o.geometry.clone());
    g.applyMatrix4(o.matrixWorld);
    if (!g.attributes.normal) g.computeVertexNormals();
    parts[o.name.replace(/\.\d+$/, '')] = g;
  });
  const need = ['base_link', 'link_1', 'link_2', 'link_3', 'link_4', 'link_5', 'link_6', 'tool_sander'];
  const missing = need.filter((k) => !parts[k]);
  if (missing.length) throw new Error('링크 누락: ' + missing.join(', '));
  return parts;
}

/** 단일 메시 프롭(리프트·레일)을 지오메트리 하나로 읽는다. */
async function loadProp(url, longAxis) {
  const { GLTFLoader } = await loadAddon('loaders/GLTFLoader.js');
  const { MeshoptDecoder } = await import(MESHOPT_URL);
  const gltf = await new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).loadAsync(url);
  const geos = [];
  gltf.scene.updateMatrixWorld(true);
  gltf.scene.traverse((o) => {
    if (!o.isMesh) return;
    const g = dequantize(o.geometry.clone());
    g.applyMatrix4(o.matrixWorld);
    if (!g.attributes.normal) g.computeVertexNormals();
    geos.push(g);
  });
  if (!geos.length) throw new Error('빈 프롭: ' + url);
  let geo = geos[0];
  if (geos.length > 1) {
    const { mergeGeometries } = await loadAddon('utils/BufferGeometryUtils.js');
    geo = mergeGeometries(geos, false);
  }
  /* 자산이 누워서 구워져 있다 — 실측하면 리프트는 기둥축이 Z(0.80 x 0.80 x 2.11 m),
     레일은 길이가 Y(0.89 x 22.86 x 0.19 m) 다. 배치 코드가 축을 추측하는 대신
     여기서 가장 긴 변을 요청한 축으로 돌려 둔다. 이걸 빼면 리프트가 눕고
     레일이 22.86 m 짜리 벽으로 선다. */
  geo.computeBoundingBox();
  const s0 = geo.boundingBox.getSize(new THREE.Vector3());
  const cur = s0.x >= s0.y && s0.x >= s0.z ? 'x' : (s0.y >= s0.z ? 'y' : 'z');
  if (longAxis && cur !== longAxis) {
    const R = { zy: ['x', -1], yz: ['x', 1], xy: ['z', 1],
                yx: ['z', -1], xz: ['y', -1], zx: ['y', 1] }[cur + longAxis];
    const m = new THREE.Matrix4();
    if (R[0] === 'x') m.makeRotationX(R[1] * Math.PI / 2);
    else if (R[0] === 'y') m.makeRotationY(R[1] * Math.PI / 2);
    else m.makeRotationZ(R[1] * Math.PI / 2);
    geo.applyMatrix4(m);
  }

  // 원점을 "바닥 중앙"으로 통일한다. 배치 코드가 자산의 원점을 추측하지 않게.
  geo.computeBoundingBox();
  const b = geo.boundingBox;
  geo.translate(-(b.min.x + b.max.x) / 2, -b.min.y, -(b.min.z + b.max.z) / 2);
  geo.computeBoundingBox();
  geo.userData.size = geo.boundingBox.getSize(new THREE.Vector3());
  return geo;
}

function robotCell(parts, mats) {
  const g = new THREE.Group();

  // 받침대는 layoutCells 에서 원통 또는 텔레스코픽 리프트로 채운다
  const stand = new THREE.Group();
  g.add(stand);
  g.userData.stand = stand;

  const arm = new THREE.Group();
  g.add(arm);
  g.userData.armRoot = arm;

  const mk = (geo, m) => {
    const o = new THREE.Mesh(geo, m);
    o.castShadow = true; o.receiveShadow = true;
    return o;
  };
  arm.add(mk(parts.base_link, mats.dark));

  const joints = [];
  let parent = arm;
  let prev = new THREE.Vector3();
  for (const key of RIG_ORDER) {
    const p = new THREE.Vector3().fromArray(RIG[key].p);
    const node = new THREE.Group();
    node.position.copy(p).sub(prev);
    node.userData.axis = new THREE.Vector3().fromArray(RIG[key].a).normalize();
    parent.add(node);
    const mesh = mk(parts[RIG_LINK[key]], mats.arm);
    mesh.position.copy(p).negate();          // 월드로 구운 지오메트리를 되돌린다
    node.add(mesh);
    joints.push(node);
    parent = node;
    prev = p;
  }

  const j6p = new THREE.Vector3().fromArray(RIG.j6.p);
  const j6a = new THREE.Vector3().fromArray(RIG.j6.a).normalize();

  const toolMesh = mk(parts.tool_sander, mats.tool);
  toolMesh.position.copy(j6p).negate();
  parent.add(toolMesh);

  // 패드 앵커 — 원점이 접촉면, +Z 가 바깥 법선
  const padAnchor = new THREE.Object3D();
  /* 샌더 메시 실측(robot_arm.opt.glb, tool_sander 정점 19,522개): 하우징은 관절 6 축선에서 옆으로 1.85 cm(리그 월드 +z 방향) 비껴 있고
     바닥면은 축 방향 +0.030 m. 앵커(스펀지 접촉면) = 그 바닥면 + 플레이트 0.8 cm + 폼 2.8 cm = +0.066, 횡오프셋 포함. */
  padAnchor.position.set(0.0004, -0.0002, 0.0185).addScaledVector(j6a, 0.066);
  padAnchor.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), j6a);
  parent.add(padAnchor);

  /* 연마 스펀지 패드 — 접촉면(앵커 원점)에서 툴 쪽(+Z)으로 2.8 cm 두께의 폼 + 어두운 백킹 플레이트.
     떠 있는 얇은 원판 대신 실제 패드처럼 보이고, 툴 하우징과의 틈을 메운다. */
  /* 앵커 좌표계: 원점 = 접촉면, +Z = 표면 안쪽(툴 축 방향), −Z = 툴(하우징) 쪽. 스펀지는 −Z 쪽에 쌓는다:
     접촉면(0) ← 폼 2.8 cm ← 백킹 플레이트 ← 하우징 면. 앵커 자체를 폼 두께만큼 툴 축 앞으로 내보내 하우징에 붙인다. */
  const padDisc = new THREE.Group();
  const foam = new THREE.Mesh(new THREE.CylinderGeometry(0.052, 0.055, 0.028, 40), mats.pad);
  foam.rotation.x = Math.PI / 2; foam.position.z = -0.014; foam.castShadow = true;
  const plate = new THREE.Mesh(new THREE.CylinderGeometry(0.068, 0.072, 0.01, 40), mats.dark);   // 하우징 바닥(반경 ≈7.6 cm)에 맞는 백킹 플레이트
  plate.rotation.x = Math.PI / 2; plate.position.z = -0.033;
  // 회전이 보이게: 폼 옆면에 어두운 띠 무늬 2개 (대칭 원통은 돌아도 안 보인다)
  for (const a of [0, Math.PI]) {
    const mark = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.03, 0.006), mats.dark);
    mark.position.set(Math.cos(a) * 0.053, Math.sin(a) * 0.053, -0.014); mark.rotation.z = a;
    padDisc.add(mark);
  }
  padDisc.add(foam, plate);
  padAnchor.add(padDisc);
  // 작업 지점 표시 — 레이저처럼 툴에서 표면으로 내려오는 투명한 빔과 표면 글로우(월드에 두고 매 프레임 옮긴다)
  const glow = new THREE.MeshBasicMaterial({ color: 0x8FE9FF, transparent: true, opacity: 0.42, blending: THREE.AdditiveBlending, depthWrite: false, depthTest: true, side: THREE.DoubleSide });
  const spot = new THREE.Mesh(new THREE.CircleGeometry(0.075, 40), glow);
  const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.005, 0.012, 1, 12, 1, true), new THREE.MeshBasicMaterial({ color: 0x8FE9FF, transparent: true, opacity: 0.22, blending: THREE.AdditiveBlending, depthWrite: false, depthTest: true }));
  spot.renderOrder = 20; beam.renderOrder = 20;   // 차체 뒤에 가려지지 않게 마지막에 그린다
  spot.visible = false; beam.visible = false;
  g.userData.spot = spot; g.userData.beam = beam;

  g.userData.joints = joints;
  g.userData.padAnchor = padAnchor;
  g.userData.padDisc = padDisc;
  g.userData.q = new Array(6).fill(0);
  // 툴 축 위의 보조점 — 위치와 자세를 한 번에 맞추기 위한 두 번째 제어점
  g.userData.padBack = new THREE.Object3D();
  g.userData.padBack.position.z = -0.12;
  padAnchor.add(g.userData.padBack);
  return g;
}

function setCellQ(cell, q) {
  const js = cell.userData.joints;
  for (let i = 0; i < 6; i++) {
    const v = THREE.MathUtils.clamp(q[i], RIG_LIMITS[i][0], RIG_LIMITS[i][1]);
    cell.userData.q[i] = v;
    js[i].quaternion.setFromAxisAngle(js[i].userData.axis, v);
  }
}

/* CCD IK — 패드 접촉면과 툴 축 위 보조점, 두 점을 동시에 맞춰
   위치와 자세를 한 번에 푼다. 이전 프레임 해에서 웜스타트한다. */
const _wp = new THREE.Vector3(), _wb = new THREE.Vector3(), _ax = new THREE.Vector3();
const _v1 = new THREE.Vector3(), _v2 = new THREE.Vector3(), _jp = new THREE.Vector3();
const _q = new THREE.Quaternion();
const _ikPad = new THREE.Vector3(), _ikBack = new THREE.Vector3(), _ikBase = new THREE.Vector3();
const _tgtP = new THREE.Vector3(), _tgtN = new THREE.Vector3(), _leadP = new THREE.Vector3();

function solveIK(cell, targetPad, targetBack, iterations = 4, tol = 0.0015) {
  const js = cell.userData.joints;
  const q = cell.userData.q;
  let residual = Infinity;
  for (let it = 0; it < iterations; it++) {
    // 후반 반복에서는 자세보다 위치를 우선한다. 두 목표가 서로 당기면
    // 어느 쪽도 수렴하지 못하고 잔차가 남는다.
    const backW = it < iterations * 0.5 ? 0.6 : 0.15;
    for (let i = 5; i >= 0; i--) {
      const node = js[i];
      node.getWorldPosition(_jp);
      _ax.copy(node.userData.axis).applyQuaternion(node.getWorldQuaternion(_q)).normalize();

      cell.userData.padAnchor.getWorldPosition(_wp);
      cell.userData.padBack.getWorldPosition(_wb);

      // 두 제어점의 오차를 관절축 둘레의 회전각 하나로 근사한다
      let num = 0, den = 0;
      for (const [cur, goal, w] of [[_wp, targetPad, 1.0], [_wb, targetBack, backW]]) {
        _v1.copy(cur).sub(_jp);
        _v1.addScaledVector(_ax, -_v1.dot(_ax));        // 축에 수직인 성분만
        if (_v1.lengthSq() < 1e-8) continue;
        _v2.copy(goal).sub(_jp);
        _v2.addScaledVector(_ax, -_v2.dot(_ax));
        if (_v2.lengthSq() < 1e-8) continue;
        const r = _v1.length();
        _v1.normalize(); _v2.normalize();
        const cross = _v1.clone().cross(_v2).dot(_ax);
        const dot = THREE.MathUtils.clamp(_v1.dot(_v2), -1, 1);
        num += w * r * Math.atan2(cross, dot);
        den += w * r;
      }
      if (den < 1e-8) continue;
      const step = THREE.MathUtils.clamp(num / den, -0.35, 0.35);
      q[i] = THREE.MathUtils.clamp(q[i] + step, RIG_LIMITS[i][0], RIG_LIMITS[i][1]);
      node.quaternion.setFromAxisAngle(node.userData.axis, q[i]);
      node.updateMatrixWorld(true);
    }
    cell.userData.padAnchor.getWorldPosition(_wp);
    residual = _wp.distanceTo(targetPad);
    if (residual < tol) break;
  }
  cell.userData.residual = residual;
  return residual;
}

class PolyTwinViewport extends HTMLElement {
  connectedCallback() {
    if (this._init) {
      cancelAnimationFrame(this._raf);
      this._raf = requestAnimationFrame(this._tick.bind(this));
      addEventListener('resize', this._onResize);
      this._onResize();
      return;
    }
    this._init = true;
    this.style.display = 'block';

    /* 그래픽 품질 — 내장 GPU(Intel/AMD APU)나 소프트웨어 렌더러면 MSAA·소프트 그림자·1.5x 픽셀비가
       프레임을 떨어뜨린다(크롬이 Intel 에 msaa_is_slow 워크어라운드를 건다). WebGL 렌더러 이름을 미리 읽어
       가벼운 프리셋을 고른다. localStorage 'pt.gfx' = 'high' | 'low' 로 강제할 수 있다. */
    const gfx = (() => {
      let pref = null; try { pref = localStorage.getItem('pt.gfx'); } catch { pref = null; }
      if (pref === 'high' || pref === 'low') return pref;
      try {
        const c = document.createElement('canvas');
        const gl = c.getContext('webgl2') || c.getContext('webgl');
        const ext = gl && gl.getExtension('WEBGL_debug_renderer_info');
        const name = ext ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : '';
        this._gpuName = name;
        return /intel|llvmpipe|swiftshader|software|radeon\(tm\) graphics|apu/i.test(name) ? 'low' : 'high';
      } catch { return 'high'; }
    })();
    this._gfx = gfx;
    const renderer = new THREE.WebGLRenderer({ antialias: gfx === 'high', alpha: true,
                                               powerPreference: 'high-performance' });
    renderer.setPixelRatio(gfx === 'high' ? Math.min(devicePixelRatio, 1.5) : 1);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.25;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = gfx === 'high' ? THREE.PCFSoftShadowMap : THREE.PCFShadowMap;
    if (gfx === 'low') console.info('[viewport] 저사양 프리셋 (GPU: ' + (this._gpuName || '?') + ') — localStorage pt.gfx=high 로 해제');
    renderer.setClearColor(0x000000, 0);
    this.appendChild(renderer.domElement);
    Object.assign(renderer.domElement.style, { display: 'block', width: '100%', height: '100%' });

    const scene = new THREE.Scene();
    scene.environment = envTexture(renderer);
    scene.environmentIntensity = 1.0;

    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
    camera.position.set(5.6, 2.3, 6.2);

    const key = new THREE.DirectionalLight(0xffffff, 3.0);
    key.position.set(2.4, 6.5, 3.2);
    key.castShadow = true;
    key.shadow.mapSize.set(gfx === 'high' ? 1024 : 512, gfx === 'high' ? 1024 : 512);
    key.shadow.autoUpdate = false;
    key.shadow.needsUpdate = true;
    key.shadow.camera.left = -6; key.shadow.camera.right = 6;
    key.shadow.camera.top = 6; key.shadow.camera.bottom = -6;
    key.shadow.camera.near = 1; key.shadow.camera.far = 24;
    key.shadow.normalBias = 0.03;
    const rimL = new THREE.DirectionalLight(0xbcd4ff, 1.5);
    rimL.position.set(-7, 3.4, -4.5);
    const rimR = new THREE.DirectionalLight(0xffd9c2, 1.1);
    rimR.position.set(7.5, 2.6, -3.5);
    const hemi = new THREE.HemisphereLight(0x8496ad, 0x080a0d, 0.5);
    scene.add(key, rimL, rimR, hemi);

    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(60, 60),
      new THREE.MeshPhysicalMaterial({ color: 0x0b0e12, roughness: 0.92, metalness: 0 })
    );
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);

    const grid = new THREE.GridHelper(24, 48, 0x1c2128, 0x141821);
    grid.position.y = 0.002;
    scene.add(grid);

    const cars = new THREE.Group();
    scene.add(cars);

    const raster = new THREE.LineSegments(
      new THREE.BufferGeometry(),
      attachPathFade(new THREE.LineBasicMaterial({ color: ACCENT, transparent: true, opacity: 0.62 }))
    );
    cars.add(raster);

    const head = new THREE.Mesh(
      new THREE.SphereGeometry(0.05, 16, 12),
      new THREE.MeshBasicMaterial({ color: ACCENT, transparent: true, opacity: 0.85 })
    );
    head.visible = false;
    cars.add(head);

    const robots = new THREE.Group();
    scene.add(robots);
    const props = new THREE.Group();      // 리프트·레일·갠트리 등 설비
    scene.add(props);
    const cellsLayer = new THREE.Group();  // ③ 셀 판정 지도 — 시뮬 피드/기록의 셀 스냅샷을 차체 위에 색으로
    scene.add(cellsLayer);
    this.cellsLayer = cellsLayer;

    // M0609 의 도달거리는 0.9 m 다. 셀은 차체 바운딩 박스에서 계산해
    // 작업면 바로 옆에 세운다 — 고정 좌표로 3 m 밖에 두면 영원히 닿지 않는다.
    const armMats = {
      dark: new THREE.MeshPhysicalMaterial({ color: 0x22262c, metalness: 0.5, roughness: 0.55 }),
      arm: new THREE.MeshPhysicalMaterial({
        color: 0xb9c0c8, metalness: 0.35, roughness: 0.38,
        clearcoat: 0.4, clearcoatRoughness: 0.3, envMapIntensity: 1.1,
      }),
      tool: new THREE.MeshPhysicalMaterial({ color: 0x2A3038, metalness: 0.6, roughness: 0.4 }),
      pad: new THREE.MeshStandardMaterial({ color: 0xD8B24A, metalness: 0.0, roughness: 0.95 }),   // 연마 스펀지(폼) 색
      lift: new THREE.MeshPhysicalMaterial({ color: 0x5b626b, metalness: 0.45, roughness: 0.62, envMapIntensity: 0.45 }),
      rail: new THREE.MeshPhysicalMaterial({ color: 0x474d55, metalness: 0.5, roughness: 0.58, envMapIntensity: 0.4 }),
    };

    Object.assign(this, { renderer, scene, camera, cars, raster, head, robots, props, ground, grid, armMats });
    this._cells = [];
    this._models = new Map();
    this._armParts = null;

    Promise.all([
      loadArmParts(ARM_URL),
      loadProp(LIFT_URL, 'y').catch((e) => { console.error('리프트 로드 실패:', e); return null; }),
      loadProp(RAIL_URL, 'z').catch((e) => { console.error('레일 로드 실패:', e); return null; }),
    ]).then(([parts, lift, rail]) => {
      this._armParts = parts;
      this._liftGeo = lift;
      this._railGeo = rail;
      this.layoutCells();
    }).catch((err) => console.error('로봇 팔 로드 실패:', err));
    this._params = { pad: 110, overlap: 40, feed: 0.03, force: 8, rpm: 3000, robotCount: 1,
                     hasRail: false, hasLift: false, carLift: 0, running: false };
    this._t0 = performance.now();
    this._vehicle = null;

    this._onResize = () => {
      const w = this.clientWidth || 800, h = this.clientHeight || 600;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.fov = THREE.MathUtils.clamp(34 * (1.5 / camera.aspect), 34, 50);
      camera.updateProjectionMatrix();
    };
    addEventListener('resize', this._onResize);
    this._onResize();

    loadAddon('controls/OrbitControls.js').then(({ OrbitControls }) => {
      const c = new OrbitControls(camera, renderer.domElement);
      c.target.set(0, 0.72, 0);
      c.enableDamping = true;
      c.dampingFactor = 0.08;
      c.minDistance = 3.2;
      c.maxDistance = 14;
      c.maxPolarAngle = Math.PI / 2 - 0.04;
      c.update();
      this._controls = c;
    });

    this.setVehicle(this.getAttribute('vehicle') || 'z4');
    this._raf = requestAnimationFrame(this._tick.bind(this));
  }

  disconnectedCallback() {
    cancelAnimationFrame(this._raf);
    removeEventListener('resize', this._onResize);
  }

  async setVehicle(id) {
    if (this._vehicle === id) return;
    this._vehicle = id;
    if (this._models.has(id)) {
      this._showVehicle(id);
      return;
    }
    /* 차종마다 자기 모델을 받는다. 처음 고른 것만 내려받는다 —
       셋을 미리 다 받으면 첫 화면이 1.5MB 무거워진다. */
    const car = CAR_MODELS[id] || CAR_MODELS.z4;
    // 같은 차종을 연타해도 파스는 한 번만
    this._carLoads = this._carLoads || new Map();
    if (!this._carLoads.has(id)) this._carLoads.set(id, loadCar(car.url));
    let model;
    try {
      model = await this._carLoads.get(id);
    } catch (err) {
      this._carLoads.delete(id);
      console.error('차체 모델을 불러오지 못했다: ' + car.url, err);
      return;
    }
    model.traverse((o) => { if (o.isMesh) o.material.color.setHex(car.tint); });
    this._models.set(id, model);
    // 받는 사이에 다른 차종으로 넘어갔으면 늦게 온 응답이 화면을 덮지 않게 한다
    if (this._vehicle !== id) return;
    this._showVehicle(id);
  }

  /** 연마 마스크를 하이트필드와 같은 격자로 만든다. */
  initPolish() {
    const f = this._field; if (!f || !this._model) return;
    this._model.updateMatrixWorld(true);
    const b = new THREE.Box3().setFromObject(this._model);
    const LONG = f.long, CROSS = f.cross;
    const mk = (nx, ny) => { const data = new Uint8Array(nx * ny); const tex = new THREE.DataTexture(data, nx, ny, THREE.RedFormat, THREE.UnsignedByteType);
      tex.minFilter = tex.magFilter = THREE.LinearFilter; tex.wrapS = tex.wrapT = THREE.ClampToEdgeWrapping; tex.needsUpdate = true; return { tex, data, nx, ny }; };
    const top = mk(f.nLong, f.nCross);                       // (long, cross)
    const side = mk(256, 96);                                // (long, y)
    const end = mk(160, 96);                                 // (cross, y)
    this._polish = { top, side, end,
      topMin: [f.l0, f.c0], topSpan: [f.l1 - f.l0, f.c1 - f.c0],
      sideMin: [b.min[LONG], b.min.y], sideSpan: [b.max[LONG] - b.min[LONG], b.max.y - b.min.y],
      endMin: [b.min[CROSS], b.min.y], endSpan: [b.max[CROSS] - b.min[CROSS], b.max.y - b.min.y], LONG, CROSS };
    const sel = (axis) => new THREE.Vector3(axis === 'x' ? 1 : 0, 0, axis === 'z' ? 1 : 0);
    polishU.uPolishTop.value = top.tex; polishU.uPolishSide.value = side.tex; polishU.uPolishEnd.value = end.tex;
    polishU.uLongSel.value = sel(LONG); polishU.uCrossSel.value = sel(CROSS);
    polishU.uTopMin.value = new THREE.Vector2(...this._polish.topMin); polishU.uTopSpan.value = new THREE.Vector2(...this._polish.topSpan);
    polishU.uSideMin.value = new THREE.Vector2(...this._polish.sideMin); polishU.uSideSpan.value = new THREE.Vector2(...this._polish.sideSpan);
    polishU.uEndMin.value = new THREE.Vector2(...this._polish.endMin); polishU.uEndSpan.value = new THREE.Vector2(...this._polish.endSpan);
    polishU.uPolishOn.value = 1;
  }

  /** 패드가 지나간 자리를 마스크에 찍는다. 반지름은 패드 지름 파라미터 그대로. */
  stampPolish(worldPos, radius, flat = false, gain = 1.0) {
    const P = this._polish; if (!P) return;
    const L = worldPos[P.LONG], C = worldPos[P.CROSS], Y = worldPos.y;
    // 세 마스크 모두에 찍는다 — 셰이더가 면의 법선으로 한 장을 고르므로, 옆면 아래쪽에 엉뚱한 광택이 생기지 않는다
    const stamp = (m, a, b, aMin, aSpan, bMin, bSpan) => {
      const u = (a - aMin) / aSpan, v = (b - bMin) / bSpan;
      if (u < -0.05 || u > 1.05 || v < -0.05 || v > 1.05) return;
      const ci = u * (m.nx - 1), cj = v * (m.ny - 1);
      const ri = Math.max(1, radius / (aSpan / (m.nx - 1))), rj = Math.max(1, radius / (bSpan / (m.ny - 1)));
      let touched = false;
      for (let j = Math.floor(cj - rj); j <= Math.ceil(cj + rj); j++) {
        if (j < 0 || j >= m.ny) continue;
        for (let i = Math.floor(ci - ri); i <= Math.ceil(ci + ri); i++) {
          if (i < 0 || i >= m.nx) continue;
          const d = Math.hypot((i - ci) / ri, (j - cj) / rj);
          if (d > 1) continue;
          const k = j * m.nx + i;
          const nv = Math.min(255, m.data[k] + 255 * (flat ? gain : (1 - d * d) * 0.9));
          if (nv !== m.data[k]) { m.data[k] = nv; touched = true; }
        }
      }
      if (touched) m.tex.needsUpdate = true;
    };
    stamp(P.top, L, C, P.topMin[0], P.topSpan[0], P.topMin[1], P.topSpan[1]);
    stamp(P.side, L, Y, P.sideMin[0], P.sideSpan[0], P.sideMin[1], P.sideSpan[1]);
    stamp(P.end, C, Y, P.endMin[0], P.endSpan[0], P.endMin[1], P.endSpan[1]);
  }

  /** 차종을 바꾸거나 공정을 다시 시작할 때 연마 상태를 지운다. */
  resetPolish() {
    if (!this._polish) return;
    for (const m of [this._polish.top, this._polish.side, this._polish.end]) { m.data.fill(0); m.tex.needsUpdate = true; }
  }

  /** 차체 바운딩 박스를 기준으로 셀을 배치한다. 대수는 setParams 로 바뀐다. */
  layoutCells() {
    try { this._layoutCells(); }
    catch (err) { console.error('layoutCells 실패:', err); }
  }

  _layoutCells() {
    if (!this._armParts || !this._model) return;
    const p = this._params;
    /* 대수 의미는 Isaac 배치와 같다: 1 = 천장(C), 2 = 좌·우(SL/SR), 3 = 천장 + 좌·우.
       옛 의미(옆면 1~3대 + 리프트 시 천장 추가)는 시뮬과 어긋났다 — 피드/기록의 로봇 id 와 1:1 로 맞춘다. */
    const total = Math.max(1, Math.min(3, p.robotCount || 1));
    const ceiling = total === 1 || total === 3;
    const want = total === 1 ? 0 : 2;
    const sig = [want, !!p.hasRail, !!p.hasLift, p.carLift || 0, this._model.uuid].join('|');
    if (sig === this._cellSig) return;
    this._cellSig = sig;

    this._cells.forEach((c) => { this.robots.remove(c); if (c.userData.spot) this.robots.remove(c.userData.spot, c.userData.beam); });
    while (this.props.children.length) this.props.remove(this.props.children[0]);
    this._cells = [];

    this._model.updateMatrixWorld(true);
    const b = new THREE.Box3().setFromObject(this._model);
    const size = b.getSize(new THREE.Vector3());
    const mid = b.getCenter(new THREE.Vector3());
    const surfaceY = b.max.y;

    /* 차체의 길이축과 폭축. 경로 생성기(buildHeightField)와 같은 규칙을 쓴다.
       레일은 길이축을 따라 깔리고 로봇은 폭축 바깥에 선다. 축을 x/z 로 박아 두면
       차종을 90도 돌려 구운 순간 레일과 로봇이 어긋난다. */
    const LONG = (this._field && this._field.long) || (size.x >= size.z ? 'x' : 'z');
    const CROSS = LONG === 'x' ? 'z' : 'x';
    this._axes = { LONG, CROSS };
    let half = size[CROSS] / 2 + 0.46;
    let l0 = mid[LONG] - size[LONG] * 0.42;
    let l1 = mid[LONG] + size[LONG] * 0.42;
    /* 시뮬을 따르는 중이면 설비 수치도 Isaac 값(feed.scene): 측면 레일 x, 갠트리 반길이·반폭·보 높이 */
    const SC = this._liveScene, XF = this._liveXf;
    const liveGear = !!(SC && XF && SC.rail_x && SC.gantry_half_y);
    if (liveGear) {
      half = Math.abs(Number(SC.rail_x[0]) || 1.36);
      l0 = XF.t.z - Number(SC.gantry_half_y); l1 = XF.t.z + Number(SC.gantry_half_y);
    }
    /* 받침대 높이는 차체 리프트를 따라가지 않는다. 같이 올라가면 어깨와
       옆면의 상대 높이가 그대로라 차를 든 의미가 없다 — 실제로 리프트는
       차를 로봇 쪽으로 올리는 장치다. 차를 들면 사이드실이 어깨로 올라오고
       그만큼 루프는 도달 범위 밖으로 나간다. 그 맞바꿈이 이 슬라이더다. */
    const standY = Math.max(0.2, surfaceY - (p.carLift || 0) - 0.52);
    /* 레일은 ㄷ자 채널이다 — 실측하면 양쪽 립 상면이 0.190, 가운데 바닥판은
       0.025 다. 받침대는 립 상면(= 바운딩 박스 상면)에서 시작한다. 이걸 빼면
       레일이 기둥 밑동을 관통하고 받침판이 레일 밖 바닥에 걸쳐 앉는다. */
    const railH = (p.hasRail && this._railGeo) ? this._railGeo.userData.size.y : 0;
    /* 받침판 폭 — 립 위에 걸쳐 앉아야 한다. 좁으면 립 사이 빈 곳 위에
       떠 보이고, 넓으면 레일 밖으로 나간다. 레일 폭에서 역산하고 양옆
       30 mm 씩 물린다. 레일이 없으면 원래 비율(0.62)을 쓴다. */
    const standS = (p.hasRail && this._railGeo && this._liftGeo)
      ? (this._railGeo.userData.size.x * RAIL_SX - 0.06) / this._liftGeo.userData.size.x
      : 0.62;

    /** 받침대 — 리프트를 켜면 텔레스코픽 컬럼, 아니면 원통 기둥.
        리프트 지오메트리는 loadProp 에서 기둥축을 Y 로 세워 두었다. */
    const buildStand = (cell, height) => {
      const stand = cell.userData.stand;
      while (stand.children.length) stand.remove(stand.children[0]);
      let m;
      if (p.hasLift && this._liftGeo) {
        m = new THREE.Mesh(this._liftGeo, this.armMats.lift);
        m.scale.set(standS, height / this._liftGeo.userData.size.y, standS);
      } else {
        m = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.17, 1, 20), this.armMats.dark);
        m.scale.y = height;
        m.position.y = height / 2;
      }
      m.castShadow = true; m.receiveShadow = true;
      stand.add(m);
    };

    /* 슬롯 — [폭축 부호, 길이축 위치]. 두 대 이상이면 반드시 반대편에 세우고
       길이 방향으로도 엇갈리게 둔다. 같은 쪽에 나란히 두면 두 팔이
       같은 공간을 지난다. */
    const SLOTS = want ? [[-1, 0], [1, 0]] : [];     // 좌(SL)·우(SR) — Isaac 측면 레일과 같이 길이축 가운데

    for (let i = 0; i < want; i++) {
      const side = SLOTS[i][0];
      const cell = robotCell(this._armParts, this.armMats);
      cell.position.set(0, 0, 0);
      cell.position[CROSS] = (liveGear ? XF.t.x : mid[CROSS]) + side * half;
      cell.position[LONG] = mid[LONG] + size[LONG] * SLOTS[i][1];
      /* 레일 위에 앉히고 기둥을 그만큼 줄인다 — 어깨 높이(standY)는 그대로다.
         차체 리프트를 끝까지 올리면 standY 가 하한 0.2 에 걸리므로 기둥에도
         하한을 둔다. 안 그러면 기둥이 0 이 되어 팔이 레일에 박힌다. */
      const columnH = Math.max(0.2, standY - railH);
      cell.position.y = railH;
      buildStand(cell, columnH);
      cell.userData.armRoot.position.y = columnH;

      /* 베이스는 레일과 나란히 둔다. 차체를 향하는 회전은 1축(선회 관절)이
         맡는다 — 셀 전체를 돌리면 받침대 볼트판이 레일과 어긋나 보인다.
         base_link 는 관절 0 의 부모라 이 회전에 따라 돌지 않는다. */
      cell.rotation.y = 0;
      setCellQ(cell, [Math.atan2(mid.x - cell.position.x, mid.z - cell.position.z), 0, 0, 0, 0, 0]);
      /* 공정 전에는 이 자세로 멈춰 선다. 환경을 구성하는 동안 팔이 혼자
         움직이면 이미 공정이 도는 것처럼 보인다 */
      cell.userData.qHome = cell.userData.q.slice();

      cell.userData.side = side;
      cell.userData.robotId = side < 0 ? 'SL' : 'SR';   // 피드/기록의 로봇 id 와 매칭
      cell.userData.onRail = !!p.hasRail;
      cell.userData.span = [l0, l1];
      cell.userData.home = cell.position[LONG];
      this.robots.add(cell);
      this.robots.add(cell.userData.spot, cell.userData.beam);
      this._cells.push(cell);
    }

    /* 차체 리프트 — 4주. 옆면을 닦으려면 차를 들어 올려야 도어가 로봇 어깨
       높이에 온다. 차체는 _applyCarLift 가 이미 올려 뒀으므로 기둥은
       바닥에서 차체 밑면(b.min.y)까지만 세우면 된다. */
    if ((p.carLift || 0) > 0.01) {
      // 텔레스코픽 컬럼 자산을 눌러 쓰면 내부 축이 드러나 앙상해 보인다.
      // 4주 리프트는 각기둥 + 받침판 + 상판이면 충분히 읽힌다.
      const postH = Math.max(0.12, b.min.y);
      for (const su of [-1, 1]) {
        for (const sc of [-1, 1]) {
          const g = new THREE.Group();
          const col = new THREE.Mesh(new THREE.BoxGeometry(0.15, postH, 0.15), this.armMats.lift);
          col.position.y = postH / 2;
          col.castShadow = true; col.receiveShadow = true;
          g.add(col);
          const foot = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.035, 0.36), this.armMats.dark);
          foot.position.y = 0.017;
          foot.receiveShadow = true;
          g.add(foot);
          const cap = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.045, 0.28), this.armMats.dark);
          cap.position.y = postH - 0.022;
          cap.castShadow = true;
          g.add(cap);
          g.position.set(0, 0, 0);
          g.position[LONG] = mid[LONG] + su * size[LONG] * 0.30;
          g.position[CROSS] = mid[CROSS] + sc * size[CROSS] * 0.30;
          this.props.add(g);
        }
      }
    }

    // 바닥 레일 — 셀이 올라타 차체 길이 방향으로 이동한다
    this._rails = {};                                // 로봇 id → 레일 메시 (라이브/재생 때 피드의 베이스 x 로 옮긴다)
    if (p.hasRail && this._railGeo) {
      const seen = new Set();
      for (const cell of this._cells) {
        if (cell.userData.ceiling) continue;
        const c = cell.position[CROSS].toFixed(3);
        if (seen.has(c)) continue;
        seen.add(c);
        const r = new THREE.Mesh(this._railGeo, this.armMats.rail);
        r.scale.set(RAIL_SX, 1, (l1 - l0) / this._railGeo.userData.size.z);
        if (LONG === 'x') r.rotation.y = Math.PI / 2;
        r.position.set(0, 0, 0);
        r.position[CROSS] = Number(c);
        r.position[LONG] = (l0 + l1) / 2;
        r.receiveShadow = true;
        this.props.add(r);
        if (cell.userData.robotId) this._rails[cell.userData.robotId] = r;
      }
    }

    // 천장 갠트리 — 지붕은 옆에서 못 닿는다. 위에서 한 대가 맡는다.
    if (ceiling && this._railGeo && this._liftGeo) {
      const beamY = liveGear && SC.gantry_beam_z ? Number(SC.gantry_beam_z) + XF.t.y : surfaceY + 1.28;
      const beam = new THREE.Mesh(this._railGeo, this.armMats.rail);
      beam.scale.set(RAIL_SX, 1, (l1 - l0) / this._railGeo.userData.size.z);
      beam.rotation.x = Math.PI;                     // 레일 면을 아래로 향하게
      if (LONG === 'x') beam.rotation.y = Math.PI / 2;
      beam.position.set(0, beamY, 0);
      beam.position[CROSS] = mid[CROSS];
      beam.position[LONG] = (l0 + l1) / 2;
      this.props.add(beam);

      // 문형 프레임 — 양쪽에 기둥을 세우고 위를 가로보로 잇는다
      const postC = liveGear && SC.gantry_half_x ? Number(SC.gantry_half_x) + 0.25 : half + 0.62;
      for (const lEnd of [l0, l1]) {
        for (const sc of [-1, 1]) {
          const post = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.09, beamY, 12), this.armMats.dark);
          post.position.set(0, beamY / 2, 0);
          post.position[CROSS] = mid[CROSS] + sc * postC;
          post.position[LONG] = lEnd;
          post.castShadow = true;
          this.props.add(post);
        }
        const cross = new THREE.Mesh(new THREE.BoxGeometry(postC * 2, 0.11, 0.11), this.armMats.dark);
        if (LONG === 'x') cross.rotation.y = Math.PI / 2;
        cross.position.set(0, beamY, 0);
        cross.position[CROSS] = mid[CROSS];
        cross.position[LONG] = lEnd;
        this.props.add(cross);
      }

      // 매달린 리프트 + 팔. 어깨가 지붕 위 0.62 m 에 오도록 길이를 잡는다
      const shoulderY = surfaceY + 0.62;
      const drop = beamY - shoulderY;
      const hang = new THREE.Mesh(this._liftGeo, this.armMats.lift);
      hang.scale.set(0.5, drop / this._liftGeo.userData.size.y, 0.5);
      hang.rotation.x = Math.PI;                     // 뒤집어 매단다
      hang.position.set(0, beamY, 0);
      hang.position[CROSS] = mid[CROSS];
      hang.position[LONG] = mid[LONG];
      this.props.add(hang);
      this._hang = hang; this._beamY = beamY;        // 라이브/재생 때 천장 로봇 베이스를 따라 옮기고 늘인다

      const cell = robotCell(this._armParts, this.armMats);
      cell.position.set(0, shoulderY, 0);
      cell.position[CROSS] = mid[CROSS];
      cell.position[LONG] = mid[LONG];
      cell.rotation.x = Math.PI;                     // 팔을 아래로
      cell.userData.armRoot.position.y = 0;
      cell.userData.ceiling = true;
      cell.userData.robotId = 'C';
      cell.userData.side = 0;                        // 지붕 담당 — 옆면 셀과 구역이 겹치지 않는다
      cell.userData.onRail = true;                   // 갠트리를 따라 길이축으로 이동한다 (레일 슬라이딩과 같은 논리)
      cell.userData.span = [l0, l1];
      cell.userData.home = mid[LONG];
      this.robots.add(cell);
      this.robots.add(cell.userData.spot, cell.userData.beam);
      this._cells.unshift(cell);                     // Isaac 피드 순서(C, SL, SR)와 같게 앞에
    }

    this.assignWork();
  }

  /** 셀마다 겹치지 않는 작업 구역을 준다.

      점 하나를 '닿을 수 있는 셀 중 가장 가까운 셀' 하나에만 준다(보로노이 분할).
      예전처럼 닿기만 하면 전부 나눠 주면 두 팔이 같은 자리를 노려 서로 파고든다.
      그 다음 레인마다 자기 몫의 '가장 긴 연속 구간' 하나만 남긴다 — 끊긴 조각을
      이어 붙이면 팔이 프레임마다 순간이동하고, 그게 버벅임으로 보인다. */
  assignWork() {
    if (!this._lanes || !this._normals || !this._cells.length) return;
    const { LONG, CROSS } = this._axes || { LONG: 'z', CROSS: 'x' };
    this.robots.updateMatrixWorld(true);

    for (const cell of this._cells) {
      const sh = cell.userData.shoulder || (cell.userData.shoulder = new THREE.Vector3());
      cell.userData.joints[0].getWorldPosition(sh);
    }

    // 레일 위 셀은 길이축으로 미끄러지므로 도달 판정에서 그 축을 뺀다.
    // 다만 구역을 가를 때는 약하게(0.3) 살려 둬야 같은 쪽 두 대가 갈린다.
    const gap = (cell, pt, w) => {
      const dc = pt[CROSS] - cell.userData.shoulder[CROSS];
      // 리프트로 어깨 높이를 맞출 수 있는 셀(천장 갠트리, 텔레리프트 측면)은 높이 차도 약하게 본다
      const canLift = cell.userData.ceiling || this._params.hasLift;
      const dy = (pt.y - cell.userData.shoulder.y) * (canLift ? Math.max(w, 0.35) : 1);
      const travel = cell.userData.onRail || cell.userData.ceiling;   // 레일/갠트리를 따라 길이축 이동 가능
      const dl = (pt[LONG] - cell.userData.shoulder[LONG]) * (travel ? w : 1);
      return Math.sqrt(dc * dc + dy * dy + dl * dl);
    };

    const carMid = (() => { try { this._model.updateMatrixWorld(true); return new THREE.Box3().setFromObject(this._model).getCenter(new THREE.Vector3()); } catch { return new THREE.Vector3(); } })();
    const owner = this._lanes.map((lane, li) => lane.map((pt, k) => {
      let best = -1, bd = Infinity;
      const n = this._normals[li] && this._normals[li][k];
      for (let ci = 0; ci < this._cells.length; ci++) {
        const cell = this._cells[ci];
        /* 면 규칙 — 천장 로봇은 위를 향한 면(윗면)만, 측면 로봇은 자기 쪽 옆면·모서리만. 반대편이나 지붕 한가운데로
           팔을 뻗게 두면 차체를 가로질러 관통한다. */
        if (n) {
          if (cell.userData.ceiling) { if (n.y < 0.45) continue; }
          else {
            if (n.y > 0.85) continue;
            if ((pt[CROSS] - carMid[CROSS]) * cell.userData.side < -0.05) continue;
          }
        }
        // 팔을 다 편 자리는 배정하지 않는다. 경계에서는 CCD 가 수렴하지 못해
        // 패드가 표면에서 20 cm 뜬 채로 따라다닌다 — 닿을 수 있는 곳만 맡긴다.
        if (gap(cell, pt, 0) > REACH * 0.90) continue;
        const d = gap(cell, pt, 0.3);
        if (d < bd) { bd = d; best = ci; }
      }
      return best;
    }));

    for (let ci = 0; ci < this._cells.length; ci++) {
      const cell = this._cells[ci];
      const pts = [], nrm = [];
      this._lanes.forEach((lane, li) => {
        const ns = this._normals[li], own = owner[li];
        // 이 레인에서 내 몫의 가장 긴 연속 구간 하나
        let best = null, run = null;
        for (let k = 0; k < lane.length; k++) {
          if (own[k] === ci) { if (run) run[1] = k; else run = [k, k]; }
          else if (run) { if (!best || run[1] - run[0] > best[1] - best[0]) best = run; run = null; }
        }
        if (run && (!best || run[1] - run[0] > best[1] - best[0])) best = run;
        if (!best || best[1] - best[0] < 3) return;
        for (let k = best[0]; k <= best[1]; k++) { pts.push(lane[k]); nrm.push(ns[k]); }
      });

      cell.userData.work = pts;
      cell.userData.workN = nrm;

      /* 누적 호 길이 — 목표를 이송속도로 전진시키기 위한 것.
         레인이 바뀌는 지점은 실제로 건너뛰는 거리이므로 그대로 넣는다.
         예전처럼 0.10 m 로 깎아 두면 2 m 를 한 프레임에 날아간다. */
      const cum = new Float32Array(pts.length);
      let acc = 0;
      for (let i = 1; i < pts.length; i++) {
        acc += pts[i].distanceTo(pts[i - 1]);
        cum[i] = acc;
      }
      cell.userData.cum = cum;
      cell.userData.pathLen = Math.max(0.01, acc);
      cell.userData.s = (cell.userData.s || 0) % cell.userData.pathLen;
      cell.userData.cursor = 0;
    }
  }

  _showVehicle(id) {
    this._models.forEach((m, k) => {
      if (k === id) { if (!m.parent) this.cars.add(m); m.visible = true; }
      else m.visible = false;
    });
    this._model = this._models.get(id);
    this._cellBox = null; this._waBox = null; this._paintBox = null;
    this._applyCarLift();
    // 차종마다 다시 굽는다. 예전에는 처음 한 번만 구워서 차를 바꾸면
    // 앞차의 표면 위에 경로가 그려졌다.
    if (this._fieldFor !== this._model.uuid) {
      this._fieldFor = this._model.uuid;
      this._buildFields();
      this.initPolish();
    }
    this.rebuildPath();
    this.layoutCells();
  }

  /** 차체를 리프트 높이만큼 올린다. cars 그룹이 아니라 차체 모델만 옮긴다 —
      경로선(raster)이 같은 그룹에 있어 그룹을 올리면 두 번 올라간다. */
  _applyCarLift() {
    const y = Math.max(0, this._params.carLift || 0);
    this._models.forEach((m) => { m.position.y = y; m.updateMatrixWorld(true); });
    this._waBox = null; this._paintBox = null;   // 차가 움직였다 — 셀 매핑 기준 상자 무효화 (다음 _buildFields 에서 재계산)
    if (this._live && this._cellsEnabled && this._lastCells) { this._cellsKey = null; this.setCells(this._lastCells, this._lastScene); }   // 이미 찍힌 구슬도 새 높이로 (라이브 중일 때만)
  }

  /** 위에서 한 장, 옆에서 두 장. 옆면 두 장이 도어와 펜더를 맡는다. */
  _buildFields() {
    if (!this._model) return;
    this._model.updateMatrixWorld(true);
    this._field = buildHeightField(this.renderer, this._model);
    this._sideFields = buildSideFields(this.renderer, this._model);
    this._endFields = buildEndFields(this.renderer, this._model);
    // 도장 정점 격자(월드) — 레인 점을 도장 면 근처로 제한(유리·휠·그릴 제외)
    const pts = (this._model.userData && this._model.userData.paintPts) || [];
    const grid = new Map(); const CELL = 0.12;
    const key = (x, y, z) => (Math.floor(x / CELL)) + ',' + (Math.floor(y / CELL)) + ',' + (Math.floor(z / CELL));
    const w = new THREE.Vector3();
    for (const q of pts) { w.copy(q).applyMatrix4(this._model.matrixWorld); const k = key(w.x, w.y, w.z); let arr = grid.get(k); if (!arr) grid.set(k, arr = []); arr.push(w.clone()); }
    this._paintGrid = { grid, CELL, n: pts.length };
    // 도장 면 bbox(휠·미러·유리 제외) — Isaac 스캔 차(도장 면만 스캔) 와 비례가 맞는 기준 상자
    if (pts.length) { const pb = new THREE.Box3(); for (const q of pts) pb.expandByPoint(w.copy(q).applyMatrix4(this._model.matrixWorld)); this._paintBox = pb; }
    else this._paintBox = null;
    this._waBox = null;                       // 셀 매핑 기준 상자는 필드와 같이 다시 잡는다
    if (this._live && this._cellsEnabled && this._lastCells) { this._cellsKey = null; this.setCells(this._lastCells, this._lastScene); }
  }

  /** 윗면 높이맵에서 (long, cross) 위치의 표면 높이 — 없으면 NaN */
  _topHeightAt(pt) {
    const f = this._field; if (!f) return NaN;
    const u = (pt[f.long] - f.l0) / (f.l1 - f.l0), v = (pt[f.cross] - f.c0) / (f.c1 - f.c0);
    if (u < 0 || u > 1 || v < 0 || v > 1) return NaN;
    const i = Math.round(u * (f.nLong - 1)), j = Math.round(v * (f.nCross - 1));
    const h = f.h[j * f.nLong + i];
    return Number.isFinite(h) ? h : NaN;
  }
  /** 팔 관절(2~5)이 차체 안에 있나 — 윗면 높이맵 아래이거나 도장 정점 4 cm 이내 */
  _armInsideCar(cell) {
    const jp = new THREE.Vector3();
    for (const ji of [2, 3, 4, 5]) {
      cell.userData.joints[ji].getWorldPosition(jp);
      const h = this._topHeightAt(jp);
      if (Number.isFinite(h) && jp.y < h - 0.02) return true;
      if (this._paintGrid && this._paintGrid.n && this._nearPaint(jp, 0.04)) return true;
    }
    return false;
  }

  /** 월드 점이 도장 정점에서 r 이내인가 (도장 정점이 수집되지 않은 모델은 항상 true) */
  _nearPaint(pt, r = 0.09) {
    const G = this._paintGrid; if (!G || !G.n) return true;
    const c = G.CELL, r2 = r * r;
    const ix = Math.floor(pt.x / c), iy = Math.floor(pt.y / c), iz = Math.floor(pt.z / c);
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) for (let dz = -1; dz <= 1; dz++) {
      const arr = G.grid.get((ix + dx) + ',' + (iy + dy) + ',' + (iz + dz)); if (!arr) continue;
      for (const q of arr) if (q.distanceToSquared(pt) <= r2) return true;
    }
    return false;
  }

  /** ③ 셀 판정 지도 — snapshot = {total, pass, rework, repaint, not_reached, items:[[x,y,z,disposition,gu],...]} (Isaac 월드).
      Isaac→콘솔 변환(_liveXf)이 있어야 한다(피드/기록의 scene). 처분별 색: 합격 초록·재도장 검토 주황·재작업 빨강. */
  /** 측면 로봇 받침 기둥을 바닥에서 h 까지 — 리프트가 켜져 있으면 텔레스코픽 기둥, 아니면 원통 */
  _setStandHeight(cell, h) {
    const stand = cell.userData.stand; if (!stand) return;
    h = Math.max(0.05, h);
    if (Math.abs((cell.userData.standH || 0) - h) < 0.01) return;
    cell.userData.standH = h;
    while (stand.children.length) stand.remove(stand.children[0]);
    let m;
    if (this._params.hasLift && this._liftGeo) {
      m = new THREE.Mesh(this._liftGeo, this.armMats.lift);
      m.scale.set(0.62, h / this._liftGeo.userData.size.y, 0.62);
    } else {
      m = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.17, 1, 20), this.armMats.dark);
      m.scale.y = h; m.position.y = h / 2;
    }
    m.castShadow = true; m.receiveShadow = true;
    stand.add(m);
  }

  /** 셀 판정 지도 표시 on/off (기본 off — 팔 동작만 보고 싶을 때 화면을 어지럽히지 않게) */
  setCellsVisible(on) {
    this._cellsEnabled = !!on;
    if (!on) this.clearCells();
    else if (this._live && this._live.cells) this.setCells(this._live.cells, this._live.scene);
  }
  /* ── 작업영역 추종 모드 ────────────────────────────────────────────
     기록에서는 "지금 어느 셀을 작업 중인지(tcp)·진행률·시간·완료 셀" 만 쓰고, 로봇의 실제 움직임·배치는 콘솔 자체
     애니메이션(레인 훑기·레일 슬라이딩·접근/후퇴)이 맡는다. 셀 위치는 Isaac 차 bbox 상대좌표 → 콘솔 차 bbox 로 옮겨
     그 근처 레인(콘솔 차 표면 위)을 훑으므로 차체를 뚫지 않는다. */
  /** 상대 매핑 점을 콘솔 차 도장 표면(레인 점)에 스냅 — 스캔 차와 모델 형상 차이로 떠 보이는 것을 없앤다 */
  _snapToSurface(pt, r = 0.35) {
    const F = this._flat; if (!F || !F.length) return pt;
    let best = null, bd = r * r;
    for (let i = 0; i < F.length; i += 2) { const d = F[i].distanceToSquared(pt); if (d < bd) { bd = d; best = F[i]; } }
    return best ? best.clone() : pt;
  }
  _mapRel(pt) {
    const sc = this._live && this._live.scene; if (!sc || !sc.car_min || !this._model) return null;
    if (!this._waBox) {
      this._model.updateMatrixWorld(true);
      if (!this._paintBox) {   // 리프트 뒤 등: 도장 정점으로 기준 상자 재계산
        const pts = (this._model.userData && this._model.userData.paintPts) || []; const w = new THREE.Vector3();
        if (pts.length) { const pb = new THREE.Box3(); for (const q of pts) pb.expandByPoint(w.copy(q).applyMatrix4(this._model.matrixWorld)); this._paintBox = pb; }
      }
      this._waBox = (this._paintBox && !this._paintBox.isEmpty()) ? this._paintBox.clone() : new THREE.Box3().setFromObject(this._model);
    }
    const b = this._waBox, mn = sc.car_min, mx = sc.car_max;
    const u = (pt[0] - mn[0]) / Math.max(1e-6, mx[0] - mn[0]);   // Isaac x(가로) → 콘솔 x
    const w = 1 - (pt[1] - mn[1]) / Math.max(1e-6, mx[1] - mn[1]);   // Isaac y(길이, 앞 +) → 콘솔 길이축. 콘솔 Z4 는 앞이 −z 라 반전 (좌우는 그대로 맞음)
    const v = (pt[2] - mn[2]) / Math.max(1e-6, mx[2] - mn[2]);   // Isaac z(높이) → 콘솔 y
    const LONG = (this._axes && this._axes.LONG) || 'z', CROSS = LONG === 'z' ? 'x' : 'z';
    const out = new THREE.Vector3();
    out[CROSS] = b.min[CROSS] + u * (b.max[CROSS] - b.min[CROSS]);
    out[LONG] = b.min[LONG] + w * (b.max[LONG] - b.min[LONG]);
    out.y = b.min.y + v * (b.max.y - b.min.y);
    return out;
  }
  /** 셀(12 cm 격자) 하나를 빈틈 없이 덮는 스탬프 반경 — 콘솔 차/Isaac 차 길이 비율로 환산 */
  _waCellRadius() {
    const sc = this._live && this._live.scene; if (!sc || !this._waBox) return 0.11;
    const k = (this._waBox.max.z - this._waBox.min.z) / Math.max(1e-6, sc.car_max[1] - sc.car_min[1]);
    return 0.085 * k;
  }
  /** 콘솔 차 표면 레인 중 pt 에 가장 가까운 점 주변 ±0.16 m 를 셀의 작업 구간으로 준다 */
  _setWorkWindow(cell, pt) {
    if (!this._lanes || !this._lanes.length) return false;
    let best = null, bd = Infinity;
    for (let li = 0; li < this._lanes.length; li++) {
      const lane = this._lanes[li];
      for (let k = 0; k < lane.length; k += 2) { const d = lane[k].distanceToSquared(pt); if (d < bd) { bd = d; best = [li, k]; } }
    }
    if (!best) return false;
    const lane = this._lanes[best[0]], ns = this._normals[best[0]];
    let k0 = best[1], k1 = best[1], acc0 = 0, acc1 = 0;
    while (k0 > 0 && acc0 < 0.16) { acc0 += lane[k0].distanceTo(lane[k0 - 1]); k0--; }
    while (k1 < lane.length - 1 && acc1 < 0.16) { acc1 += lane[k1].distanceTo(lane[k1 + 1]); k1++; }
    if (k1 - k0 < 2) return false;
    const pts = [], nrm = [];
    for (let k = k0; k <= k1; k++) { pts.push(lane[k]); nrm.push(ns[k]); }
    const cum = new Float32Array(pts.length); let acc = 0;
    for (let i = 1; i < pts.length; i++) { acc += pts[i].distanceTo(pts[i - 1]); cum[i] = acc; }
    cell.userData.work = pts; cell.userData.workN = nrm; cell.userData.cum = cum;
    cell.userData.pathLen = Math.max(0.01, acc); cell.userData.s = 0; cell.userData.cursor = 0;
    return true;
  }
  _driveWorkArea(dt, t, p) {
    const feed = this._live; if (!feed) return;
    this._waActive = true;
    /* 진행률 모드(기본): 기록에서는 전체 진행률만 쓴다. 로봇마다 배정된 레인 경로(work)의 p 지점까지 훑는다.
       패드가 지나간 자리가 유광이 되므로 p=1 이면 차 전체가 닦여 있다. 설비는 작업점을 따라온다(_liftFollow). */
    if (!this._lanes || !this._lanes.length) return;
    const prog = Math.max(0, Math.min(1, Number(feed.progress) || 0));
    let jumped = false;
    for (const cell of this._cells) {
      if (!cell.userData.work || cell.userData.work.length < 2) continue;
      const len = cell.userData.pathLen || 0;
      /* 로봇별로 따로 간다: 기록의 로봇 진행률(자기 셀 몫 중 끝낸 비율)과 상태를 그대로 — 세 대가 한 진행률에 묶이지 않는다 */
      const rb = (feed.robots || []).find((r) => r.id === cell.userData.robotId) || null;
      const pi = rb && Number.isFinite(Number(rb.progress)) ? Math.max(0, Math.min(1, Number(rb.progress))) : prog;
      cell.userData.liveState = rb ? rb.state : null;
      const sTarget = pi * len;
      const cur = cell.userData.s || 0;
      const d = sTarget - cur;
      if (Math.abs(d) > 0.4) {                                      // 슬라이더 점프(앞/뒤): 즉시 그 지점으로
        cell.userData.s = sTarget; cell.userData.cursor = 0; jumped = true;
      } else {
        const maxStep = Math.max(0.02, 1.2 * dt);                   // 재생 중 미세 지연은 부드럽게
        cell.userData.s = Math.abs(d) > maxStep ? cur + Math.sign(d) * maxStep : sTarget;
      }
    }
    if (jumped || this._waNeedGloss) { this._waNeedGloss = false; this._rebuildGlossForProgress(p); }   // 점프·레인 재구성 뒤: 그 시점까지의 광택 재계산
    this._liftFollow = true;
    if (!this._waT0) this._waT0 = t;
    this._rateScale = Math.min(1, 0.15 + (t - this._waT0) / 2.5);   // 시작 2.5 s 동안 관절·설비 속도를 서서히 올린다 (첫 프레임에 팍 튀지 않게)
    this._animateLanes(dt, t, p, true);
    return;   // 광택은 패드가 실제로 지나간 자리만 (레인이 도장 면 전체를 덮으므로 100 % 에서 전부 닦인다)
    for (const cell of this._cells) {
      const rid = cell.userData.robotId;
      const r = (rid && feed.robots.find((x) => x.id === rid)) || null;
      if (!r || !r.tcp) continue;                                  // 이동 중(SLIDE)이면 직전 구간을 계속 훑는다
      let pt = this._mapRel(r.tcp); if (!pt) continue; pt = this._snapToSurface(pt);
      const last = cell.userData.waPt;
      if (!last || last.distanceTo(pt) > 0.06) {                    // 셀이 바뀌었다 → 새 작업 구간
        if (this._setWorkWindow(cell, pt)) { cell.userData.waPt = pt.clone(); this.stampPolish(pt, this._waCellRadius(), true, 0.6); }   // 작업 중인 셀: 팔이 있는 자리부터 광택
      }
      // 리프트 축 추종 — 팔만 뻗지 않고 설비가 셀 쪽으로 온다
      const tgt = cell.userData.waPt; if (!tgt) continue;
      const LONG = (this._axes && this._axes.LONG) || 'z';
      if (cell.userData.ceiling) {
        // 천장: 갠트리를 따라 길이축 이동 + 매달림 기둥을 늘였다 줄여 어깨를 셀 위 0.65 m 에
        const beamY = this._beamY || (cell.position.y + 1.0);
        const stepL = RAIL_SPEED * dt, stepY = 0.35 * dt;
        cell.position[LONG] += THREE.MathUtils.clamp(tgt[LONG] - cell.position[LONG], -stepL, stepL);
        const wantY = THREE.MathUtils.clamp(tgt.y + 0.65, (this._waBox ? this._waBox.max.y : tgt.y) + 0.3, beamY - 0.3);
        cell.position.y += THREE.MathUtils.clamp(wantY - cell.position.y, -stepY, stepY);
        if (this._hang && this._liftGeo) {
          this._hang.position.set(cell.position.x, beamY, cell.position.z);
          this._hang.scale.y = Math.max(0.05, beamY - cell.position.y) / this._liftGeo.userData.size.y;
        }
        cell.updateMatrixWorld(true);
      } else if (this._params.hasLift) {
        // 측면: 텔레스코픽 기둥으로 어깨를 셀 높이 근처(−0.15 m)에
        const root = cell.userData.armRoot;
        const wantY = THREE.MathUtils.clamp(tgt.y - 0.15, 0.55, 1.75);
        const stepY = 0.25 * dt;
        root.position.y += THREE.MathUtils.clamp(wantY - root.position.y, -stepY, stepY);
        this._setStandHeight(cell, root.position.y);
        cell.updateMatrixWorld(true);
      }
    }
    this._animateLanes(dt, t, p);                                   // 콘솔 자체 동작: 레일 슬라이딩·접근·훑기·광택
  }

  /** 진행률 모드에서 탐색(점프) 뒤 광택 마스크를 처음부터 다시: 로봇마다 경로의 s 지점까지 패드 반경으로 촘촘히 찍는다 */
  _rebuildGlossForProgress(p) {
    this.resetPolish();
    const r = (p.pad / 1000) / 2, step = Math.max(0.01, r * 0.7);
    for (const cell of this._cells) {
      const work = cell.userData.work, cum = cell.userData.cum; if (!work || work.length < 2) continue;
      const sEnd = cell.userData.s || 0;
      let next = 0;
      for (let k = 0; k < work.length && cum[k] <= sEnd; k++) {
        if (cum[k] < next) continue;
        // 레인 전환 구간(20 cm 이상 점프)은 표면 위를 지나지 않으므로 찍지 않는다
        if (k > 0 && cum[k] - cum[k - 1] > 0.20) { next = cum[k]; continue; }
        this.stampPolish(work[k], r); next = cum[k] + step;
      }
    }
  }

  /** 완료된 셀 전체를 광택 마스크에 찍는다(셀 12 cm → 반경 9 cm 원). 팔 동작과 무관하게 판정 완료 = 닦임. */
  stampCells(snapshot, scene) {
    if (this._liveWorkArea) return;                                 // 진행률 모드: 광택은 패드가 지나간 자리로만 (레인이 전 표면을 덮는다)
    const items = snapshot && Array.isArray(snapshot.items) ? snapshot.items : [];
    const xf = this._liveXf; if ((!xf && !this._liveWorkArea) || !this._polish) return;   // 변환이 아직 없으면 건너뜀(여기서 만들지 않는다 — 재귀 원인)
    const key = 'stamp:' + items.length;
    if (key === this._stampKey) return;
    this._stampKey = key;
    const p = new THREE.Vector3();
    // 작업영역 모드: 콘솔 차가 Isaac 차보다 크므로(약 1.35배) 스탬프 반경도 비례
    const rad = this._liveWorkArea ? this._waCellRadius() : 0.085;
    for (let i = this._stampedN || 0; i < items.length; i++) {
      const it = items[i]; if (!it || it[3] === 'not_reached') continue;
      if (this._liveWorkArea) { const m = this._mapRel([Number(it[0]), Number(it[1]), Number(it[2])]); if (!m) continue; p.copy(m); }
      else p.set(Number(it[0]), Number(it[1]), Number(it[2])).multiplyScalar(xf.s).applyMatrix4(xf.rot).add(xf.t);
      this.stampPolish(p, rad, true, 1.0);                          // 완료 셀: 면적 전체 100 %
    }
    this._stampedN = items.length;
  }
  setCells(snapshot, scene) {
    this._lastCells = snapshot; this._lastScene = scene;
    this.stampCells(snapshot, scene);
    if (!this._cellsEnabled) return;
    const items = snapshot && Array.isArray(snapshot.items) ? snapshot.items.filter((it) => it && it[3] && it[3] !== 'not_reached') : [];
    if (!this._liveXf && scene) this._buildLiveXform(scene);
    const xf = this._liveXf;
    if (!xf || !items.length) { this.clearCells(); return; }
    const key = items.length + ':' + items.reduce((a, it) => a + (it[3] === 'pass' ? 1 : it[3] === 'rework_candidate' ? 3 : 2), 0);
    if (key === this._cellsKey) return;                       // 바뀐 게 없으면 그대로
    if (this._liveWorkArea) {
      this._cellsKey = key; this.clearCells();
      const geo = new THREE.SphereGeometry(0.036, 10, 8), mat = new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0.05 });
      const mesh = new THREE.InstancedMesh(geo, mat, items.length), m4 = new THREE.Matrix4(), col = new THREE.Color();
      const C = { pass: 0x2e8b57, spot_repaint_review: 0xe69f00, rework_candidate: 0xd55e00 };
      for (let i = 0; i < items.length; i++) { const it = items[i]; let m = this._mapRel([Number(it[0]), Number(it[1]), Number(it[2])]); if (!m) continue; m = this._snapToSurface(m); m4.makeTranslation(m.x, m.y, m.z); mesh.setMatrixAt(i, m4); mesh.setColorAt(i, col.setHex(C[it[3]] || 0x888888)); }
      mesh.instanceMatrix.needsUpdate = true; if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      this.cellsLayer.add(mesh); this._cellsMesh = mesh; return;
    }
    this._cellsKey = key;
    this.clearCells();
    const geo = new THREE.SphereGeometry(0.032, 10, 8);
    const mat = new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0.05, vertexColors: false });
    const mesh = new THREE.InstancedMesh(geo, mat, items.length);
    const m4 = new THREE.Matrix4(), p = new THREE.Vector3(), col = new THREE.Color();
    const C = { pass: 0x2e8b57, spot_repaint_review: 0xe69f00, rework_candidate: 0xd55e00 };
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      p.set(Number(it[0]), Number(it[1]), Number(it[2])).multiplyScalar(xf.s).applyMatrix4(xf.rot).add(xf.t);
      m4.makeTranslation(p.x, p.y, p.z);
      mesh.setMatrixAt(i, m4);
      mesh.setColorAt(i, col.setHex(C[it[3]] || 0x888888));
    }
    mesh.instanceMatrix.needsUpdate = true; if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.castShadow = false; mesh.receiveShadow = false;
    this.cellsLayer.add(mesh);
    this._cellsMesh = mesh;
  }
  clearCells() {
    if (this._cellsMesh) { this.cellsLayer.remove(this._cellsMesh); this._cellsMesh.geometry.dispose(); this._cellsMesh.material.dispose(); this._cellsMesh = null; }
    this._cellsKey = null;
  }

  /** 접촉 품질 스냅샷 — 로봇별 {id, working, dist(m), angle(°), ok} (콘솔 공정 감시 패널이 5 Hz 로 읽는다) */
  getContact() { return this._cells.map((c) => c.userData.contactQ).filter(Boolean); }

  /** 기록 재생기 (지연 생성) — 콘솔이 v.replay.load(id) / play() / pause() / seek(t) / setSpeed(x) 로 쓴다 */
  get replay() { return this._replay || (this._replay = new ReplayPlayer(this)); }

  /** 시뮬 피드(/api/monitor 의 feed) 를 넣으면 팔이 Isaac 관절을 그대로 따른다. null 이면 해제. */
  setLive(feed, snap = false) {
    const had = !!this._live;
    this._live = feed && feed.robots && feed.robots.some((r) => Array.isArray(r.q) || r.tcp) ? feed : null;
    this._liveWorkArea = !!(this._live && typeof this._live.kind === 'string' && this._live.kind.indexOf('result_replay') === 0);
    if (this._liveWorkArea && !had) { this.resetPolish(); this._waBox = null; for (const c of this._cells) { c.userData.s = 0; c.userData.cursor = 0; } }
    if (this._live && !had && !this._liveWorkArea && this._vehicle !== 'scan') {   // 실제 Isaac 기록: 관절 추종 → Isaac 과 같은 스캔 차체
      this._vehicleBefore = this._vehicle;
      this.setVehicle('scan').then(() => { this._liveXf = null; if (this._live && this._live.scene) this._buildLiveXform(this._live.scene); }).catch(() => {});
    }
    this._liveSnap = !!snap;
    if (this._live && !this._liveWorkArea && this._live.scene && !this._liveXf) this._buildLiveXform(this._live.scene);
    if (this._live && this._live.cells && Array.isArray(this._live.cells.items)) this.setCells(this._live.cells, this._live.scene);   // 셀 스냅샷: 광택 스탬프(항상) + 구슬 표시(옵션)
    if (this._live) { this.raster.visible = false; this.head.visible = false; }   // 시뮬을 따를 땐 데모 경로선은 의미가 없다
    if (had && !this._live) {
      this._waT0 = null; this._rateScale = 1;
      this.raster.visible = true;
      this.clearCells();
      if (this._waActive) { this._waActive = false; this._liftFollow = false; for (const c of this._cells) { c.userData.waPt = null; } this._cellSig = null; this.layoutCells(); this.resetPolish(); }
      this._liveScene = null;
      if (this._vehicleBefore && this._vehicleBefore !== 'scan') { const vb = this._vehicleBefore; this._vehicleBefore = null; this.setVehicle(vb).catch(() => {}); }
      if (this._liveLift0 !== undefined) { this._params.carLift = this._liveLift0; this._liveLift0 = undefined; this._applyCarLift(); }
      if (this._modelScale0 && this._model) {        // 차체 크기·배치 원복
        this._model.scale.copy(this._modelScale0); this._model.updateMatrixWorld(true);
        this._cellSig = null; this.layoutCells();
        try { this._buildFields(); this.initPolish(); } catch (e) { /* 유지 */ }
      }
      // 해제: 받침대 다시 보이고 배치 자세로
      for (const cell of this._cells) {
        if (cell.userData.stand) cell.userData.stand.visible = true;
        cell.userData.liveQ = null;
      }
      this._liveXf = null;
    }
  }

  /* Isaac 월드 → 콘솔 월드. 차 점군 bbox(feed.scene) 와 콘솔 차체 bbox 를 맞춘다(길이축 스케일 + 중심 정렬). */
  _buildLiveXform(scene) {
    if (!this._model || !scene || !scene.car_min || !scene.car_max) return;
    if (this._buildingXf) return;                      // 재진입 금지 (_applyCarLift → setCells → … → 여기로 되돌아오던 무한 재귀)
    this._buildingXf = true;
    try { this._buildLiveXformInner(scene); } finally { this._buildingXf = false; }
  }
  _buildLiveXformInner(scene) {
    this._liveScene = scene;
    this._model.updateMatrixWorld(true);
    const b = new THREE.Box3().setFromObject(this._model);
    const mid = b.getCenter(new THREE.Vector3()), size = b.getSize(new THREE.Vector3());
    const LONG = (this._axes && this._axes.LONG) || 'z';
    const mn = new THREE.Vector3().fromArray(scene.car_min), mx = new THREE.Vector3().fromArray(scene.car_max);
    const isaacLen = Math.max(1e-3, mx.y - mn.y);
    /* 로봇은 실물 크기(미터)로 움직이므로 좌표는 스케일 1 로 옮기고, 대신 콘솔 차체를 Isaac 차(스캔 모델, 길이 ≈3.0 m) 크기로 줄인다.
       그래야 팔 도달거리·패드 위치가 Isaac 과 같은 비율이 된다. 해제 시 원래 크기로 돌린다. */
    if (!this._modelScale0) this._modelScale0 = this._model.scale.clone();
    const carScale = THREE.MathUtils.clamp(isaacLen / size[LONG], 0.3, 3.0);
    this._model.scale.copy(this._modelScale0).multiplyScalar(carScale);
    /* Isaac 에서는 차가 리프트 위(바닥 z = car_min.z ≈ 1.0 m)에 떠 있다. 콘솔도 차량 리프트로 같은 높이에 올리고
       바닥↔바닥(z=0 ↔ y=0)으로 맞춘다 — 그래야 갠트리·레일·로봇 높이가 절대값 그대로 맞는다. */
    if (this._liveLift0 === undefined) this._liveLift0 = this._params.carLift || 0;
    this._params.carLift = Math.max(0, mn.z);
    this._applyCarLift();
    this._model.updateMatrixWorld(true);
    const b2 = new THREE.Box3().setFromObject(this._model);
    const mid2 = b2.getCenter(new THREE.Vector3());
    const s = 1.0;
    const rot = new THREE.Matrix4().setFromMatrix3(_LIVE_M);
    if (LIVE_LONG_FLIP) rot.premultiply(new THREE.Matrix4().makeRotationY(Math.PI));
    const cIsaac = mn.clone().add(mx).multiplyScalar(0.5).applyMatrix4(rot);
    // 높이는 바닥끼리(Isaac z=0 ↔ 콘솔 y=0); 콘솔 차 바닥이 mn.z 에 오도록 리프트했으므로 잔차만 보정
    const t = new THREE.Vector3(mid2.x - cIsaac.x, b2.min.y - mn.z, mid2.z - cIsaac.z);
    this._liveXf = { s, rot, t, q: new THREE.Quaternion().setFromRotationMatrix(rot), carScale };
    // 줄어든·올라간 차체에 맞춰 레일·갠트리·연마 텍스처 좌표를 다시 잡는다 (initPolish 가 마스크 격자·유니폼을 새 필드로 갱신)
    this._cellSig = null; this.layoutCells();
    try { this._buildFields(); this.initPolish(); } catch (e) { console.warn('필드 재구성 실패', e); }
  }

  _driveLive(dt) {
    const feed = this._live; if (!feed) return;
    const xf = this._liveXf;
    const robots = feed.robots;
    const _p = new THREE.Vector3(), _qi = new THREE.Quaternion(), _v = new THREE.Vector3();
    for (let ci = 0; ci < this._cells.length; ci++) {
      const cell = this._cells[ci];
      const rid = cell.userData.robotId;
      const r = (rid && robots.find((x) => x.id === rid)) || robots[ci]; if (!r || (!Array.isArray(r.q) && !r.tcp)) continue;
      // 관절: 오프셋·부호 보정 후 속도 제한으로 따라붙기 (결과 리플레이는 아래 IK 가 대신한다)
      const useIK = r.tcp && (!Array.isArray(r.q) || feed.kind === 'result_replay');
      if (!useIK && Array.isArray(r.q)) {
        const tgt = cell.userData.liveQ || (cell.userData.liveQ = cell.userData.q.slice());
        for (let j = 0; j < 6; j++) tgt[j] = LIVE_Q_SIGN[j] * ((Number(r.q[j]) || 0) - LIVE_Q_OFFSET[j]);
        const q = cell.userData.q, step = this._liveSnap ? 1e9 : LIVE_JOINT_RATE * dt;
        for (let j = 0; j < 6; j++) q[j] += THREE.MathUtils.clamp(tgt[j] - q[j], -step, step);
        setCellQ(cell, q);
      }
      // 베이스 자세: 피드에 있으면 Isaac 위치·자세를 그대로(레일 이동·리프트 포함).
      // 셀 원점은 바닥(또는 갠트리 보)에 두고 팔 뿌리(armRoot)를 베이스 높이로 올린다 → 기둥이 바닥~베이스를 잇는다.
      if (r.base && r.base.pos && xf) {
        _p.fromArray(r.base.pos).multiplyScalar(xf.s).applyMatrix4(xf.rot).add(xf.t);
        if (r.base.quat) {
          // 거울상 변환: 축은 M·n, 각도는 반전 → (w, −M·v)
          _v.set(r.base.quat[1], r.base.quat[2], r.base.quat[3]).applyMatrix3(_LIVE_M).negate();
          _qi.set(_v.x, _v.y, _v.z, r.base.quat[0]);
          if (LIVE_LONG_FLIP) _qi.premultiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI));
        } else _qi.identity();
        const root = cell.userData.armRoot;
        if (cell.userData.ceiling) {
          const beamY = this._beamY || (_p.y + 1.0);
          cell.position.set(_p.x, beamY, _p.z); cell.quaternion.identity();
          root.position.set(0, _p.y - beamY, 0); root.quaternion.copy(_qi);
          if (this._hang && this._liftGeo) {           // 매달린 텔레스코픽 기둥: 보에서 베이스까지
            this._hang.position.set(_p.x, beamY, _p.z);
            this._hang.scale.y = Math.max(0.05, beamY - _p.y) / this._liftGeo.userData.size.y;
          }
          if (cell.userData.stand) cell.userData.stand.visible = false;
        } else {
          cell.position.set(_p.x, 0, _p.z); cell.quaternion.identity();
          root.position.set(0, _p.y, 0); root.quaternion.copy(_qi);
          this._setStandHeight(cell, _p.y);            // 측면 텔레리프트 기둥: 바닥에서 베이스까지
          if (cell.userData.stand) cell.userData.stand.visible = true;
          const rail = this._rails && this._rails[cell.userData.robotId];   // 레일도 Isaac 의 rail_x 자리로
          if (rail) { const CROSS = (this._axes && this._axes.CROSS) || 'x'; rail.position[CROSS] = _p[CROSS]; }
        }
        cell.updateMatrixWorld(true);
      }
      // 결과 리플레이(관절 없이 셀 목표점만 있는 프레임): 콘솔 IK 로 패드를 표면에 붙인다 — 관통 없이 자연스러운 접근
      if (r.tcp && xf && (!Array.isArray(r.q) || feed.kind === 'result_replay')) {
        const pad = new THREE.Vector3().fromArray(r.tcp).multiplyScalar(xf.s).applyMatrix4(xf.rot).add(xf.t);
        const nrm = new THREE.Vector3().fromArray(r.normal || [0, 0, 1]).applyMatrix3(_LIVE_M);
        if (LIVE_LONG_FLIP) nrm.applyAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI);
        nrm.normalize();
        let back = pad.clone().addScaledVector(nrm, 0.2);
        // 이전 자세를 기억해 두고 풀어서, 셀이 바뀔 때도 관절이 실물 속도(JOINT_RATE)로만 움직이게 — 순간이동 없이
        const prev = cell.userData.ikPrev || (cell.userData.ikPrev = cell.userData.q.slice());
        for (let j = 0; j < 6; j++) prev[j] = cell.userData.q[j];
        // 시드: 피드에 실린 실제 Isaac 폴리싱 자세(q) 쪽으로 20 % 당긴 뒤 푼다 → 팔꿈치가 뒤집히는 기괴한 해를 피한다
        if (Array.isArray(r.q)) {
          const qs = cell.userData.q;
          for (let j = 0; j < 6; j++) { const seed = LIVE_Q_SIGN[j] * ((Number(r.q[j]) || 0) - LIVE_Q_OFFSET[j]); qs[j] += (seed - qs[j]) * 0.2; }
          setCellQ(cell, qs);
        }
        solveIK(cell, pad, back, 12);
        // 팔꿈치(관절 3)·손목(관절 5)이 차체 상자 안이면 목표를 법선 바깥으로 더 세워 다시 푼다 (관통 방지)
        if (this._model) {
          const bb = this._carBox || (this._carBox = new THREE.Box3());
          bb.setFromObject(this._model).expandByScalar(-0.03);
          const jp = new THREE.Vector3();
          let inside = false;
          for (const ji of [2, 3, 4]) { cell.userData.joints[ji].getWorldPosition(jp); if (bb.containsPoint(jp)) { inside = true; break; } }
          if (inside) { back = pad.clone().addScaledVector(nrm, 0.45); solveIK(cell, pad, back, 16); }
        }
        const maxStep = JOINT_RATE * dt * (feed.state === 'SLIDE' ? 1.0 : 1.4);
        let clamped = false;
        for (let j = 0; j < 6; j++) {
          const d = cell.userData.q[j] - prev[j];
          if (Math.abs(d) > maxStep) { prev[j] += Math.sign(d) * maxStep; clamped = true; } else prev[j] = cell.userData.q[j];
        }
        if (clamped) setCellQ(cell, prev);
      }
      // 패드 자전·연마 자국 — 접촉 중(POLISH)일 때만. 자국은 패드가 3 mm 이상 움직였을 때만 찍는다
      // (매 프레임 찍으면 텍스처 재업로드가 프레임마다 일어난다).
      const rpm = this._params.rpm || 3000;
      cell.userData.padDisc.rotation.z += (rpm / 60) * Math.PI * 2 * dt;
      if (r.state === 'POLISH' && (Number(r.force) || 0) > 0.5) {
        cell.userData.padAnchor.getWorldPosition(_p);
        const last = cell.userData.liveStamp || (cell.userData.liveStamp = new THREE.Vector3(1e9, 1e9, 1e9));
        if (last.distanceToSquared(_p) > 9e-6) {
          this.stampPolish(_p, (this._params.pad / 1000) / 2);
          last.copy(_p);
        }
      }
    }
  }

  setParams(p) {
    const prev = this._params;
    const spacingChanged = p.pad !== prev.pad || p.overlap !== prev.overlap;
    this._params = { ...prev, ...p };
    const f = THREE.MathUtils.clamp((this._params.force - 3) / 9, 0, 1);
    this.raster.material.opacity = 0.34 + f * 0.5;
    this.raster.material.color.setHSL(0.543, 0.40 + f * 0.22, 0.42 + f * 0.16);
    /* 관절 추종 모드(실제 Isaac 기록)만 리프트를 시뮬 값으로 고정. 그 외(대기·데모·진행률 재생)는 차를 올리면
       표면 좌표가 통째로 바뀌므로 높이맵·레인·마스크·배치를 즉시 다시 굽는다 — 차는 떠 있는데 레인만 바닥에 남는 일이 없게 */
    if (this._live && !this._liveWorkArea && p.carLift !== undefined) { this._params.carLift = prev.carLift; }
    else if (p.carLift !== undefined && p.carLift !== prev.carLift) {
      this._applyCarLift();
      this._buildFields();
      this.initPolish();                // 차체가 움직이면 마스크 기준 상자도 다시
      this.rebuildPath();
      this.layoutCells();
      if (this._liveWorkArea) this._waNeedGloss = true;   // 레인이 다시 생기면(비동기) 진행률까지의 광택도 재계산
    } else if (spacingChanged) {
      this.rebuildPath();
    }
    if (p.running === true && prev.running === false) {
      this.resetPolish();
      /* 대기 중에 진행량이 남아 있으면 시작하자마자 중간부터 튄다.
         셀마다 조금씩 어긋나게 두는 건 세 대가 같은 자리를 훑지 않게 하려는 것이다 */
      this._cells.forEach((cell, ci) => {
        cell.userData.s = ci * (cell.userData.pathLen || 0) * 0.31;
        cell.userData.cursor = 0;
      });
    }
    if (['robotCount', 'hasRail', 'hasLift'].some((k) => p[k] !== undefined && p[k] !== prev[k])) {
      this.layoutCells();
    }
  }

  rebuildPath() {
    // coalesce bursts of slider input into a single rebuild per frame
    if (this._pathQueued) return;
    this._pathQueued = true;
    requestAnimationFrame(() => {
      this._pathQueued = false;
      if (!this._field) return;
      const { pad, overlap } = this._params;
      const spacing = Math.max(0.03, (pad / 1000) * (1 - overlap / 100));

      // 위에서 한 장 + 옆에서 두 장. 옆면 레인이 없으면 도어에는 경로 자체가 없다.
      const pts = [], lanes = [], normals = [];
      for (const f of [this._field].concat(this._sideFields || [], this._endFields || [])) {
        if (!f) continue;
        const r = tracePath(f, spacing);
        for (let k = 0; k < r.lanes.length; k++) {
          // 도장 면 근처의 점만 남기고(유리·그릴·휠 제외), 끊긴 곳에서 레인을 나눈다
          const L = r.lanes[k], N = r.normals[k];
          let cur = [], curN = [];
          for (let i = 0; i < L.length; i++) {
            if (this._nearPaint(L[i])) { cur.push(L[i]); curN.push(N[i]); }
            else if (cur.length) { if (cur.length >= 3) { lanes.push(cur); normals.push(curN); } cur = []; curN = []; }
          }
          if (cur.length >= 3) { lanes.push(cur); normals.push(curN); }
        }
      }
      for (const L of lanes) for (const q of L) pts.push(q);
      this.raster.geometry.dispose();
      this.raster.geometry = new THREE.BufferGeometry().setFromPoints(pts);
      this._lanes = lanes;
      this._flat = lanes.flat();
      // 법선은 하이트필드 기울기에서 나온다 — 패드가 곡면에 눕는 각도가 이것이다
      this._normals = normals;
      this.head.visible = this._flat.length > 0;
      this.assignWork();
      if (this._liveWorkArea) this._waNeedGloss = true;   // 레인이 바뀌었다 — 다음 프레임에 진행률까지 광택 재계산
    });
  }

  /* 공정 모니터링 패널이 읽는 값. 화면에 보이는 것과 같은 수를 돌려준다 —
     패널에만 있는 숫자를 따로 만들면 둘이 어긋난다. */
  getStats() {
    const cells = this._cells.map((c) => {
      const len = c.userData.pathLen || 0;
      return {
        lap: len > 0 ? ((c.userData.s || 0) / len) : 0,   // 담당 구역 진행 비율
        pts: (c.userData.work || []).length,              // 맡은 작업점 수
        onRail: !!c.userData.onRail,
      };
    });
    return {
      cells,
      lanes: (this._lanes || []).length,
      points: (this._flat || []).length,
      /* 팔이 실제로 맡은 점 수. 도달거리 밖은 아무 셀에도 배정되지 않는다 —
         커버리지가 100% 에 못 가는 이유가 여기 있고, 그건 숨길 값이 아니다 */
      assigned: cells.reduce((n, c) => n + c.pts, 0),
      // 실제로 닦인 면적 비율. 시간 진행률로 대신하면 3D 와 숫자가 어긋난다
      polished: this._polishCoverage(),
    };
  }

  /** 폴리싱 마스크에서 실제로 찍힌 비율. 차체 실루엣이 아니라 필드 기준이다. */
  _polishCoverage() {
    const P = this._polish;
    if (!P) return null;
    const d = P.top.data;
    let n = 0;
    for (let i = 0; i < d.length; i++) if (d[i] > 8) n++;
    return n / d.length;
  }

  setView(v) {
    const P = {
      front: [new THREE.Vector3(0.1, 1.5, 7.4), new THREE.Vector3(0, 0.7, 0)],
      top: [new THREE.Vector3(0.1, 8.2, 0.6), new THREE.Vector3(0, 0.4, 0)],
      side: [new THREE.Vector3(8.4, 1.8, 0.2), new THREE.Vector3(0, 0.75, 0)],
      free: [new THREE.Vector3(5.6, 2.3, 6.2), new THREE.Vector3(0, 0.72, 0)],
    }[v];
    if (!P) return;
    this._camGoal = { pos: P[0], look: P[1] };
  }

  _tick(now) {
    this._raf = requestAnimationFrame(this._tick.bind(this));
    try { this._frame(now); }
    catch (err) {
      if (!this._tickErr) { this._tickErr = 1; console.error('틱 실패:', err); }
      this.renderer.render(this.scene, this.camera);
    }
  }

  /** 콘솔 자체 공정 애니메이션 — 셀마다 배정된 레인(work)을 이송속도로 훑는다: 레일 슬라이딩·접근/후퇴·IK·패드 회전·광택 스탬프.
      데모 모드와 '작업영역 추종' 재생 모드가 함께 쓴다. */
  _animateLanes(dt, t, p, holdS = false) {
    if (this._lanes && this._lanes.length && this._cells.length) {
      // 실제 이송속도(m/s)에 데모 배속을 곱한다. 0.03 m/s 그대로면
      // 한 패스에 2분이 넘어 심사에서 아무 일도 안 일어나 보인다.
      const speed = p.feed * DEMO_SPEEDUP;
      const nCell = this._cells.length;
      let lead = null;

      for (let ci = 0; ci < nCell; ci++) {
        const cell = this._cells[ci];
        const work = cell.userData.work;
        if (!work || work.length < 2) continue;

        /* 자기 구역을 이송속도로 훑는다. 진행량은 비율이 아니라 미터다 —
           작업점이 몇 개든 패드가 실제로 움직이는 속도가 같아야 팔이 따라온다. */
        const cum = cell.userData.cum, len = cell.userData.pathLen;
        let s;
        if (holdS) {                                   // 진행률 모드: s 는 기록의 % 로 정해져 있다 (끝에서 멈춤)
          s = Math.min(len - 1e-4, Math.max(0, cell.userData.s || 0));
        } else {
          s = (cell.userData.s || (ci * len * 0.31)) + speed * dt;
          if (s >= len) s -= len * Math.floor(s / len);
        }
        cell.userData.s = s;
        // 이전 위치에서 이어 찾는다(대부분 한두 칸)
        let k = cell.userData.cursor || 0;
        if (cum[k] > s) k = 0;
        while (k < work.length - 1 && cum[k + 1] <= s) k++;
        cell.userData.cursor = k;
        if (!work[k]) continue;

        /* 표본과 표본 사이를 보간한다. 웨이포인트에 그대로 스냅하면 목표가
           한 칸씩 튀고 팔이 그 튐을 그대로 따라 한다 — 버벅임의 정체다. */
        const k1 = Math.min(k + 1, work.length - 1);
        const seg = cum[k1] - cum[k];
        const u = seg > 1e-6 ? THREE.MathUtils.clamp((s - cum[k]) / seg, 0, 1) : 0;
        const pt = _tgtP.copy(work[k]).lerp(work[k1], u);
        const nrm = _tgtN.copy(cell.userData.workN[k]).lerp(cell.userData.workN[k1], u).normalize();

        /* 레인이 바뀌는 구간(20 cm 이상 건너뜀)은 표면을 긁으며 가지 않는다.
           실제 공정처럼 법선 방향으로 들었다가 내려놓는다. 이걸 안 하면
           패드가 도장면을 뚫고 직선으로 지나가면서 지나지도 않은 자리를 연마한다. */
        let hop = seg > 0.20 ? Math.sin(Math.PI * u) * Math.min(0.20, seg * 0.26) : 0;
        const st = cell.userData.liveState;
        if (holdS && st && st !== 'POLISH') hop = Math.max(hop, cell.userData.ceiling ? 0.35 : 0.12);   // 이동 중: 천장은 차 위 35 cm, 측면은 12 cm 들고 따라간다
        if (seg > 0.5) hop = Math.max(hop, cell.userData.ceiling ? 0.35 : 0.2);                         // 먼 레인 전환(앞↔뒤)은 높게 넘어간다 — 유리·지붕 관통 금지
        /* 들어올림은 지수 스무딩으로 — 상태가 바뀌어도 팔이 부드럽게 떠오르고 내려앉는다 */
        const hs = cell.userData.hopCur == null ? hop
          : cell.userData.hopCur + (hop - cell.userData.hopCur) * (1 - Math.exp(-dt * 5));
        cell.userData.hopCur = hs;
        if (hs > 0.0005) pt.addScaledVector(nrm, hs);
        const contact = hs < 0.004;
        if (ci === 0) lead = _leadP.copy(pt);

        /* 설비가 작업점을 따라온다(진짜 공정처럼): 천장 로봇은 갠트리를 따라 이동하며 매달림 기둥을 신축해
           어깨를 작업점 위 0.65 m 에, 측면 로봇은 텔레리프트로 어깨를 작업점 높이 근처에 둔다. */
        if (this._liftFollow) {
          const LONG2 = (this._axes && this._axes.LONG) || 'z';
          if (cell.userData.ceiling) {
            const beamY = this._beamY || (cell.position.y + 1.0);
            const stepL = RAIL_SPEED * dt, stepY = 0.35 * dt;
            cell.position[LONG2] += THREE.MathUtils.clamp(pt[LONG2] - cell.position[LONG2], -stepL, stepL);
            const wantY = THREE.MathUtils.clamp(pt.y + 0.65, pt.y + 0.35, beamY - 0.3);
            cell.position.y += THREE.MathUtils.clamp(wantY - cell.position.y, -stepY, stepY);
            if (this._hang && this._liftGeo) {
              this._hang.position.set(cell.position.x, beamY, cell.position.z);
              this._hang.scale.y = Math.max(0.05, beamY - cell.position.y) / this._liftGeo.userData.size.y;
            }
            cell.updateMatrixWorld(true);
          } else if (p.hasLift) {
            const root = cell.userData.armRoot;
            const wantY = THREE.MathUtils.clamp(pt.y - 0.15, 0.55, 1.75);
            const stepY = 0.25 * dt;
            root.position.y += THREE.MathUtils.clamp(wantY - root.position.y, -stepY, stepY);
            this._setStandHeight(cell, root.position.y);
            cell.updateMatrixWorld(true);
          }
        }

        // 레일 위 셀은 목표를 따라 길이 방향으로 미끄러진다
        if (cell.userData.onRail) {
          const LONG = (this._axes && this._axes.LONG) || 'z';
          const [a0, a1] = cell.userData.span;
          const goal = THREE.MathUtils.clamp(pt[LONG], a0, a1);
          const step = RAIL_SPEED * dt;
          cell.position[LONG] += THREE.MathUtils.clamp(goal - cell.position[LONG], -step, step);
          cell.updateMatrixWorld(true);
        }

        // 패드 접촉면 = 표면점, 툴 축은 법선 반대 방향.
        // solveIK 는 월드 좌표로 푼다 — 여기서 로컬로 바꾸면 안 된다.
        // 경로선은 z-fighting 을 피하려고 도장면에서 13 mm 띄워 그린다.
        // 패드는 그 선이 아니라 도장면을 짚어야 하므로 되돌려 겨눈다.
        _ikPad.copy(pt).addScaledVector(nrm, -PATH_LIFT + 0.002);   // 표면에서 2 mm 띄운다(패드가 파묻혀 보이지 않게)
        _ikBack.copy(_ikPad).addScaledVector(nrm, 0.18);              // 손목을 법선 쪽으로 더 세워 팔이 차체 위를 지나가게
        if (contact) {   // 작업 중 손목이 살짝 흔들린다(±1.2 cm, 1.3 Hz) — 진짜 폴리싱처럼 팔에 움직임이 보이게
          const side = new THREE.Vector3(nrm.z, 0, -nrm.x); if (side.lengthSq() < 1e-6) side.set(1, 0, 0); side.normalize();
          _ikBack.addScaledVector(side, 0.012 * Math.sin(t * 2 * Math.PI * 1.3 + ci * 2.1));
        }

        // 작업 지점 빛: 표면 글로우(법선 정렬) + 손목→표면 빔. 접촉 중일 때만, 숨쉬듯 맥동
        {
          // 접촉 품질 — 패드 접촉면(앵커)과 표면 작업점의 거리, 패드 법선(앵커 −Z)과 표면 법선의 각도
          const aw = cell.userData.padAnchor.getWorldPosition(new THREE.Vector3());
          const an = new THREE.Vector3(0, 0, -1).applyQuaternion(cell.userData.padAnchor.getWorldQuaternion(new THREE.Quaternion())).normalize();
          const dist = aw.distanceTo(_ikPad), ang = THREE.MathUtils.radToDeg(Math.acos(THREE.MathUtils.clamp(an.dot(nrm), -1, 1)));
          cell.userData.contactQ = { id: cell.userData.robotId || ('R' + (ci + 1)), working: contact, dist, angle: ang, ok: !contact || (dist < 0.012 && ang < 12) };
          const spot = cell.userData.spot, beam = cell.userData.beam;
          if (spot && beam) {
            if (contact) {
              spot.visible = true; beam.visible = true;
              spot.position.copy(_ikPad).addScaledVector(nrm, 0.012);
              spot.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), nrm);
              spot.material.opacity = 0.3 + 0.18 * (0.5 + 0.5 * Math.sin(t * 6 + ci));
              const wrist = cell.userData.joints[5].getWorldPosition(new THREE.Vector3());
              const dir = new THREE.Vector3().subVectors(_ikPad, wrist); const len = Math.max(0.01, dir.length()); dir.normalize();
              beam.position.copy(wrist).addScaledVector(dir, len / 2);
              beam.scale.set(1, len, 1);
              beam.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
            } else { spot.visible = false; beam.visible = false; }
          }
        }

        // 이번 프레임 시작 자세를 기억해 두고 푼다
        const q0 = cell.userData.qPrev || (cell.userData.qPrev = cell.userData.q.slice());
        for (let jj = 0; jj < 6; jj++) q0[jj] = cell.userData.q[jj];
        solveIK(cell, _ikPad, _ikBack, 8);
        // 관절이 차체 안으로 들어갔으면 손목을 더 세워(0.35 → 0.5 m) 다시 푼다 — 관통 방지
        if (this._armInsideCar(cell)) {
          _ikBack.copy(_ikPad).addScaledVector(nrm, 0.35); solveIK(cell, _ikPad, _ikBack, 8);
          if (this._armInsideCar(cell)) { _ikBack.copy(_ikPad).addScaledVector(nrm, 0.5); solveIK(cell, _ikPad, _ikBack, 8); }
        }

        // 관절 가감속 — 목표에 지수적으로 접근(가까울수록 감속)하되 각속도 상한을 지킨다.
        // 등속 클램프는 '로봇이 뚝뚝 끊기는' 느낌을 준다; IK 해의 프레임 간 미세 떨림도 이 필터가 흡수한다.
        const maxStep = JOINT_RATE * dt * (this._rateScale || 1);
        const ease = 1 - Math.exp(-dt * 9);              // 시정수 ~110 ms
        let over = false;
        for (let jj = 0; jj < 6; jj++) {
          let d = (cell.userData.q[jj] - q0[jj]) * ease;
          if (Math.abs(d) > maxStep) d = Math.sign(d) * maxStep;
          if (Math.abs(cell.userData.q[jj] - (q0[jj] + d)) > 1e-5) over = true;
          q0[jj] += d;
        }
        if (over) setCellQ(cell, q0);

        // 패드 자전 + 듀얼액션 궤도(4 mm, 5 Hz) — 공정 중일 때만. 어느 배속에서도 '작업 중' 이 보인다
        const rpm = p.rpm || 3000;
        cell.userData.padDisc.rotation.z += (rpm / 60) * Math.PI * 2 * dt;
        const orb = contact ? 0.001 : 0.0, ph = t * 2 * Math.PI * 5;   // 듀얼액션 궤도 1 mm
        cell.userData.padDisc.position.set(orb * Math.cos(ph), orb * Math.sin(ph), 0);

        // 지나간 자리를 무광에서 유광으로 — 빛이 닿는 표면 작업점(패드가 조금 떠도 광택은 정확히 그 자리)
        if (contact) this.stampPolish(_ikPad, (p.pad / 1000) / 2);
      }

      this.head.visible = false;   // 작업점 구슬 대신 빔·글로우가 보여준다
    }

  }

  _frame(now) {
    const t = (now - this._t0) / 1000;
    const p = this._params;

    const dt = Math.min(0.05, (now - (this._last || now)) / 1000);
    this._last = now;

    if (this._camGoal) {
      const g = this._camGoal;
      // 프레임 수와 무관하게 같은 속도로 붙는다 — 고정 계수는 120 Hz 에서 두 배 빠르다
      const a = 1 - Math.pow(0.91, dt * 60);
      this.camera.position.lerp(g.pos, a);
      if (this._controls) {
        this._controls.target.lerp(g.look, a);
        if (this.camera.position.distanceTo(g.pos) < 0.02) this._camGoal = null;
      }
    }
    if (this._controls) this._controls.update();

    /* 팔마다 자기 레인을 맡아 이송속도로 훑는다. 패드는 표면점에 닿고
       법선 반대로 눌린다 — 위치와 자세를 IK 로 동시에 푼다. */
    /* 공정 시작 전에는 로봇이 멈춰 있어야 한다. 이 화면은 환경을 구성하는
       화면이고, 팔이 도는 것은 'RL 공정 시작' 이후의 일이다.
       대수를 바꾸면 팔이 늘고 줄되, 늘어난 팔도 대기 자세로 서 있는다. */
    /* 시뮬 피드/기록을 따르는 중이면 공정 실행 여부와 무관하게 팔·베이스를 피드대로 구동한다
       (기록 재생은 running=false 상태로 돈다 — 여기서 먼저 잡지 않으면 아래 대기 자세 복귀가 삼킨다) */
    if (this._live) {
      if (this._liveWorkArea) this._driveWorkArea(dt, t, p);
      else { this._driveLive(dt); this.head.visible = false; }
      this.renderer.render(this.scene, this.camera);
      return;
    }

    if (!p.running) {
      const rate = JOINT_RATE * dt * 0.5;      // 대기 복귀는 공정보다 느리게
      for (const cell of this._cells) {
        const home = cell.userData.qHome;
        if (!home) continue;
        const q = cell.userData.q;
        let moved = false;
        for (let jj = 0; jj < 6; jj++) {
          const d = home[jj] - q[jj];
          if (Math.abs(d) < 1e-4) continue;
          q[jj] += THREE.MathUtils.clamp(d, -rate, rate);
          moved = true;
        }
        if (moved) setCellQ(cell, q);
        if (cell.userData.padDisc) cell.userData.padDisc.rotation.z = 0;
        if (cell.userData.spot) { cell.userData.spot.visible = false; cell.userData.beam.visible = false; }
        cell.userData.qPrev = null;
      }
      this.head.visible = false;              // 작업점 표시도 공정 중에만
      this.renderer.render(this.scene, this.camera);
      return;
    }

    this._animateLanes(dt, t, p);
    this.renderer.render(this.scene, this.camera);
  }
}

/* ── 기록 재생기 ─────────────────────────────────────────────────────
   서버(/api/runs/:id/chunks)에서 gzip 청크를 미리 받아 두고, 재생 시계에 맞춰 이웃 프레임을 보간해
   viewport.setLive(frame, true) 로 넣는다. 네트워크·시뮬 속도와 무관하게 60 fps 로 매끈하다.
   실시간(기록 중) 런은 끝(t_sim_end)에서 LIVE_LAG 초 뒤를 따라간다 → 지연 재생. */
const REPLAY_PREFETCH_S = 30;   // 앞으로 미리 받아 둘 구간
const REPLAY_LIVE_LAG_S = 3.0;  // 기록 중 런을 따라갈 때의 지연
const REPLAY_KEEP_BACK_S = 60;  // 지나간 프레임은 이만큼만 남기고 버린다 — 수 시간짜리 기록도 메모리 일정

async function gunzipJson(b64) {
  const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const ds = new DecompressionStream('gzip');
  const w = ds.writable.getWriter(); w.write(bin); w.close();
  const txt = await new Response(ds.readable).text();
  return JSON.parse(txt);
}

class ReplayPlayer {
  constructor(viewport) {
    this.vp = viewport;
    this.run = null; this.frames = []; this.loadedTo = -1; this.loading = false;
    this.t = 0; this.speed = 1; this.playing = false; this.follow = false;
    this.onFrame = null; this.onState = null;
    this._raf = null; this._last = 0; this._lastEmit = 0;
  }
  async load(runId) {
    this.stop();
    const r = await fetch('/api/runs/' + runId, { credentials: 'same-origin', cache: 'no-store' }).then((x) => x.json());
    this.run = r.run; this.frames = []; this.loadedTo = -1; this.t = 0;
    this.follow = this.run.status === 'recording';
    this.scene = (this.run.meta && this.run.meta.scene) || null;
    ReplayPlayer._kind = (this.run.meta && this.run.meta.kind) || '';
    this.cellSnaps = []; this._cellAfter = 0; this._cellApplied = -1;
    await this._loadCells();
    await this._ensure(0);
    this._emitState();
    return this.run;
  }
  get duration() { return this.run ? Number(this.run.t_sim_end || 0) : 0; }
  async _refreshRun() {
    try {
      const r = await fetch('/api/runs/' + this.run.id, { credentials: 'same-origin', cache: 'no-store' }).then((x) => x.json());
      if (r && r.run) this.run = r.run;
    } catch { /* 유지 */ }
  }
  /* t 부터 REPLAY_PREFETCH_S 앞까지 받아 둔다 (중복 요청 방지) */
  async _ensure(t) {
    if (!this.run || this.loading) return;
    const need = t + REPLAY_PREFETCH_S * Math.max(1, this.speed);   // 배속만큼 더 앞까지
    // 뒤로 탐색했으면 그 구간부터 다시 받는다
    if (this.frames.length && t < this.frames[0].t - 0.5) { this.frames = []; this.loadedTo = Math.max(0, t - 1); }
    if (this.loadedTo >= need) return;
    this.loading = true;
    try {
      const from = Math.max(0, this.loadedTo);
      const r = await fetch(`/api/runs/${this.run.id}/chunks?from=${from}&to=${Math.min(need, from + 110)}`, { credentials: 'same-origin', cache: 'no-store' }).then((x) => x.json());
      const have = new Set(this.frames.map((f) => f.t));
      for (const c of r.chunks || []) {
        const fr = await gunzipJson(c.data);
        for (const f of fr) if (!have.has(f.t)) { this.frames.push(f); have.add(f.t); }
        this.loadedTo = Math.max(this.loadedTo, c.t1);
      }
      this.frames.sort((a, b) => a.t - b.t);
      if (!(r.chunks || []).length) this.loadedTo = Math.max(this.loadedTo, need);
      // 지나간 프레임 정리 (탐색용으로 REPLAY_KEEP_BACK_S 만 남김)
      const cut = t - REPLAY_KEEP_BACK_S;
      let k = 0; while (k < this.frames.length && this.frames[k].t < cut) k++;
      if (k > 0) this.frames.splice(0, k);
    } catch (err) { console.warn('리플레이 청크 로드 실패:', err); }
    finally { this.loading = false; }
  }
  /* 셀 판정 스냅샷(~10 s 간격)을 전부 받아 둔다 — 작다(수십 KB). 기록 중이면 따라가며 더 받는다 */
  async _loadCells() {
    if (!this.run) return;
    try {
      for (let guard = 0; guard < 200; guard++) {
        const r = await fetch(`/api/runs/${this.run.id}/cells?after=${this._cellAfter}`, { credentials: 'same-origin', cache: 'no-store' }).then((x) => x.json());
        const rows = r.cells || [];
        for (const c of rows) { this.cellSnaps.push({ id: c.id, t: Number(c.t), data: await gunzipJson(c.data) }); this._cellAfter = c.id; }
        if (rows.length < 20) break;
      }
    } catch (err) { console.warn('셀 스냅샷 로드 실패:', err); }
  }
  _applyCells() {
    const S = this.cellSnaps; if (!S.length) return;
    let k = -1; for (let i = 0; i < S.length; i++) { if (S[i].t <= this.t) k = i; else break; }
    if (k === this._cellApplied) return;
    if (k < this._cellApplied) { this.vp._stampedN = 0; this.vp._stampKey = null; if (this.vp.resetPolish) this.vp.resetPolish(); }   // 뒤로 탐색: 광택 다시
    this._cellApplied = k;
    if (k < 0) this.vp.clearCells(); else this.vp.setCells(S[k].data, this.scene);
  }
  play() { if (!this.run) return; this.playing = true; this._last = performance.now(); if (!this._raf) this._raf = requestAnimationFrame((n) => this._tick(n)); this._emitState(); }
  pause() { this.playing = false; this._emitState(); }
  stop() { this.playing = false; if (this._raf) cancelAnimationFrame(this._raf); this._raf = null; this.vp.setLive(null); this.vp.clearCells(); this._cellApplied = -1; this.vp._stampedN = 0; this.vp._stampKey = null; this._emitState(); }
  seek(t) { this.t = Math.max(0, Math.min(t, this.duration)); this._ensure(this.t); this._apply(); this._emitState(true); }
  setSpeed(x) { this.speed = x; this._emitState(); }
  _emitState(force) {
    if (this.onState) this.onState({ t: this.t, duration: this.duration, playing: this.playing, speed: this.speed, follow: this.follow,
                                     status: this.run ? this.run.status : '', loaded: this.loadedTo });
  }
  _tick(now) {
    this._raf = requestAnimationFrame((n) => this._tick(n));
    const dt = Math.min(0.1, (now - this._last) / 1000); this._last = now;
    if (!this.playing || !this.run) return;
    if (this.follow) {
      // 기록 중: 끝에서 LAG 만큼 뒤를 따라간다 (5 s 마다 런 정보 갱신)
      if (!this._lastRefresh || now - this._lastRefresh > 5000) { this._lastRefresh = now; this._refreshRun().then(() => { if (this.run.status !== 'recording') this.follow = false; }); this._loadCells(); }
      const target = Math.max(0, this.duration - REPLAY_LIVE_LAG_S);
      this.t = Math.min(target, this.t + dt * this.speed);
    } else {
      this.t += dt * this.speed;
      if (this.t >= this.duration) { this.t = this.duration; this.playing = false; }
    }
    this._ensure(this.t);
    this._apply();
    if (now - this._lastEmit > 200) { this._lastEmit = now; this._emitState(); }
  }
  /* 현재 시각의 프레임을 이웃 두 프레임에서 보간해 뷰포트·콜백에 준다 */
  _apply() {
    const F = this.frames; if (!F.length) return;
    let lo = 0, hi = F.length - 1;
    while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (F[mid].t <= this.t) lo = mid; else hi = mid - 1; }
    const a = F[lo], b = F[Math.min(lo + 1, F.length - 1)];
    const u = b.t > a.t ? Math.max(0, Math.min(1, (this.t - a.t) / (b.t - a.t))) : 0;
    const feed = ReplayPlayer.interp(a, b, u, this.scene);
    this.vp.setLive(feed, true);
    this._applyCells();
    if (this.onFrame) this.onFrame(feed, a);
  }
  static interp(a, b, u, scene) {
    const L = (x, y) => x + (y - x) * u;
    const robots = a.r.map((ra, i) => {
      const rb = (b.r && b.r[i]) || ra;
      const r = { id: ra[0], force: L(ra[1], rb[1]), target: L(ra[2], rb[2]), state: ra[3], progress: L(ra[4], rb[4]),
                  rl_force_scale: L(ra[5], rb[5]), rl_feed_scale: L(ra[6], rb[6]) };
      if (ra[7] && rb[7]) r.q = ra[7].map((v, j) => L(v, rb[7][j])); else if (ra[7]) r.q = ra[7].slice();
      if (ra[10]) r.tcp = rb[10] ? ra[10].map((v, j) => L(v, rb[10][j])) : ra[10].slice();
      if (ra[11]) r.normal = ra[11].slice();
      if (ra[8]) {
        const pos = rb[8] ? ra[8].map((v, j) => L(v, rb[8][j])) : ra[8].slice();
        let quat = ra[9];
        if (ra[9] && rb[9]) {
          const qa = new THREE.Quaternion(ra[9][1], ra[9][2], ra[9][3], ra[9][0]);
          const qb = new THREE.Quaternion(rb[9][1], rb[9][2], rb[9][3], rb[9][0]);
          qa.slerp(qb, u); quat = [qa.w, qa.x, qa.y, qa.z];
        }
        r.base = { pos, quat };
      }
      return r;
    });
    return { ts: Date.now() / 1000, state: a.s, progress: L(a.p, b.p), elapsed_s: L(a.e, b.e), robots, scene, t_sim: L(a.t, b.t), kind: ReplayPlayer._kind || '' };
  }
}

if (!customElements.get('polytwin-viewport')) customElements.define('polytwin-viewport', PolyTwinViewport);
