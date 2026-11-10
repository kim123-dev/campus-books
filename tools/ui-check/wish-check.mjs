// 11단계 찜하기 화면을 375px 헤드리스 Chrome으로 확인한다. (DevTools 프로토콜 직접 사용, 추가 설치 없음)
import { spawn } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { BASE, CDP_PORT, CHROME_PATH } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const seed = JSON.parse(readFileSync(join(OUT, "seed.json"), "utf8"));
const PORT = CDP_PORT;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, detail = "") => {
  results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);
};

const chrome = spawn(CHROME_PATH, [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${join(OUT, "chrome-profile")}`,
  "--no-first-run",
  "--no-default-browser-check",
  "about:blank",
]);

let ws;
let nextId = 1;
const pending = new Map();
const exceptions = [];

async function connect() {
  for (let i = 0; i < 50; i++) {
    try {
      const targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = targets.find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(200);
  }
  throw new Error("Chrome에 연결하지 못했습니다.");
}

function send(method, params = {}) {
  const id = nextId++;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

async function evaluate(expression) {
  const { result, exceptionDetails } = await send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
  return result.value;
}

async function goto(path, waitFor) {
  await send("Page.navigate", { url: BASE + path });
  await waitUntil(waitFor ?? "document.readyState === 'complete'");
}

async function waitUntil(expression, timeout = 8000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try {
      if (await evaluate(`Boolean(${expression})`)) return true;
    } catch {}
    await sleep(150);
  }
  return false;
}

async function screenshot(name) {
  const { data } = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, name), Buffer.from(data, "base64"));
}

async function api(method, path, token, body) {
  const response = await fetch(BASE + path, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  return response.status;
}

const setToken = (token) => evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(token)})`);
// 모바일 에뮬레이션에서는 내용이 넓으면 innerWidth도 함께 넓어지므로, 375px 고정값과 모든 요소의 오른쪽 끝을 비교한다.
const noHorizontalScroll = () => evaluate(`document.documentElement.scrollWidth <= ${W} && [...document.querySelectorAll('main *')].every(e => e.getBoundingClientRect().right <= ${W + 0.5} || getComputedStyle(e).position === 'absolute' || e.closest('.visually-hidden'))`);

try {
  ws = new WebSocket(await connect());
  await new Promise((r) => ws.addEventListener("open", r));
  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    }
    if (msg.method === "Runtime.exceptionThrown") exceptions.push(msg.params.exceptionDetails.exception?.description);
    if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") exceptions.push(msg.params.entry.text);
  });
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Log.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: 812, deviceScaleFactor: 2, mobile: true });

  // ---------- 11단계: 찜하기 (375px) ----------
  const heartOf = (postId) => `document.querySelector('.post-list__item a[href$="id=${postId}"]')?.parentElement.querySelector('.wish-button')`;
  const pressed = (selector) => evaluate(`${selector}?.getAttribute('aria-pressed') ?? null`);
  const getJson = async (path, token) => (await fetch(BASE + path, { headers: token ? { Authorization: `Bearer ${token}` } : {} })).json();
  const wishedIds = async () => (await getJson("/users/me/wishlist", seed.buyer_token)).items.map((i) => i.id);
  const createPost = async (title) => {
    const res = await fetch(`${BASE}/posts`, {
      method: "POST",
      headers: { Authorization: `Bearer ${seed.seller_token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ title, book_title: "테스트 교재", condition: "GOOD", price: 5000 }),
    });
    return (await res.json()).id;
  };
  const listUrl = "/static/index.html";
  const listReady = "document.querySelectorAll('.post-card').length > 0";

  // 비로그인: 하트는 보이고, 누르면 로그인 화면으로 (돌아올 주소 포함)
  await goto(listUrl);
  await evaluate("localStorage.clear()");
  await goto(listUrl, listReady);
  check("비로그인: 카드마다 하트, 모두 빈 하트", (await evaluate("document.querySelectorAll('.wish-button').length")) === (await evaluate("document.querySelectorAll('.post-card').length")) && (await evaluate("[...document.querySelectorAll('.wish-button')].every(b => b.getAttribute('aria-pressed') === 'false')")));
  await evaluate(`${heartOf(seed.p1)}.click()`);
  await waitUntil("location.pathname === '/static/login.html'");
  check("비로그인: 하트 누르면 로그인 화면 (next=목록)", await evaluate("location.pathname === '/static/login.html' && new URLSearchParams(location.search).get('next') === '/static/index.html'"), await evaluate("location.href"));
  await goto("/static/wishlist.html");
  await waitUntil("location.pathname === '/static/login.html'");
  check("비로그인: 찜 목록 화면은 로그인으로", await evaluate("location.pathname === '/static/login.html'"));

  // 구매자 로그인: 내 글(p3)에는 하트 없음, 남의 글 찜하기
  await setToken(seed.buyer_token);
  // 모바일은 헤더 메뉴 대신 하단 탭 바 (14단계)
  await goto(listUrl, listReady + " && document.getElementById('nav-messages')");
  check("탭 바: '찜' 탭", (await evaluate("document.querySelector('.tab-bar a[href=\"/static/wishlist.html\"] .tab-bar__label')?.textContent")) === "찜");
  check("목록: 내 글 카드에는 하트 없음", (await evaluate(`${heartOf(seed.p3)} === null`)) && (await pressed(heartOf(seed.p1))) === "false");
  const placement = await evaluate(`(() => {
    const b = ${heartOf(seed.p1)}.getBoundingClientRect();
    const c = ${heartOf(seed.p1)}.parentElement.getBoundingClientRect();
    return { inside: b.right <= c.right && b.bottom <= c.bottom && c.right - b.right < 12 && c.bottom - b.bottom < 12, size: [Math.round(b.width), Math.round(b.height)] };
  })()`);
  // 모바일 가로형 카드에서는 카드 오른쪽 아래 (14단계). PC는 사진 오른쪽 위 그대로.
  check("목록: 하트는 카드 오른쪽 아래, 44px", placement.inside && placement.size[0] >= 44 && placement.size[1] >= 44, JSON.stringify(placement));
  check("목록: 하트 이름에 글 제목", (await evaluate(`${heartOf(seed.p1)}.getAttribute('aria-label')`)).endsWith("찜하기"));
  await evaluate(`${heartOf(seed.p1)}.click()`);
  await waitUntil(`${heartOf(seed.p1)}.getAttribute('aria-pressed') === 'true'`);
  check("목록: 하트 누르면 찜 (채운 하트 + 서버 반영)", (await pressed(heartOf(seed.p1))) === "true" && (await wishedIds()).includes(seed.p1));
  check(`${W}px: 목록 가로 스크롤 없음`, await noHorizontalScroll());
  await evaluate(`${heartOf(seed.p1)}.scrollIntoView({block: 'center'})`);
  await screenshot("11-1-list-heart.png");

  await goto(listUrl, listReady);
  check("목록: 새로고침해도 찜 상태 유지", (await pressed(heartOf(seed.p1))) === "true");

  // 상세: 해제·다시 찜, 내 글은 하트 없음
  const detailReady = "!document.getElementById('post-detail').hidden";
  await goto(`/static/post.html?id=${seed.p1}`, detailReady);
  // 모바일은 하트가 하단 연락 바로 옮겨진다.
  const detailHeart = "document.querySelector('.post-detail__top .wish-button, .contact-bar .wish-button')";
  check("상세: 찜한 글은 채운 하트", (await pressed(detailHeart)) === "true");
  await evaluate(`${detailHeart}.click()`);
  await waitUntil(`${detailHeart}.getAttribute('aria-pressed') === 'false'`);
  check("상세: 누르면 해제", (await pressed(detailHeart)) === "false" && !(await wishedIds()).includes(seed.p1));
  await evaluate(`${detailHeart}.click()`);
  await waitUntil(`${detailHeart}.getAttribute('aria-pressed') === 'true'`);
  check("상세: 다시 누르면 찜", (await wishedIds()).includes(seed.p1));
  check(`${W}px: 상세 가로 스크롤 없음`, await noHorizontalScroll());
  await screenshot("11-2-detail-heart.png");
  await goto(`/static/post.html?id=${seed.p3}`, detailReady);
  check("상세: 내 글에는 하트 없음", await evaluate(`${detailHeart} === null`));

  // 판매 완료: 찜해 둔 글은 남고(배지), 찜 안 한 판매 완료 글에는 하트 없음
  await api("POST", `/posts/${seed.p2}/wishlist`, seed.buyer_token);
  await api("PATCH", `/posts/${seed.p2}/status`, seed.seller_token, { status: "SOLD" });
  const soldPlain = await createPost("판매 완료된 다른 글");
  await api("PATCH", `/posts/${soldPlain}/status`, seed.seller_token, { status: "SOLD" });
  await goto(listUrl, listReady);
  check("목록: 찜한 판매 완료 글은 하트 유지, 찜 안 한 판매 완료 글은 하트 없음", (await pressed(heartOf(seed.p2))) === "true" && (await evaluate(`${heartOf(soldPlain)} === null`)));

  // 찜 목록 화면
  await evaluate("document.querySelector('.tab-bar a[href=\"/static/wishlist.html\"]').click()");
  await waitUntil("location.pathname === '/static/wishlist.html' && document.querySelectorAll('.post-card').length > 0");
  const wishCards = await evaluate("[...document.querySelectorAll('.post-list__item')].map(li => ({ href: li.querySelector('a').getAttribute('href'), pressed: li.querySelector('.wish-button')?.getAttribute('aria-pressed'), sold: !!li.querySelector('.badge--sold') }))");
  check("찜 목록: 찜한 2개, 최근 찜(p2)이 먼저, 모두 채운 하트", wishCards.length === 2 && wishCards[0].href.endsWith(`id=${seed.p2}`) && wishCards.every((c) => c.pressed === "true"), JSON.stringify(wishCards));
  check("찜 목록: 판매 완료 글은 배지 표시", wishCards[0].sold === true && wishCards[1].sold === false);
  check("찜 목록: 요약 '총 2개'", (await evaluate("document.getElementById('result-summary').textContent")) === "총 2개");
  check(`${W}px: 찜 목록 가로 스크롤 없음`, await noHorizontalScroll());
  await screenshot("11-3-wishlist.png");
  await evaluate(`${heartOf(seed.p2)}.click()`);
  await waitUntil(`${heartOf(seed.p2)}.getAttribute('aria-pressed') === 'false'`);
  check("찜 목록: 해제해도 카드는 그 자리에 (빈 하트)", (await evaluate("document.querySelectorAll('.post-list__item').length")) === 2 && (await pressed(heartOf(seed.p2))) === "false");
  await goto("/static/wishlist.html", "document.querySelectorAll('.post-card').length > 0");
  check("찜 목록: 새로고침하면 해제한 글은 사라짐", (await evaluate("document.querySelectorAll('.post-card').length")) === 1);

  // 실패 알림: 화면을 연 뒤 글이 삭제됨
  await goto(listUrl, listReady);
  await api("DELETE", `/posts/${seed.p1}`, seed.seller_token);
  await evaluate(`${heartOf(seed.p1)}.click()`);
  await waitUntil("document.querySelector('.toast') && !document.querySelector('.toast').hidden");
  const toast = await evaluate("({ text: document.querySelector('.toast')?.textContent, role: document.querySelector('.toast')?.getAttribute('role') })");
  check("실패: 삭제된 글 하트 → 서버 메시지 알림", toast.text === "게시글을 찾을 수 없습니다." && toast.role === "alert", JSON.stringify(toast));
  check(`${W}px: 알림이 화면 안에`, await evaluate(`(() => { const r = document.querySelector('.toast').getBoundingClientRect(); return r.left >= 0 && r.right <= ${W}; })()`));
  await screenshot("11-4-toast.png");
  await goto("/static/wishlist.html", "document.getElementById('result-summary').textContent !== '불러오는 중…'");
  check("글 삭제: 찜 목록에서도 사라짐 (빈 목록 안내)", (await evaluate("document.querySelectorAll('.post-card').length")) === 0 && !(await evaluate("document.getElementById('empty-actions').hidden")));

  // 하단 탭 바가 화면 안에 (14단계: 헤더 메뉴 대신)
  check(`${W}px: 탭 바 가로 넘침 없음`, await evaluate(`[...document.querySelectorAll('.tab-bar > *')].every(e => e.getBoundingClientRect().right <= ${W} + 0.5)`));

  check("JS 예외·콘솔 에러 없음", exceptions.filter((e) => !String(e).includes("Failed to load resource")).length === 0, exceptions.join(" / "));
} catch (error) {
  results.push(`ERROR  ${error.stack}`);
} finally {
  writeFileSync(join(OUT, "wish-check.txt"), results.join("\n"));
  console.log(results.join("\n"));
  ws?.close();
  chrome.kill();
}
