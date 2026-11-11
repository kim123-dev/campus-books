// 서비스 워커 캐시 확인 (375px):
// 1) 계정 전환: 로그아웃하거나 다른 계정으로 바꿔도 이전 사용자의 화면 조각이 캐시에서 나오지 않는지
// 2) 새 배포: 파일을 바꾸고 서버를 다시 켜면(= 새 버전) 재방문 두 번 안에 새 화면이 나오는지, HTML과 JS가 섞이지 않는지
// 2)는 이 스크립트가 따로 띄운 서버(UI_CHECK_DEPLOY_PORT, 기본 8002)로 확인한다. 바꾼 파일은 끝나면 원래대로 돌려놓는다.
import { spawn } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { BASE, PYTHON, ROOT, cliEnv, readSeed, sleep, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const DEPLOY_PORT = Number(process.env.UI_CHECK_DEPLOY_PORT ?? 8002);
const DEPLOY_BASE = `http://127.0.0.1:${DEPLOY_PORT}`;
const seed = readSeed(OUT);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  [${W}] ${name}${detail ? `  (${detail})` : ""}`);

const b = await startBrowser(OUT, { width: W, height: 812, mobile: true });
const { evaluate, waitUntil, goto, send } = b;

// 캐시에 담긴 주소 (모든 캐시)
const cachedUrls = () =>
  evaluate(`(async () => {
    const urls = [];
    for (const name of await caches.keys()) for (const req of await (await caches.open(name)).keys()) urls.push(new URL(req.url).pathname + new URL(req.url).search);
    return urls;
  })()`);
const headerUser = () => evaluate(`document.querySelector('.site-nav__user')?.textContent ?? null`);
const inboxReady = "document.getElementById('result-summary') && !document.getElementById('result-summary').textContent.includes('불러오는 중')";
const partners = () => evaluate(`[...document.querySelectorAll('.conversation-card__partner')].map(e => e.textContent)`);
const setToken = (token) => evaluate(`localStorage.setItem('campus-books.token', ${JSON.stringify(token)})`);

const FILES = {
  html: join(ROOT, "static", "index.html"),
  js: join(ROOT, "static", "js", "pages", "index.js"),
};
const original = { html: readFileSync(FILES.html, "utf8"), js: readFileSync(FILES.js, "utf8") };
let server = null;

async function startServer() {
  const proc = spawn(PYTHON, ["-m", "uvicorn", "app.main:app", "--port", String(DEPLOY_PORT)], { cwd: ROOT, env: cliEnv(OUT) });
  for (let i = 0; i < 60; i++) {
    try {
      if ((await fetch(`${DEPLOY_BASE}/health`)).ok) return proc;
    } catch {}
    await sleep(500);
  }
  throw new Error("배포 확인용 서버가 켜지지 않았습니다.");
}
async function stopServer() {
  if (!server) return;
  const done = new Promise((r) => server.once("exit", r));
  server.kill();
  await done;
  server = null;
}
// 목록 화면을 열고, 그 화면이 어느 버전의 HTML·JS로 그려졌는지 읽는다.
async function openList() {
  await send("Page.navigate", { url: `${DEPLOY_BASE}/static/index.html` });
  await sleep(200);
  await waitUntil("document.readyState === 'complete' && document.querySelectorAll('#post-list > *').length > 0", 8000);
  return evaluate(`({ html: document.querySelector('meta[name=deploy-marker]')?.content ?? 'old', js: window.__deployMarker ?? 'old' })`);
}
const swVersion = () =>
  evaluate(`fetch('/static/sw.js').then(r => r.text()).then(t => t.match(/const VERSION = "([^"]+)"/)[1])`);

try {
  // ---------- 1) 계정 전환 ----------
  await goto("/static/index.html");
  await setToken(seed.buyer_token);
  await goto("/static/index.html", "document.querySelectorAll('#post-list > *').length > 0");
  await evaluate("navigator.serviceWorker.ready.then(() => true)");
  await goto("/static/conversations.html", inboxReady);
  await waitUntil("navigator.serviceWorker.controller !== null", 8000);
  // 서비스 워커가 화면을 맡은 상태(캐시에서 나오는 상태)로 다시 연다.
  await goto("/static/conversations.html", inboxReady);
  await waitUntil(`document.querySelector('.site-nav__user')`, 5000);
  const buyerHeader = await headerUser();
  const buyerPartners = await partners();
  check("구매자로 로그인: 헤더 이름, 쪽지함 상대", buyerHeader === "구매자지은님" && buyerPartners.length === 3 && buyerPartners.every((n) => n === "판매자민수"), `${buyerHeader} / ${buyerPartners.join(",")}`);
  // 프로필(판매자, 사용자 1번)도 캐시된 화면으로 연다.
  await goto("/static/user.html?id=1", "document.getElementById('profile-name')?.textContent");
  check("구매자가 본 판매자 프로필: 판매자 이름", (await evaluate("document.getElementById('profile-name').textContent")) === "판매자민수");

  // 로그아웃 (헤더 버튼과 같은 동작: 토큰 지우고 새로고침)
  await goto("/static/index.html", "document.querySelectorAll('#post-list > *').length > 0");
  await evaluate(`[...document.querySelectorAll('button')].find(b => b.textContent === '로그아웃').click()`);
  await sleep(300);
  await waitUntil("document.readyState === 'complete' && !localStorage.getItem('campus-books.token')", 5000);
  await waitUntil("[...document.querySelectorAll('a')].some(a => a.textContent === '로그인')", 5000);
  check("로그아웃 뒤 목록: 이전 사용자 이름 없음, 로그인 링크", (await headerUser()) === null && !(await evaluate("document.body.textContent.includes('구매자지은님')")));
  await goto("/static/conversations.html", "location.pathname.endsWith('/login.html')");
  check("로그아웃 뒤 쪽지함: 로그인 화면으로 이동 (캐시된 목록 없음)", await evaluate("location.pathname.endsWith('/login.html') && !document.querySelector('.conversation-card')"));

  // 다른 계정(판매자)으로 로그인
  await setToken(seed.seller_token);
  await goto("/static/conversations.html", inboxReady);
  await waitUntil(`document.querySelector('.site-nav__user')`, 5000);
  const sellerHeader = await headerUser();
  const sellerPartners = await partners();
  check("판매자로 바꾼 뒤: 헤더·쪽지함이 판매자 것", sellerHeader === "판매자민수님" && sellerPartners.length === 3 && sellerPartners.every((n) => n === "구매자지은"), `${sellerHeader} / ${sellerPartners.join(",")}`);
  check("화면 어디에도 이전 사용자 헤더 없음", !(await evaluate("document.body.textContent.includes('구매자지은님')")));
  const urls = await cachedUrls();
  check(
    "캐시에는 /static/ 파일만 (API·사진·쿼리 붙은 주소 없음)",
    urls.length > 0 && urls.every((u) => u.startsWith("/static/") && !u.includes("?")),
    `${urls.length}개, 밖: ${urls.filter((u) => !u.startsWith("/static/") || u.includes("?")).join() || "없음"}`,
  );
  check("캐시에 모든 화면 HTML이 미리 담김", ["index", "post", "conversations", "chat", "user", "admin", "login"].every((p) => urls.includes(`/static/${p}.html`)));

  // ---------- 2) 새 배포 ----------
  server = await startServer();
  await send("Page.navigate", { url: `${DEPLOY_BASE}/static/index.html` });
  await sleep(500);
  await evaluate("navigator.serviceWorker.ready.then(() => true)");
  await waitUntil("navigator.serviceWorker.controller !== null", 8000);
  const before = await openList();
  const oldVersion = await swVersion();
  check("배포 전: 옛 화면, 서비스 워커가 화면을 맡음", before.html === "old" && before.js === "old" && (await evaluate("!!navigator.serviceWorker.controller")), JSON.stringify(before));

  // 파일을 바꾸고 서버를 다시 켠다. (= 새 배포)
  await stopServer();
  writeFileSync(FILES.html, original.html.replace('<meta charset="utf-8" />', '<meta charset="utf-8" />\n    <meta name="deploy-marker" content="new" />'));
  writeFileSync(FILES.js, `${original.js}\nwindow.__deployMarker = "new";\n`);
  server = await startServer();

  const visit1 = await openList();
  // 사용자가 화면을 보는 동안 새 서비스 워커가 뒤에서 파일을 받는다. 켜질 때까지 걸린 시간을 함께 기록한다.
  const t0 = Date.now();
  const timeline = [];
  for (let i = 0; i < 100; i++) {
    const state = await evaluate(`navigator.serviceWorker.getRegistration('/static/').then(r => [r.installing?.state, r.waiting?.state, r.active?.state, r.active?.scriptURL].join('|'))`);
    const names = await evaluate("caches.keys()");
    timeline.push(`${Date.now() - t0}ms ${state.split("|").slice(0, 3).join("/")} caches=${names.length}`);
    // 옛 버전 캐시가 지워지고 새 버전 캐시만 남으면 새 서비스 워커가 켜진 것이다.
    if (names.length === 1 && names[0] !== `campus-books-static-${oldVersion}`) break;
    await sleep(100);
  }
  check("새 서비스 워커가 켜짐 (걸린 시간)", true, timeline.at(-1));
  results.push(`INFO  ${timeline.filter((_, i) => i % 5 === 0).join(" → ")}`);
  const visit2 = await openList();
  const newVersion = await swVersion();
  check("서버 재시작으로 sw.js 버전이 바뀜", newVersion !== oldVersion, `${oldVersion} → ${newVersion}`);
  check("재방문 1: HTML과 JS가 같은 버전 (섞이지 않음)", visit1.html === visit1.js, JSON.stringify(visit1));
  check("재방문 2: 새 화면 (HTML·JS 모두 새 버전)", visit2.html === "new" && visit2.js === "new", JSON.stringify(visit2));
  const names = await evaluate("caches.keys()");
  check("옛 버전 캐시는 지워지고 새 버전 캐시 하나만", names.length === 1 && names[0] === `campus-books-static-${newVersion}`, names.join());

  // 원래 파일로 되돌리고 다시 켜면 이전 버전 번호로 돌아온다. (내용이 같으면 버전도 같다)
  await stopServer();
  writeFileSync(FILES.html, original.html);
  writeFileSync(FILES.js, original.js);
  server = await startServer();
  await openList();
  check("파일을 되돌리면 버전도 이전 값", (await swVersion()) === oldVersion);
  await sleep(1500);
  const back = await openList();
  check("되돌린 뒤 재방문 2번 안에 옛 화면으로", back.html === "old" && back.js === "old", JSON.stringify(back));

  check("JS 예외·콘솔 에러 없음", b.exceptions.filter((e) => !String(e).includes("Failed to load resource")).length === 0, b.exceptions.join(" / "));
} catch (error) {
  results.push(`ERROR  ${error.stack}`);
} finally {
  // 확인 중 바꾼 파일은 무슨 일이 있어도 원래대로 돌려놓는다.
  writeFileSync(FILES.html, original.html);
  writeFileSync(FILES.js, original.js);
  await stopServer();
  writeFileSync(join(OUT, "sw-check.txt"), results.join("\n"));
  b.close();
}
