// PWA 확인 (375px, 목록 화면만): 아이폰 Safari 설치 안내 표시·닫기·다시 안 뜸, standalone·다른 브라우저는 안 뜸,
// 서비스 워커가 정적 파일만 캐시하는지.
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { readSeed, seedExtra, sleep, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const seed = readSeed(OUT);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  [${W}] ${name}${detail ? `  (${detail})` : ""}`);

const UA = {
  iphoneSafari: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
  iphoneChrome: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/130.0.6723.90 Mobile/15E148 Safari/604.1",
  android: "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
};

await seedExtra(OUT, seed); // 사진 있는 글(/images 요청)이 목록에 나오게 한다.
const b = await startBrowser(OUT, { width: W, height: 812, mobile: true });
const { evaluate, waitUntil, goto, screenshot, send } = b;
const listReady = "document.querySelectorAll('.post-card').length > 0 && document.fonts.status === 'loaded'";
const guideShown = () => evaluate("!!document.querySelector('.install-guide') && document.querySelector('.install-guide').getClientRects().length > 0");
const setUa = (userAgent) => send("Emulation.setUserAgentOverride", { userAgent, platform: "" });

try {
  await goto("/static/index.html");
  await evaluate("localStorage.clear()");

  // ---------- 아이폰 Safari: 처음에는 안내가 보인다 ----------
  await setUa(UA.iphoneSafari);
  await goto("/static/index.html", listReady);
  await sleep(300);
  check("아이폰 Safari: 목록 맨 위에 설치 안내", (await guideShown()) && (await evaluate("document.querySelector('main').firstElementChild.classList.contains('install-guide')")));
  const guide = await evaluate(`(() => {
    const g = document.querySelector('.install-guide'), c = g.querySelector('.install-guide__close').getBoundingClientRect(), r = g.getBoundingClientRect();
    const sizes = [...g.querySelectorAll('p')].map(p => parseFloat(getComputedStyle(p).fontSize));
    return { text: g.textContent.replace(/\\s+/g, ' ').trim(), share: !!g.querySelector('.install-guide__share svg.icon--share'), close: [Math.round(c.width), Math.round(c.height)], closeLabel: g.querySelector('.install-guide__close').getAttribute('aria-label'), right: r.right, minFont: Math.min(...sizes), wide: document.documentElement.scrollWidth > ${W} };
  })()`);
  check("안내 문구: '공유 → 홈 화면에 추가' + 공유 아이콘", guide.text.includes("공유 → '홈 화면에 추가'") && guide.share, guide.text);
  check("안내: 닫기 버튼 44px, 이름 있음", guide.close[0] >= 44 && guide.close[1] >= 44 && guide.closeLabel === "홈 화면 추가 안내 닫기", guide.close.join("x"));
  check("안내: 글자 16px 이상, 가로 스크롤 없음", guide.minFont >= 16 && !guide.wide && guide.right <= W, `${guide.minFont}px`);
  await screenshot(`pwa-${W}-guide.png`);

  // 닫기 (손가락으로 누름)
  const p = await evaluate("(() => { const r = document.querySelector('.install-guide__close').getBoundingClientRect(); return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) }; })()");
  await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [p] });
  await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await sleep(400);
  check("닫기: 안내가 사라지고 localStorage에 기록", !(await guideShown()) && (await evaluate("localStorage.getItem('campus-books.install-guide-dismissed')")) === "1");
  await goto("/static/index.html", listReady);
  await sleep(300);
  check("닫은 뒤 다시 열어도 안 보임", !(await guideShown()));

  // ---------- 이미 홈 화면 앱으로 연 경우(standalone): 안 보임 ----------
  await evaluate("localStorage.removeItem('campus-books.install-guide-dismissed')");
  const { identifier } = await send("Page.addScriptToEvaluateOnNewDocument", { source: "Object.defineProperty(navigator, 'standalone', { get: () => true })" });
  await goto("/static/index.html", listReady);
  await sleep(300);
  check("홈 화면 앱(standalone)으로 열면 안 보임", !(await guideShown()) && (await evaluate("navigator.standalone")) === true);
  await send("Page.removeScriptToEvaluateOnNewDocument", { identifier });

  // ---------- 다른 브라우저: 안 보임 ----------
  for (const [label, ua] of [["아이폰 Chrome", UA.iphoneChrome], ["안드로이드 Chrome", UA.android]]) {
    await setUa(ua);
    await goto("/static/index.html", listReady);
    await sleep(300);
    check(`${label}: 안 보임 (Safari 공유 메뉴 안내라서)`, !(await guideShown()));
  }
  // 다시 아이폰 Safari면 기록이 없으므로 보인다 (위 확인이 기록을 지운 상태에서 했는지 확인)
  await setUa(UA.iphoneSafari);
  await goto("/static/index.html", listReady);
  await sleep(300);
  check("기록을 지운 아이폰 Safari: 다시 보임", await guideShown());

  // ---------- 서비스 워커: 정적 파일만 캐시 ----------
  await evaluate("navigator.serviceWorker.ready.then(() => true)");
  await goto("/static/index.html", listReady); // 서비스 워커가 이 화면을 맡은 상태로 다시 연다
  await waitUntil("navigator.serviceWorker.controller !== null", 8000);
  await waitUntil("[...document.querySelectorAll('img.post-card__thumb')].every(i => i.complete)", 8000);
  await sleep(800);
  const sw = await evaluate(`(async () => {
    const reg = await navigator.serviceWorker.getRegistration('/static/');
    const names = await caches.keys();
    const urls = [];
    for (const name of names) for (const req of await (await caches.open(name)).keys()) urls.push(new URL(req.url).pathname);
    const imageRequests = performance.getEntriesByType('resource').filter(e => new URL(e.name).pathname.startsWith('/images/')).length;
    return { scope: reg && new URL(reg.scope).pathname, controlled: !!navigator.serviceWorker.controller, names, urls, imageRequests };
  })()`);
  check("서비스 워커: /static/ 범위로 등록, 화면을 맡음", sw.scope === "/static/" && sw.controlled, JSON.stringify({ scope: sw.scope, controlled: sw.controlled }));
  check("캐시 이름에 버전 키", sw.names.length === 1 && /^campus-books-static-.+/.test(sw.names[0]), sw.names.join());
  check("캐시에 HTML·CSS·JS·아이콘이 담김", ["/static/index.html", "/static/css/style.css", "/static/js/pages/index.js", "/static/js/pwa.js", "/static/img/icon-192.png"].every((u) => sw.urls.includes(u)), `${sw.urls.length}개`);
  check("캐시에 API·사진(/images)은 없음 (목록이 사진을 불러왔어도)", sw.imageRequests > 0 && sw.urls.every((u) => u.startsWith("/static/")), `사진 요청 ${sw.imageRequests}개, /static 밖 ${sw.urls.filter((u) => !u.startsWith("/static/")).join() || "없음"}`);

  check("JS 예외·콘솔 에러 없음", b.exceptions.filter((e) => !String(e).includes("Failed to load resource")).length === 0, b.exceptions.join(" / "));
} catch (error) {
  results.push(`ERROR  ${error.stack}`);
} finally {
  writeFileSync(join(OUT, "pwa-check.txt"), results.join("\n"));
  b.close();
}
