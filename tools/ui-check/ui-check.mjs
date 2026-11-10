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

  // ---------- 상세 화면: 로그아웃 상태 ----------
  await goto("/static/index.html");
  await evaluate("localStorage.clear()");
  await goto(`/static/post.html?id=${seed.p1}`, "!document.getElementById('post-detail').hidden");
  const guestText = await evaluate("document.querySelector('.post-detail__contact')?.textContent ?? ''");
  const guestLink = await evaluate("document.querySelector('.post-detail__contact-login a')?.getAttribute('href') ?? ''");
  check("비로그인: 로그인 안내 문구", guestText.includes("로그인하면 쪽지로 문의하거나 연락 방법을 볼 수 있어요"));
  check("비로그인: 로그인 링크에 next 포함", guestLink.includes("next=%2Fstatic%2Fpost.html%3Fid%3D"), guestLink);
  check("비로그인: 문의하기 버튼 없음", !(await evaluate("[...document.querySelectorAll('button')].some(b => b.textContent.includes('문의하기'))")));
  await screenshot("1-detail-guest.png");

  // ---------- 상세 화면: 판매자 본인 ----------
  await setToken(seed.seller_token);
  await goto(`/static/post.html?id=${seed.p1}`, "!document.getElementById('post-detail').hidden");
  await waitUntil("document.getElementById('nav-messages')");
  check("판매자 본인 글: 문의하기 버튼 없음", !(await evaluate("[...document.querySelectorAll('button')].some(b => b.textContent.includes('문의하기'))")));

  // ---------- 상세 화면: 구매자 ----------
  await setToken(seed.buyer_token);
  await goto(`/static/post.html?id=${seed.p1}`, "!document.getElementById('post-detail').hidden");
  await waitUntil("!document.getElementById('nav-unread')?.hidden");
  const badge = await evaluate("document.getElementById('nav-unread')?.textContent");
  const badgeLabel = await evaluate("document.getElementById('nav-messages')?.getAttribute('aria-label')");
  check("헤더: 쪽지 배지 표시", badge === "4", `배지 ${badge}, aria-label "${badgeLabel}"`);
  // 모바일은 문의 버튼이 하단 연락 바로 옮겨지므로 id로 찾는다.
  const buttons = await evaluate("[document.getElementById('inquiry-button'), ...document.querySelectorAll('.post-detail__contact-actions > :not(#inquiry-button)')].filter(Boolean).map(b => b.textContent + '|' + b.className)");
  check("구매자: 문의하기(주 버튼) + 오픈채팅(보조 버튼)", buttons.length === 2 && buttons[0].includes("button--primary"), buttons.join(", "));
  check(`${W}px: 가로 스크롤 없음 (상세)`, await noHorizontalScroll());
  await screenshot("2-detail-buyer.png");

  // ---------- 문의하기 → 대화 화면 ----------
  await evaluate("[...document.querySelectorAll('button')].find(b => b.textContent.includes('문의하기')).click()");
  await waitUntil(`location.pathname === '/static/chat.html' && !document.getElementById('chat').hidden`);
  check("문의하기: 기존 대화방으로 이동", await evaluate(`location.search === '?id=${seed.c1}'`), await evaluate("location.href"));
  await sleep(300);
  check("대화: 처음 30개 불러옴", (await evaluate("document.querySelectorAll('.message').length")) === 30);
  check("대화: 이전 메시지 보기 버튼 표시", await evaluate("!document.getElementById('older-button').hidden"));
  check("대화: 맨 아래로 스크롤됨", await evaluate("(() => { const s = document.getElementById('chat-scroll'); return s.scrollHeight - s.scrollTop - s.clientHeight < 2; })()"));
  check("대화: 내/상대 말풍선 구분", await evaluate("document.querySelectorAll('.message--mine').length > 0 && document.querySelectorAll('.message--theirs').length > 0"));
  check("대화: 줄바꿈 유지", await evaluate("[...document.querySelectorAll('.message__bubble')].some(b => b.textContent.includes('\\n'))"));
  check("대화: 개인정보 안내 표시", (await evaluate("document.querySelector('.chat__privacy').textContent")).includes("개인정보"));
  await waitUntil("document.getElementById('nav-unread')?.textContent === '1'");
  check("대화: 읽은 뒤 헤더 배지 4 → 1 (다른 방 1개 남음)", (await evaluate("document.getElementById('nav-unread').textContent")) === "1");
  check(`${W}px: 가로 스크롤 없음 (대화)`, await noHorizontalScroll());
  await screenshot("3-chat.png");

  // ---------- 이전 메시지 (위로 스크롤) ----------
  const firstVisibleBefore = await evaluate("document.querySelector('.message').dataset.id");
  await evaluate("document.getElementById('chat-scroll').scrollTop = 0");
  await waitUntil("document.querySelectorAll('.message').length === 40");
  check("이전 메시지: 맨 위 스크롤로 10개 더 불러옴", (await evaluate("document.querySelectorAll('.message').length")) === 40);
  check("이전 메시지: 버튼 숨김(더 없음)", await evaluate("document.getElementById('older-button').hidden"));
  check("이전 메시지: 보던 위치 유지 (scrollTop > 0)", (await evaluate("document.getElementById('chat-scroll').scrollTop")) > 0,
    `scrollTop=${await evaluate("document.getElementById('chat-scroll').scrollTop")}, 원래 첫 메시지 id=${firstVisibleBefore}`);
  check("이전 메시지: id 순서 유지", await evaluate("(() => { const ids = [...document.querySelectorAll('.message')].map(m => Number(m.dataset.id)); return ids.every((v, i) => i === 0 || ids[i - 1] < v); })()"));

  // ---------- 폴링: 위쪽을 보는 중 새 메시지 → "새 메시지" 버튼 ----------
  await api("POST", `/conversations/${seed.c1}/messages`, seed.seller_token, { content: "폴링으로 도착한 메시지" });
  await waitUntil("[...document.querySelectorAll('.message__bubble')].some(b => b.textContent === '폴링으로 도착한 메시지')", 8000);
  check("폴링: 5초 안에 새 메시지 표시", await evaluate("document.querySelector('.message:last-child .message__bubble').textContent === '폴링으로 도착한 메시지'"));
  {
    const polled = await evaluate(`(() => {
      const item = [...document.querySelectorAll('.message')].find(m => m.querySelector('.message__bubble').textContent === '폴링으로 도착한 메시지');
      const box = document.getElementById('chat-scroll').getBoundingClientRect();
      const bubble = item.querySelector('.message__bubble').getBoundingClientRect();
      return { className: item.className, color: getComputedStyle(item.querySelector('.message__bubble')).backgroundColor,
               leftGap: Math.round(bubble.left - box.left), rightGap: Math.round(box.right - bubble.right) };
    })()`);
    check("폴링: 받은 상대 메시지가 왼쪽(상대) 말풍선", polled.className.includes("message--theirs") && !polled.className.includes("message--mine") && polled.leftGap < polled.rightGap && polled.color === "rgb(255, 255, 255)",
      JSON.stringify(polled));
  }
  check("폴링: 위쪽 보는 중이면 '새 메시지 ↓' 버튼", await evaluate("!document.getElementById('new-message-button').hidden"));
  await evaluate("document.getElementById('new-message-button').click()");
  check("새 메시지 버튼: 누르면 맨 아래로", await waitUntil("document.getElementById('new-message-button').hidden"));

  // ---------- 탭 숨김: 폴링 멈춤 ----------
  await evaluate("Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }); document.dispatchEvent(new Event('visibilitychange'))");
  await api("POST", `/conversations/${seed.c1}/messages`, seed.seller_token, { content: "숨긴 동안 온 메시지" });
  await sleep(6500);
  check("탭 숨김: 6.5초 동안 폴링 안 함", !(await evaluate("[...document.querySelectorAll('.message__bubble')].some(b => b.textContent === '숨긴 동안 온 메시지')")));
  await evaluate("Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); document.dispatchEvent(new Event('visibilitychange'))");
  check("탭 다시 보임: 바로 확인", await waitUntil("[...document.querySelectorAll('.message__bubble')].some(b => b.textContent === '숨긴 동안 온 메시지')", 2000));

  // ---------- 전송 ----------
  await evaluate("{ const t = document.getElementById('content'); t.value = '화면에서 보낸 메시지'; t.dispatchEvent(new Event('input')) }");
  check("전송: 글자 수 표시", (await evaluate("document.getElementById('content-count').textContent")) === "11 / 1000");
  await evaluate("document.getElementById('message-form').requestSubmit()");
  check("전송: 내 말풍선으로 추가", await waitUntil("document.querySelector('.message:last-child')?.classList.contains('message--mine') && document.querySelector('.message:last-child .message__bubble').textContent === '화면에서 보낸 메시지'"));
  check("전송: 입력창 비움", (await evaluate("document.getElementById('content').value")) === "");
  await evaluate("document.getElementById('content').focus()");
  await sleep(300);
  // 모바일은 입력 중(is-typing) 헤더와 '← 쪽지함'을 일부러 접으므로, 그때는 입력창이 화면 안에 있는지 본다.
  check(`${W}px: 입력창을 누르고 보낸 뒤에도 페이지가 밀리지 않음 (PC: '← 쪽지함'이 헤더 아래 / 모바일: 입력 중 헤더 접음)`, await evaluate("(() => { if (scrollY !== 0) return false; if (document.body.classList.contains('is-typing')) return document.getElementById('site-header').getClientRects().length === 0 && document.getElementById('content').getBoundingClientRect().bottom <= innerHeight; const h = document.getElementById('site-header').getBoundingClientRect(); const b = document.querySelector('.back-link a').getBoundingClientRect(); return b.top >= h.bottom; })()"),
    JSON.stringify(await evaluate("({ scrollY, pageHeight: document.documentElement.scrollHeight, viewport: innerHeight })")));
  const count = await evaluate("document.querySelectorAll('.message').length");
  await sleep(5500);
  check("전송: 폴링이 같은 메시지를 중복으로 그리지 않음", (await evaluate("document.querySelectorAll('.message').length")) === count);

  // 빈 내용 → 422 메시지
  await evaluate("document.getElementById('content').value = '   '; document.getElementById('message-form').requestSubmit()");
  await waitUntil("!document.querySelector('[data-error-for=content]').hidden");
  check("전송: 공백만 → 칸 아래 에러", await evaluate("document.querySelector('[data-error-for=content]').textContent"), await evaluate("document.querySelector('[data-error-for=content]').textContent"));

  // ---------- 429 ----------
  for (let i = 0; i < 4; i++) await api("POST", `/conversations/${seed.c1}/messages`, seed.buyer_token, { content: `연속 ${i}` });
  await evaluate("{ const t = document.getElementById('content'); t.value = '도배 테스트'; t.dispatchEvent(new Event('input')); document.getElementById('message-form').requestSubmit() }");
  await waitUntil("document.getElementById('send-error').textContent.includes('초 후 다시 보낼 수 있어요')");
  const errorText = await evaluate("document.getElementById('send-error').textContent");
  check("429: 서버 메시지 + 남은 시간 표시", errorText.includes("너무 빠르게") && /\d+초 후/.test(errorText), errorText);
  check("429: 보내기 버튼 잠김", await evaluate("document.querySelector('#message-form button[type=submit]').disabled"));
  check("429: 입력 내용 유지", (await evaluate("document.getElementById('content').value")) === "도배 테스트");
  await sleep(300);
  check("429: 안내가 생겨 영역이 줄어도 마지막 메시지가 잘리지 않음", await evaluate("(() => { const box = document.getElementById('chat-scroll').getBoundingClientRect(); const last = document.querySelector('.message:last-child').getBoundingClientRect(); return last.bottom <= box.bottom + 1; })()"));
  await screenshot("4-chat-429.png");
  await sleep(2100);
  const later = await evaluate("document.getElementById('send-error').textContent");
  check("429: 남은 초가 줄어듦", later !== errorText, later);
  await setToken(seed.seller_token); // 같은 브라우저 다른 탭에서 판매자로 로그인한 상황
  await api("POST", `/conversations/${seed.c1}/messages`, seed.seller_token, { content: "계정 바뀐 뒤 판매자 메시지" });
  await waitUntil("!document.getElementById('page-error').hidden", 8000);
  check("계정 바뀜: 폴링을 멈추고 안내", (await evaluate("document.getElementById('page-error-text').textContent")).includes("로그인 상태가 바뀌어"),
    await evaluate("document.getElementById('page-error-text').textContent"));
  check("계정 바뀜: 상대 메시지를 내 말풍선으로 그리지 않음", !(await evaluate("[...document.querySelectorAll('.message--mine .message__bubble')].some(b => b.textContent === '계정 바뀐 뒤 판매자 메시지')")));
  await setToken(seed.buyer_token);

  // ---------- 쪽지함 ----------
  await goto("/static/conversations.html", "document.querySelectorAll('.conversation-card').length > 0");
  const cards = await evaluate("[...document.querySelectorAll('.conversation-card')].map(c => c.innerText.replace(/\\s+/g, ' '))");
  check("쪽지함: 대화방 3개", cards.length === 3, "");
  check("쪽지함: 최신 메시지순 (방금 대화한 방이 맨 위)", cards[0].includes("판매자민수") && cards[0].includes("자료구조"), cards[0]);
  check("쪽지함: 받은 문의 역할 표시", cards.some((c) => c.includes("받은 문의")));
  check("쪽지함: 안 읽은 개수 배지", await evaluate("document.querySelectorAll('.count-badge').length >= 1"));
  check("쪽지함: <script> 문자열이 글자로 표시", cards.some((c) => c.includes("<script>alert(1)</script>")));
  check(`${W}px: 가로 스크롤 없음 (쪽지함)`, await noHorizontalScroll());
  await screenshot("5-conversations.png");

  // ---------- 판매 완료 글 / 삭제된 글 ----------
  await api("PATCH", `/posts/${seed.p2}/status`, seed.seller_token, { status: "SOLD" });
  await goto(`/static/post.html?id=${seed.p2}`, "!document.getElementById('post-detail').hidden");
  check("판매 완료 글: 연락 영역 숨김", await evaluate("document.querySelector('.post-detail__contact') === null"));
  await setToken(seed.seller_token);
  await api("DELETE", `/posts/${seed.p2}`, seed.seller_token);
  await goto("/static/conversations.html", "document.querySelectorAll('.conversation-card').length > 0");
  check("삭제된 글: 쪽지함에 '삭제된 글' 표시", await evaluate("[...document.querySelectorAll('.conversation-card__post--deleted')].some(p => p.textContent === '삭제된 글')"));
  await goto(`/static/chat.html?id=${seed.c2}`, "!document.getElementById('chat').hidden");
  check("삭제된 글: 대화 화면 머리에도 표시", (await evaluate("document.getElementById('chat-post').textContent")).includes("삭제된 글"));

  // ---------- 남의 대화방 / 잘못된 주소 ----------
  await goto("/static/chat.html?id=9999", "!document.getElementById('page-error').hidden");
  check("없는 대화방: 서버 메시지", (await evaluate("document.getElementById('page-error-text').textContent")) === "대화방을 찾을 수 없습니다.");
  await goto("/static/chat.html?id=abc", "!document.getElementById('page-error').hidden");
  check("잘못된 주소: 안내", (await evaluate("document.getElementById('page-error-text').textContent")) === "대화방 주소가 올바르지 않습니다.");

  check("JS 예외·콘솔 에러 없음", exceptions.filter((e) => !String(e).includes("Failed to load resource")).length === 0, exceptions.join(" / "));
} catch (error) {
  results.push(`ERROR  ${error.stack}`);
} finally {
  writeFileSync(join(OUT, "ui-check.txt"), results.join("\n"));
  console.log(results.join("\n"));
  ws?.close();
  chrome.kill();
}
