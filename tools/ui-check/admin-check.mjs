// 13단계 신고 관리 화면을 375px 헤드리스 Chrome으로 확인한다. (DevTools 프로토콜 직접 사용, 추가 설치 없음)
import { spawn } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { BASE, CDP_PORT, CHROME_PATH, PYTHON, ROOT, cliEnv as makeCliEnv } from "./lib.mjs";

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


  // ---------- 13단계: 신고 관리·이용 정지 (375px) ----------
  const { execFileSync } = await import("node:child_process");
  const call = async (method, path, token, body) => {
    const response = await fetch(BASE + path, {
      method,
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    return { status: response.status, body: await response.json().catch(() => null) };
  };
  const loginApi = async (email, password) => {
    const response = await fetch(BASE + "/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: email, password }),
    });
    return { status: response.status, body: await response.json() };
  };
  const text = (selector) => evaluate(`document.querySelector(${JSON.stringify(selector)})?.textContent ?? null`);
  const autoConfirm = () => evaluate("window.confirm = (m) => { window.lastConfirm = m; return true; }");
  const loaded = "document.getElementById('result-summary') && document.getElementById('result-summary').textContent !== '불러오는 중…'";
  const card = (id) => `document.querySelector('[aria-labelledby="report-${id}-title"]')`;
  const headerHasAdminLink = () => evaluate("!!document.querySelector('#site-header a[href=\"/static/admin.html\"]')");
  const PASSWORD = "check-password-123";

  const sellerId = (await call("GET", "/users/me", seed.seller_token)).body.id;
  // 정지 로그인·409 확인용 사용자 (비밀번호를 알아야 로그인 화면을 시험할 수 있다)
  await call("POST", "/auth/signup", null, { email: "target@uicheck.ac.kr", password: PASSWORD, nickname: "정지대상" });
  const target = await loginApi("target@uicheck.ac.kr", PASSWORD);
  const targetId = (await call("GET", "/users/me", target.body.access_token)).body.id;

  // 구매자가 신고 4건: 판매자 글 2개, 판매자, 정지대상
  const r1 = (await call("POST", `/posts/${seed.p1}/reports`, seed.buyer_token, { reason: "FRAUD", description: "선입금을 요구해요" })).body.id;
  const r2 = (await call("POST", `/posts/${seed.p2}/reports`, seed.buyer_token, { reason: "SPAM" })).body.id;
  const r3 = (await call("POST", `/users/${sellerId}/reports`, seed.buyer_token, { reason: "ABUSE", description: "<b>욕설</b>을 했어요" })).body.id;
  const r4 = (await call("POST", `/users/${targetId}/reports`, seed.buyer_token, { reason: "OTHER", description: "다른 관리자가 먼저 처리할 신고" })).body.id;
  check("준비: 신고 4건 접수", [r1, r2, r3, r4].every(Number.isInteger), JSON.stringify([r1, r2, r3, r4]));

  // 일반 사용자: "관리" 링크 없음, admin.html은 목록으로 보냄
  await goto("/static/index.html");
  await setToken(seed.buyer_token);
  await goto("/static/index.html", "document.querySelector('#site-header nav a')");
  check("일반 사용자: 헤더에 '관리' 링크 없음", !(await headerHasAdminLink()));
  await goto("/static/admin.html");
  await waitUntil("location.pathname === '/static/index.html'");
  check("일반 사용자: admin.html → 목록으로 이동", await evaluate("location.pathname === '/static/index.html'"));
  check("일반 사용자: /admin API는 403", (await call("GET", "/admin/reports", seed.buyer_token)).status === 403);

  // 비로그인: admin.html → 로그인
  await evaluate("localStorage.clear()");
  await goto("/static/admin.html");
  await waitUntil("location.pathname === '/static/login.html'");
  check("비로그인: admin.html → 로그인 화면", await evaluate("location.pathname === '/static/login.html'"));

  // 관리자 지정 CLI
  await call("POST", "/auth/signup", null, { email: "admin@uicheck.ac.kr", password: PASSWORD, nickname: "관리자" });
  const cliEnv = makeCliEnv(OUT);
  const cliOut = execFileSync(PYTHON, ["-m", "app.cli", "make-admin", "ADMIN@uicheck.ac.kr"], { cwd: ROOT, env: cliEnv, encoding: "utf8" });
  check("CLI: make-admin 성공 안내 (대문자 이메일도 찾음)", cliOut.includes("관리자로 지정했습니다"), cliOut.trim());
  let cliFail = "";
  try {
    execFileSync(PYTHON, ["-m", "app.cli", "make-admin", "nobody@uicheck.ac.kr"], { cwd: ROOT, env: cliEnv, encoding: "utf8", stdio: "pipe" });
  } catch (error) {
    cliFail = `${error.status} ${error.stderr}`;
  }
  check("CLI: 없는 이메일은 종료 코드 1", cliFail.startsWith("1 ") && cliFail.includes("가입한 사용자가 없습니다"), cliFail.trim());
  const admin = (await loginApi("admin@uicheck.ac.kr", PASSWORD)).body.access_token;

  // 관리자: 헤더 링크와 목록
  await goto("/static/index.html");
  await setToken(admin);
  await goto("/static/index.html", "document.querySelector('#site-header nav a')");
  check("관리자: 헤더에 '관리' 링크", await headerHasAdminLink());
  await goto("/static/admin.html", `${loaded} && document.querySelectorAll('.report-card').length > 0`);
  await autoConfirm();
  check("목록: '미처리' 탭 선택, 총 4건", (await evaluate("document.querySelector('.tabs__item[aria-current=page]')?.dataset.status")) === "PENDING" && (await text("#result-summary")) === "총 4건", await text("#result-summary"));
  check("목록: 카드 4장, 최신순(#4 → #1)", JSON.stringify(await evaluate("[...document.querySelectorAll('.report-card__reason')].map(h => h.textContent.split(' ')[0])")) === JSON.stringify([`#${r4}`, `#${r3}`, `#${r2}`, `#${r1}`]));
  check("카드: 신고자 → 대상, 사본, 사유", (await evaluate(`${card(r1)}.textContent`)).includes("신고자 구매자지은 → 대상 판매자민수") && (await evaluate(`${card(r1)}.textContent`)).includes("자료구조 교재 팝니다") && (await evaluate(`${card(r1)}.querySelector('.report-card__reason').textContent`)).includes("사기"));
  check("카드: 같은 사용자 미처리 신고 2건 더", (await evaluate(`${card(r1)}.querySelector('.report-card__more')?.textContent`)) === "이 사용자에 대한 미처리 신고가 2건 더 있습니다.");
  check("카드: 설명의 HTML은 글자로만", (await evaluate(`${card(r3)}.querySelector('.report-card__description').textContent`)) === "<b>욕설</b>을 했어요" && (await evaluate(`${card(r3)}.querySelector('b') === null`)));
  check("카드: 글 신고에는 글 삭제, 사용자 신고에는 없음", (await evaluate(`!!${card(r1)}.querySelector('input[value=DELETE_POST]')`)) && (await evaluate(`${card(r3)}.querySelector('input[value=DELETE_POST]') === null`)));
  check("카드: 사본 제목은 글 링크", (await evaluate(`${card(r1)}.querySelector('.report-card__snapshot-title a')?.getAttribute('href')`)) === `/static/post.html?id=${seed.p1}`);
  check(`${W}px: 관리 화면 가로 스크롤 없음`, await noHorizontalScroll());
  const radioHeights = await evaluate(`[...${card(r1)}.querySelectorAll('.report-card__choice')].map(l => Math.round(l.getBoundingClientRect().height))`);
  check("조치 선택 줄 높이 44px 이상", radioHeights.every((h) => h >= 44), JSON.stringify(radioHeights));
  await screenshot("13-1-admin-list.png");

  // 조치 없이 처리 → 안내
  await evaluate(`${card(r1)}.querySelector('button[type=submit]').click()`);
  check("처리: 조치 없이 누르면 '조치를 골라 주세요.'", (await evaluate(`${card(r1)}.querySelector('.form-error').textContent`)) === "조치를 골라 주세요.");

  // 고른 조치에 따라 칸이 바뀜
  const pick = (id, action) => evaluate(`(() => { const r = ${card(id)}.querySelector('input[value=${action}]'); r.click(); })()`);
  await pick(r1, "SUSPEND");
  check("정지 선택: 기간 칸과 '함께 처리' 보임", (await evaluate(`!${card(r1)}.querySelector('.report-card__days').hidden && !${card(r1)}.querySelector('.report-card__together').hidden`)));
  await pick(r1, "DELETE_POST");
  check("글 삭제 선택: 기간 칸·'함께 처리' 숨김", (await evaluate(`${card(r1)}.querySelector('.report-card__days').hidden && ${card(r1)}.querySelector('.report-card__together').hidden`)));
  await screenshot("13-2-admin-choose.png");

  // 글 삭제 처리
  await evaluate(`${card(r1)}.querySelector('textarea').value = '선입금 사기 확인'`);
  await evaluate(`${card(r1)}.querySelector('button[type=submit]').click()`);
  await waitUntil("!document.getElementById('admin-notice').hidden && document.querySelectorAll('.report-card').length === 3");
  check("글 삭제: 확인 창에 글 제목", (await evaluate("window.lastConfirm ?? ''")).includes("자료구조 교재 팝니다"), await evaluate("window.lastConfirm"));
  check("글 삭제: 완료 안내", ((await text("#admin-notice")) ?? "").startsWith(`신고 #${r1}을(를) 글 삭제(으)로 처리했습니다.`), await text("#admin-notice"));
  check("글 삭제: 글이 404, 목록 다시 그림(3건)", (await call("GET", `/posts/${seed.p1}`)).status === 404 && (await text("#result-summary")) === "총 3건");

  // 기간 정지 + 같은 사용자 함께 처리
  await autoConfirm();
  await pick(r2, "SUSPEND");
  await evaluate(`(() => { const s = ${card(r2)}.querySelector('select'); s.value = '7'; s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
  check("정지: '함께 처리' 문구에 남은 건수(1건)", ((await evaluate(`${card(r2)}.querySelector('.report-card__together').textContent`)) ?? "").includes("미처리 신고 1건도 함께 처리"));
  await evaluate(`${card(r2)}.querySelector('.report-card__together input').click()`);
  await evaluate(`${card(r2)}.querySelector('textarea').value = '반복 사기'`);
  await evaluate(`${card(r2)}.querySelector('button[type=submit]').click()`);
  await waitUntil("document.querySelectorAll('.report-card').length === 1");
  const confirmText = await evaluate("window.lastConfirm ?? ''");
  check("정지: 확인 창에 대상·기간·함께 처리", confirmText.includes("판매자민수님을(를) 7일 동안 정지") && confirmText.includes("미처리 신고 1건도 같은 조치로"), confirmText);
  check("정지: 완료 안내(함께 1건, 종료 시각)", /함께 처리한 신고 1건\. .+까지 정지됩니다\.$/.test((await text("#admin-notice")) ?? ""), await text("#admin-notice"));
  check("정지: 미처리에는 #4만 남음", JSON.stringify(await evaluate("[...document.querySelectorAll('.report-card__reason')].map(h => h.textContent.split(' ')[0])")) === JSON.stringify([`#${r4}`]));

  // 다른 관리자가 먼저 처리 → 409 안내
  const otherAdminResolve = await call("POST", `/admin/reports/${r4}/resolve`, admin, { action: "SUSPEND", suspend_days: 1, note: "다른 관리자 처리" });
  check("준비: 다른 곳에서 #4 먼저 정지 처리", otherAdminResolve.status === 200);
  await autoConfirm();
  await pick(r4, "DISMISS");
  await evaluate(`${card(r4)}.querySelector('button[type=submit]').click()`);
  await waitUntil(`!${card(r4)}.querySelector('.form-error').hidden`);
  check("409: 카드 안에 '이미 처리된 신고입니다.'", (await evaluate(`${card(r4)}.querySelector('.form-error').textContent`)) === "이미 처리된 신고입니다." && (await evaluate(`!${card(r4)}.querySelector('button[type=submit]').disabled`)));
  await screenshot("13-3-admin-409.png");

  // 처리됨 탭
  await evaluate("document.querySelector('.tabs__item[data-status=RESOLVED]').click()");
  await waitUntil(`${loaded} && location.search.includes('RESOLVED') && document.querySelectorAll('.report-card--resolved').length === 4`);
  check("처리됨 탭: 4건 모두 흐리게", (await evaluate("document.querySelectorAll('.report-card--resolved').length")) === 4 && (await evaluate("getComputedStyle(document.querySelector('.report-card--resolved')).opacity")) === "0.6");
  check("처리됨: 처리 기록(조치 · 관리자 · 시각) + 메모", ((await evaluate(`${card(r1)}.querySelector('.report-card__resolution-line').textContent`)) ?? "").startsWith("글 삭제 · 관리자 · ") && (await evaluate(`${card(r1)}.querySelector('.report-card__note').textContent`)) === "메모: 선입금 사기 확인");
  check("처리됨: 함께 처리 표시", (await evaluate(`${card(r3)}.querySelector('.report-card__resolution-with')?.textContent`)) === `신고 #${r2}와 함께 처리`);
  check("처리됨: 삭제된 글은 링크 대신 '글 삭제됨'", (await evaluate(`${card(r1)}.querySelector('.report-card__snapshot-title a') === null && ${card(r1)}.querySelector('.report-card__deleted')?.textContent === '글 삭제됨'`)));
  check("처리됨: 처리 버튼 없음", await evaluate("document.querySelectorAll('.report-card form').length === 0"));
  check("처리됨: 대상의 정지 중 표시", ((await evaluate(`${card(r3)}.querySelector('.report-card__suspended')?.textContent`)) ?? "").endsWith("까지 정지 중"));
  check(`${W}px: 처리됨 화면 가로 스크롤 없음`, await noHorizontalScroll());
  await screenshot("13-4-admin-resolved.png");
  await goto("/static/admin.html?status=ALL", loaded);
  check("전체 탭: 주소로 열어도 탭 선택·4건", (await evaluate("document.querySelector('.tabs__item[aria-current=page]')?.dataset.status")) === "ALL" && (await text("#result-summary")) === "총 4건");

  // 정지된 판매자: 이미 받은 토큰으로 화면 사용
  await setToken(seed.seller_token);
  await goto("/static/index.html", "document.querySelector('.site-notice')");
  const siteNotice = (await text(".site-notice")) ?? "";
  check("정지: 헤더 아래 정지 안내", /^\d+월 \d+일 \d{2}:\d{2}까지 이용이 정지된 상태입니다\./.test(siteNotice), siteNotice);
  check("정지: 목록(읽기)은 보임", (await evaluate("document.querySelectorAll('.post-card').length")) > 0);
  check(`${W}px: 정지 안내가 있어도 가로 스크롤 없음`, await noHorizontalScroll());
  await screenshot("13-5-suspended-list.png");
  await goto(`/static/chat.html?id=${seed.c3}`, "!document.getElementById('chat').hidden && !document.getElementById('chat-blocked').hidden");
  check("정지: 대화는 보이고 입력창 잠금 + 안내", (await evaluate("document.getElementById('content').disabled")) && ((await text("#chat-blocked")) ?? "").includes("까지 이용이 정지된 상태입니다") && (await evaluate("document.querySelectorAll('#message-list li').length")) > 0);
  await screenshot("13-6-suspended-chat.png");
  check("정지: 쓰기 API 403", (await call("PATCH", `/posts/${seed.p2}`, seed.seller_token, { price: 1000 })).status === 403);

  // 정지된 사용자 로그인 화면
  await evaluate("localStorage.clear()");
  await goto("/static/login.html", "document.getElementById('login-form')");
  await evaluate("document.getElementById('username').value = 'target@uicheck.ac.kr'; document.getElementById('password').value = " + JSON.stringify(PASSWORD));
  await evaluate("document.querySelector('#login-form button[type=submit]').click()");
  await waitUntil("!document.getElementById('login-error').hidden");
  const loginError = (await text("#login-error")) ?? "";
  check("정지: 로그인 화면에 '○월 ○일 ○○:○○까지 이용이 정지되었습니다.'", /^\d+월 \d+일 \d{2}:\d{2}까지 이용이 정지되었습니다\.$/.test(loginError), loginError);
  check("정지: 로그인 실패 시 토큰 저장 안 됨, 화면 그대로", (await evaluate("location.pathname === '/static/login.html' && !localStorage.getItem('campus-books.token')")));
  await screenshot("13-7-suspended-login.png");

  check("JS 예외·콘솔 에러 없음", exceptions.filter((e) => !String(e).includes("Failed to load resource")).length === 0, exceptions.join(" / "));
} catch (error) {
  results.push(`ERROR  ${error.stack}`);
} finally {
  writeFileSync(join(OUT, "admin-check.txt"), results.join("\n"));
  console.log(results.join("\n"));
  ws?.close();
  chrome.kill();
}
