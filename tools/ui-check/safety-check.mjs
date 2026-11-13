// 9-2 쪽지 화면을 375px 헤드리스 Chrome으로 확인한다. (DevTools 프로토콜 직접 사용, 추가 설치 없음)
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

  // ---------- 12단계: 신고·차단 (375px) ----------
  const getJson = async (path, token) => (await fetch(BASE + path, { headers: { Authorization: `Bearer ${token}` } })).json();
  const text = (selector) => evaluate(`document.querySelector(${JSON.stringify(selector)})?.textContent ?? null`);
  const buttonByText = (label, scope = "document") => `[...${scope}.querySelectorAll('button')].find(b => b.textContent === ${JSON.stringify(label)})`;
  const sellerId = (await getJson("/users/me", seed.seller_token)).id;
  const buyerId = (await getJson("/users/me", seed.buyer_token)).id;
  const detailReady = "!document.getElementById('post-detail').hidden";
  const chatActions = "document.getElementById('chat-actions')";
  // 브라우저 확인 창은 헤드리스에서 멈추므로 항상 "확인"을 누른 것으로 바꾼다. (페이지를 열 때마다 다시)
  const autoConfirm = () => evaluate("window.confirm = (m) => { window.lastConfirm = m; return true; }");

  // 비로그인: 신고·차단 없음
  await goto("/static/index.html");
  await evaluate("localStorage.clear()");
  await goto(`/static/post.html?id=${seed.p1}`, detailReady);
  check("비로그인: 상세에 신고·차단 없음", await evaluate("document.querySelector('.post-detail__safety') === null"));

  // 구매자: 내 글에는 없고, 남의 글에는 있다
  await setToken(seed.buyer_token);
  await goto(`/static/post.html?id=${seed.p3}`, detailReady);
  check("상세: 내 글에는 신고·차단 없음", await evaluate("document.querySelector('.post-detail__safety') === null"));
  await goto(`/static/post.html?id=${seed.p1}`, detailReady + " && document.querySelector('.post-detail__safety')");
  check("상세: '이 글 신고'·'판매자 차단' 버튼", await evaluate(`!!${buttonByText("이 글 신고")} && !!${buttonByText("판매자 차단")}`));

  // 신고 창
  await evaluate(`${buttonByText("이 글 신고")}.click()`);
  await waitUntil("document.querySelector('dialog.report-dialog')?.open");
  const dialogBox = await evaluate("(() => { const r = document.querySelector('.report-dialog').getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom }; })()");
  check("신고 창: 모달로 열림, 375px 안에 (좌우 16px)", dialogBox.left >= 15.5 && dialogBox.right <= W - 15.5 && dialogBox.top >= 0 && dialogBox.bottom <= 812, JSON.stringify(dialogBox));
  check("신고 창: 사유 5개, 첫 사유에 포커스", (await evaluate("document.querySelectorAll('.report-dialog input[name=reason]').length")) === 5 && (await evaluate("document.activeElement?.name === 'reason'")));
  const reasonHeights = await evaluate("[...document.querySelectorAll('.report-dialog__reason')].map(l => Math.round(l.getBoundingClientRect().height))");
  check("신고 창: 사유 줄 높이 44px 이상", reasonHeights.every((h) => h >= 44), JSON.stringify(reasonHeights));
  await screenshot("12-1-report-dialog.png");
  await evaluate(`${buttonByText("신고하기")}.click()`);
  check("신고 창: 사유 없이 보내면 안내", (await text(".report-dialog .form-error")) === "신고 사유를 골라 주세요.");
  await evaluate("document.querySelector('.report-dialog input[value=OTHER]').click()");
  await evaluate(`${buttonByText("신고하기")}.click()`);
  check("신고 창: 기타 + 설명 없음이면 안내", (await text(".report-dialog .form-error")) === "기타 사유는 설명을 입력해 주세요." && (await evaluate("document.activeElement?.id === 'report-description'")));
  await evaluate("(() => { const t = document.getElementById('report-description'); t.value = '선입금을 요구해요'; t.dispatchEvent(new Event('input')); })()");
  check("신고 창: 글자 수 표시", (await text("#report-description-count")) === "9 / 500", await text("#report-description-count"));
  await screenshot("12-2-report-dialog-error.png");
  await evaluate(`${buttonByText("신고하기")}.click()`);
  await waitUntil("document.querySelector('.report-dialog') === null");
  check("신고: 접수되면 창이 닫히고 안내", (await text("#safety-notice")) === "신고가 접수되었습니다. 신고한 사실과 신고자는 상대에게 알려지지 않아요." && !(await evaluate("document.getElementById('safety-notice').hidden")));
  await screenshot("12-3-report-done.png");

  await evaluate(`${buttonByText("이 글 신고")}.click()`);
  await waitUntil("document.querySelector('dialog.report-dialog')?.open");
  await evaluate("document.querySelector('.report-dialog input[value=SPAM]').click()");
  await evaluate(`${buttonByText("신고하기")}.click()`);
  await waitUntil("document.querySelector('.report-dialog .form-error') && !document.querySelector('.report-dialog .form-error').hidden");
  check("신고: 같은 글 다시 신고 → 409 안내, 창은 열린 채", (await text(".report-dialog .form-error")) === "이미 신고한 대상입니다." && (await evaluate("document.querySelector('.report-dialog').open")));
  await evaluate(`${buttonByText("취소")}.click()`);
  await waitUntil("document.querySelector('.report-dialog') === null");
  check("신고 창: 취소하면 닫히고 요소도 제거", await evaluate("document.querySelector('.report-dialog') === null"));

  // 차단
  await autoConfirm();
  await evaluate(`${buttonByText("판매자 차단")}.click()`);
  await waitUntil(`!!${buttonByText("판매자 차단 해제")}`);
  check("차단: 확인 창에 차단 목록 위치 안내", (await evaluate("window.lastConfirm ?? ''")).includes("차단 목록은 내 정보 화면에서 확인·해제할 수 있어요."));
  const notice = await evaluate("({ text: document.getElementById('safety-notice').textContent, link: document.querySelector('#safety-notice a')?.getAttribute('href') })");
  check("차단: 완료 안내에 '차단 목록은 내 정보 화면에서 확인·해제할 수 있어요' + 링크", notice.text.includes("차단 목록은 내 정보 화면에서 확인·해제할 수 있어요.") && notice.link === "/static/me.html", JSON.stringify(notice));
  check("차단: 문의 버튼 대신 안내, 하트 숨김", ((await text(".post-detail__contact-login")) ?? "").startsWith("차단한 사용자의 글입니다") && (await evaluate("document.querySelector('.wish-button') === null && document.querySelector('.contact-bar').hidden")));
  check("차단: 서버에 저장", (await getJson("/users/me/blocks", seed.buyer_token)).items.map((i) => i.user.id).includes(sellerId));
  check(`${W}px: 상세 가로 스크롤 없음`, await noHorizontalScroll());
  await evaluate("document.querySelector('.post-detail__safety').scrollIntoView({ block: 'center' })");
  await screenshot("12-4-block-done.png");

  // 목록: 차단한 판매자 글이 사라짐
  await goto("/static/index.html", "document.querySelectorAll('.post-card').length > 0");
  const hrefs = await evaluate("[...document.querySelectorAll('.post-list__item a')].map(a => a.getAttribute('href'))");
  check("목록: 차단한 판매자의 글(p1, p2)은 안 보이고 내 글(p3)은 보임", !hrefs.some((h) => h.endsWith(`id=${seed.p1}`) || h.endsWith(`id=${seed.p2}`)) && hrefs.some((h) => h.endsWith(`id=${seed.p3}`)), JSON.stringify(hrefs));

  // 대화: 입력창 잠김 + 사용자 신고 + 차단 해제
  await goto(`/static/chat.html?id=${seed.c1}`, `!document.getElementById('chat').hidden && ${chatActions}.querySelector('button')`);
  await autoConfirm();
  check("대화: 내가 차단 → 입력창·전송 잠김, 안내", (await evaluate("document.getElementById('content').disabled && document.querySelector('#message-form button[type=submit]').disabled")) && (await text("#chat-blocked")) === "차단한 사용자입니다. 차단을 해제하면 다시 쪽지를 보낼 수 있어요.");
  check("대화: 지난 메시지는 그대로 보임", (await evaluate("document.querySelectorAll('#message-list li').length")) > 0);
  check("대화: '신고'·'차단 해제' 버튼", await evaluate(`!!${buttonByText("신고", chatActions)} && !!${buttonByText("차단 해제", chatActions)}`));
  check(`${W}px: 대화 가로 스크롤 없음`, await noHorizontalScroll());
  await screenshot("12-5-chat-blocked.png");
  await evaluate(`${buttonByText("신고", chatActions)}.click()`);
  await waitUntil("document.querySelector('dialog.report-dialog')?.open");
  check("대화: 사용자 신고 창 (상대 닉네임)", (await text(".report-dialog__title")) === "사용자 신고" && (await text(".report-dialog__target")) === "판매자민수님");
  await evaluate("document.querySelector('.report-dialog input[value=ABUSE]').click()");
  await evaluate(`${buttonByText("신고하기")}.click()`);
  await waitUntil("document.querySelector('.report-dialog') === null");
  check("대화: 사용자 신고 접수 안내", ((await text("#chat-safety-notice")) ?? "").startsWith("신고가 접수되었습니다."));
  await evaluate(`${buttonByText("차단 해제", chatActions)}.click()`);
  await waitUntil("!document.getElementById('content').disabled");
  check("대화: 차단 해제 → 입력창 풀림, 안내", !(await evaluate("document.getElementById('content').disabled")) && (await text("#chat-safety-notice")) === "차단을 해제했습니다." && (await evaluate("document.getElementById('chat-blocked').hidden")));

  // 상대가 대화 중에 나를 차단: 전송하면 400 안내 + 입력창 잠김 (누가 차단했는지는 말하지 않음)
  await api("POST", `/users/${buyerId}/block`, seed.seller_token);
  await evaluate("(() => { const t = document.getElementById('content'); t.value = '아직 구매 가능할까요?'; t.dispatchEvent(new Event('input')); })()");
  await evaluate("document.querySelector('#message-form button[type=submit]').click()");
  await waitUntil("document.getElementById('content').disabled");
  check("대화: 상대가 차단 → 전송 400 안내", (await text("#send-error")) === "이 사용자에게는 쪽지를 보낼 수 없습니다.", await text("#send-error"));
  check("대화: 상대가 차단 → 입력창 잠김, 같은 안내", (await evaluate("document.getElementById('content').disabled")) && (await text("#chat-blocked")) === "이 사용자에게는 쪽지를 보낼 수 없습니다.");
  await screenshot("12-6-chat-they-blocked.png");
  await api("DELETE", `/users/${buyerId}/block`, seed.seller_token);

  // 차단 목록: 내 글 → 차단 목록 → 해제
  await api("POST", `/users/${sellerId}/block`, seed.buyer_token);
  const blocksLink = ".profile-card__actions a[href=\"/static/blocks.html\"]";
  await goto("/static/me.html", `document.querySelector(${JSON.stringify(blocksLink)})`);
  check("내 글: '차단 목록' 링크", (await text(blocksLink)) === "차단 목록");
  check(`${W}px: 내 글 가로 스크롤 없음`, await noHorizontalScroll());
  await evaluate(`document.querySelector(${JSON.stringify(blocksLink)}).click()`);
  await waitUntil("location.pathname === '/static/blocks.html' && document.querySelector('.block-item')");
  await autoConfirm();
  check("차단 목록: 차단한 사용자 표시", (await text(".block-item__name")) === "판매자민수" && (await text("#result-summary")) === "총 1명");
  check("차단 목록: 이메일 없음", !(await evaluate("document.querySelector('main').textContent.includes('@')")));
  check(`${W}px: 차단 목록 가로 스크롤 없음`, await noHorizontalScroll());
  await screenshot("12-7-blocks.png");
  await evaluate(`${buttonByText("차단 해제")}.click()`);
  await waitUntil("document.querySelector('.block-item__done')");
  check("차단 목록: 해제 → '해제됨'으로 남음 + 서버 반영", (await text(".block-item__done")) === "해제됨" && (await getJson("/users/me/blocks", seed.buyer_token)).total === 0);
  await goto("/static/blocks.html", "document.getElementById('result-summary').textContent !== '불러오는 중…'");
  check("차단 목록: 새로고침하면 빈 안내", (await text("#result-summary")) === "차단한 사용자가 없습니다.");
  await goto("/static/index.html", "document.querySelectorAll('.post-card').length > 0");
  check("목록: 해제하면 판매자 글이 다시 보임", await evaluate(`[...document.querySelectorAll('.post-list__item a')].some(a => a.getAttribute('href').endsWith('id=${seed.p1}'))`));

  // 비로그인으로 차단 목록 → 로그인 화면
  await evaluate("localStorage.clear()");
  await goto("/static/blocks.html");
  await waitUntil("location.pathname === '/static/login.html'");
  check("비로그인: 차단 목록은 로그인으로", await evaluate("location.pathname === '/static/login.html'"));

  check("JS 예외·콘솔 에러 없음", exceptions.filter((e) => !String(e).includes("Failed to load resource")).length === 0, exceptions.join(" / "));
} catch (error) {
  results.push(`ERROR  ${error.stack}`);
} finally {
  writeFileSync(join(OUT, "safety-check.txt"), results.join("\n"));
  console.log(results.join("\n"));
  ws?.close();
  chrome.kill();
}
