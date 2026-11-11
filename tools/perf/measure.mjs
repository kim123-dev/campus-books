// 화면 이동 속도 측정 (헤드리스 Chrome, 375px): 목록 → 상세 → 쪽지함 → 프로필을 세 가지 상황으로 잰다.
//   first  : 새 브라우저 프로필로 처음 방문
//   second : 같은 브라우저에서 바로 다시 방문 (메모리·HTTP 캐시가 살아 있음)
//   cold   : 브라우저를 껐다가 COLD_WAIT초 뒤 같은 프로필로 다시 방문 (브라우저 추정 캐시 기간이 지난 재방문)
// 사용: node tools/perf/measure.mjs <출력 폴더> [반복 횟수=3]   → <출력 폴더>/results.json
//       node tools/perf/report.mjs <출력 폴더>/results.json   → 화면별 중앙값 표와 요청 목록
// 환경 변수 (모두 선택)
//   BASE        측정할 주소 (기본: 운영 사이트)
//   TOKEN       로그인 토큰. 있으면 로그인 상태로 잰다. 없으면 쪽지함은 로그인 화면으로 넘어가는 시간을 잰다
//   LATENCY     요청마다 더할 지연(ms). 로컬 서버를 운영과 비슷한 왕복 시간으로 잴 때 쓴다 (기본 0)
//   COLD_WAIT   cold 측정 전 기다릴 초 (기본 150)
//   CHROME_PATH Chrome 실행 파일, CDP_PORT 원격 디버깅 포트 (기본 9444)
// 목록의 첫 글과 그 판매자로 상세·프로필 주소를 정한다. 글이 하나도 없으면 측정할 수 없다.
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const BASE = (process.env.BASE ?? "https://campus-books-production.up.railway.app").replace(/\/$/, "");
const OUT = resolve(process.argv[2] ?? "tools/perf/out");
const RUNS = Number(process.argv[3] ?? 3);
const TOKEN = process.env.TOKEN ?? null;
const LATENCY = Number(process.env.LATENCY ?? 0);
const CHROME =
  process.env.CHROME_PATH ??
  [
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
  ].find((path) => existsSync(path));
// Chrome을 띄울 때마다 다른 포트를 쓴다. (이전 Chrome이 늦게 꺼져도 겹치지 않게)
let nextPort = Number(process.env.CDP_PORT ?? 9444);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
mkdirSync(OUT, { recursive: true });
// Chrome 프로필은 짧은 임시 폴더에 둔다. Windows는 경로가 260자를 넘으면 서비스 워커 캐시 파일을 만들지 못해
// 설치가 "Entry already exists"로 실패한다. (프로필 안 캐시 경로만 150자 가까이 된다)
const PROFILES = mkdtempSync(join(tmpdir(), "cb-perf-"));

// 화면별 "본문이 그려졌다" 조건 (불러오는 중 문구가 바뀌고 내용이 들어옴)
const READY = {
  list: `document.querySelectorAll('#post-list > *').length > 0`,
  detail: `!!document.querySelector('.post-detail__info')`,
  inbox: TOKEN
    ? `(() => { const s = document.getElementById('result-summary'); return s && !s.textContent.includes('불러오는 중'); })()`
    : `location.pathname.endsWith('/login.html') && !!document.querySelector('form')`,
  profile: `(() => { const r = document.getElementById('reviews-summary'); const p = document.getElementById('posts-summary'); const done = (x) => x && x.textContent && !x.textContent.includes('불러오는 중'); return done(r) && done(p); })()`,
};

async function startChrome(profile, fresh = true) {
  if (fresh) rmSync(profile, { recursive: true, force: true });
  const PORT = nextPort++;
  const proc = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "--no-first-run", "--no-default-browser-check", "about:blank"]);
  let wsUrl;
  for (let i = 0; i < 150 && !wsUrl; i++) {
    try {
      wsUrl = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find((t) => t.type === "page")?.webSocketDebuggerUrl;
    } catch {}
    if (!wsUrl) await sleep(200);
  }
  const ws = new WebSocket(wsUrl);
  await new Promise((r) => ws.addEventListener("open", r));
  let id = 1;
  const pending = new Map();
  const listeners = [];
  ws.addEventListener("message", (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) {
      const p = pending.get(m.id);
      pending.delete(m.id);
      m.error ? p.reject(new Error(m.error.message)) : p.resolve(m.result);
    }
    for (const fn of listeners) fn(m);
  });
  const send = (method, params = {}) => {
    const i = id++;
    ws.send(JSON.stringify({ id: i, method, params }));
    return new Promise((resolve, reject) => pending.set(i, { resolve, reject }));
  };
  const evaluate = async (expression) => {
    const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text);
    return r.result.value;
  };
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Network.enable");
  // 서비스 워커 설치 실패를 결과에 남긴다. (설치가 안 되면 재방문도 네트워크로 가서 숫자가 크게 달라진다)
  const swErrors = [];
  listeners.push((m) => {
    if (m.method === "ServiceWorker.workerErrorReported") swErrors.push(m.params.errorMessage?.errorMessage ?? JSON.stringify(m.params));
  });
  await send("ServiceWorker.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 375, height: 812, deviceScaleFactor: 2, mobile: true });
  // 네트워크로 나가는 요청에만 지연이 붙는다. 서비스 워커 캐시·메모리 캐시에서 나오는 응답은 그대로다.
  if (LATENCY > 0) await send("Network.emulateNetworkConditions", { offline: false, latency: LATENCY, downloadThroughput: -1, uploadThroughput: -1 });
  // 끌 때는 Chrome이 완전히 끝날 때까지 기다린다. (같은 프로필로 다시 열 때 이전 프로세스와 겹치지 않게)
  const exited = new Promise((r) => proc.once("exit", r));
  const close = async () => {
    ws.close();
    proc.kill();
    await exited;
  };
  return { send, evaluate, listeners, swErrors, close };
}

async function visit(b, name, url) {
  const reqs = new Map();
  const on = (m) => {
    const p = m.params;
    if (m.method === "Network.requestWillBeSent") {
      reqs.set(p.requestId, { url: p.request.url, type: p.type, start: p.timestamp, initiator: p.initiator?.url ?? p.initiator?.stack?.callFrames?.[0]?.url ?? "" });
    } else if (m.method === "Network.responseReceived" && reqs.has(p.requestId)) {
      const r = reqs.get(p.requestId);
      r.status = p.response.status;
      r.sw = p.response.fromServiceWorker;
      r.disk = p.response.fromDiskCache;
      r.enc = p.response.headers["content-encoding"] ?? p.response.headers["Content-Encoding"] ?? "";
      r.timing = p.response.timing;
    } else if (m.method === "Network.loadingFinished" && reqs.has(p.requestId)) {
      const r = reqs.get(p.requestId);
      r.end = p.timestamp;
      r.size = p.encodedDataLength;
    } else if (m.method === "Network.loadingFailed" && reqs.has(p.requestId)) {
      reqs.get(p.requestId).end = p.timestamp;
      reqs.get(p.requestId).failed = p.errorText;
    }
  };
  b.listeners.push(on);
  await b.send("Page.navigate", { url });
  // 새 문서로 바뀔 때까지 기다린 뒤, 문서 안에서 조건을 rAF로 확인해 그 시각(performance.now)을 받는다.
  let ready = null;
  const t0 = Date.now();
  while (Date.now() - t0 < 15000) {
    await sleep(30);
    try {
      ready = await b.evaluate(`(async () => {
        if (performance.getEntriesByType('navigation')[0]?.name !== ${JSON.stringify(url)} && !${JSON.stringify(name === "inbox" && !TOKEN)}) return null;
        const ok = () => { try { return ${READY[name]}; } catch { return false; } };
        const start = performance.now();
        while (!ok()) { if (performance.now() - start > 12000) return -1; await new Promise(r => requestAnimationFrame(r)); }
        await new Promise(r => requestAnimationFrame(r));
        const nav = performance.getEntriesByType('navigation')[0];
        const fcp = performance.getEntriesByName('first-contentful-paint')[0];
        return { ready: performance.now(), href: location.pathname, ttfb: nav.responseStart, dcl: nav.domContentLoadedEventEnd, fcp: fcp?.startTime ?? null };
      })()`);
      if (ready) break;
    } catch {}
  }
  // load 이벤트까지 기다린다. 서비스 워커는 load 뒤에 등록되므로(pwa.js), 이걸 기다리지 않고 다음 화면으로 가면
  // 측정 도구에서는 등록이 시작되지 않는 경우가 있었다. 실제 사용자도 화면이 다 뜬 뒤에 옮긴다.
  for (let i = 0; i < 200; i++) {
    try {
      if (await b.evaluate("document.readyState === 'complete'")) break;
    } catch {}
    await sleep(50);
  }
  await sleep(1500); // 늦게 끝나는 요청(배지, 서비스 워커 설치)까지 모은다
  b.listeners.splice(b.listeners.indexOf(on), 1);
  const list = [...reqs.values()].sort((a, c) => a.start - c.start);
  const base = list[0]?.start ?? 0;
  const rows = list.map((r) => ({
    url: r.url.replace(BASE, "").replace(/^https?:\/\/[^/]+/, (h) => h),
    type: r.type,
    startMs: Math.round((r.start - base) * 1000),
    durMs: r.end ? Math.round((r.end - r.start) * 1000) : null,
    ttfbMs: r.timing ? Math.round(r.timing.receiveHeadersEnd - r.timing.sendStart) : null,
    connMs: r.timing && r.timing.connectStart >= 0 ? Math.round(r.timing.connectEnd - r.timing.connectStart) : 0,
    src: r.sw ? "SW" : r.disk ? "disk" : r.status ? "net" : "-",
    status: r.status ?? r.failed,
    size: r.size,
    enc: r.enc,
    initiator: (r.initiator || "").replace(BASE, ""),
  }));
  // 이 화면을 서비스 워커가 맡았는지 (맡았으면 정적 파일이 서비스 워커 캐시에서 나온다)
  const controlled = await b.evaluate("!!navigator.serviceWorker?.controller").catch(() => null);
  return { name, url: url.replace(BASE, ""), ...ready, controlled, requests: rows };
}

async function flow(b, ids) {
  const out = [];
  out.push(await visit(b, "list", `${BASE}/static/index.html`));
  out.push(await visit(b, "detail", `${BASE}/static/post.html?id=${ids.post}`));
  out.push(await visit(b, "inbox", `${BASE}/static/conversations.html`));
  out.push(await visit(b, "profile", `${BASE}/static/user.html?id=${ids.seller}`));
  return out;
}

const posts = await (await fetch(`${BASE}/posts?page=1&size=12`)).json();
const ids = { post: posts.items[0].id, seller: posts.items[0].seller.id };
const results = [];
for (let run = 0; run < RUNS; run++) {
  const b = await startChrome(join(PROFILES, `p${run}`));
  if (TOKEN) {
    await b.send("Page.navigate", { url: `${BASE}/static/login.html` });
    await sleep(1500);
    await b.evaluate(`localStorage.setItem('campus-books.token', ${JSON.stringify(TOKEN)})`);
    await b.evaluate(`navigator.serviceWorker.getRegistrations().then(rs => Promise.all(rs.map(r => r.unregister())))`);
    await b.evaluate(`caches.keys().then(ks => Promise.all(ks.map(k => caches.delete(k))))`);
    await b.send("Network.clearBrowserCache");
  }
  const first = await flow(b, ids);
  await sleep(1000);
  const sw = await b.evaluate(`navigator.serviceWorker.getRegistration('/static/').then(r => (r?.active ? 'active' : 'none') + (navigator.serviceWorker.controller ? ' ctrl' : ''))`);
  const second = await flow(b, ids);
  results.push({ run, sw, swErrors: [...b.swErrors], first, second });
  await b.close();
  await sleep(800);
}
// 브라우저를 껐다가, 추정 캐시 기간(마지막 수정 후 경과의 10%)이 지난 뒤 같은 프로필로 다시 연다.
const WAIT = Number(process.env.COLD_WAIT ?? 150);
console.log(`waiting ${WAIT}s for heuristic cache to expire`);
await sleep(WAIT * 1000);
for (const r of results) {
  const b = await startChrome(join(PROFILES, `p${r.run}`), false);
  r.cold = await flow(b, ids);
  await b.close();
  await sleep(800);
}
writeFileSync(join(OUT, "results.json"), JSON.stringify({ ids, results }, null, 2));
rmSync(PROFILES, { recursive: true, force: true });
for (const r of results) {
  for (const kind of ["first", "second", "cold"]) {
    console.log(`run${r.run} ${kind}: ` + r[kind].map((v) => `${v.name}=${Math.round(v.ready)}ms(req ${v.requests.length}${v.controlled ? ", SW" : ""})`).join("  "));
  }
}
