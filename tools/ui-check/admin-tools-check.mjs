// 관리 화면(메뉴·신고 처리 사유·관리 기록)을 모바일 폭(기본 375px)으로 확인한다.
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { api, loginApi, makeAdmin, readSeed, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const seed = readSeed(OUT);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);

// 준비: 관리자 계정과 신고 2건 (구매자가 판매자의 글 p2를, 판매자가 구매자의 글 p3를 신고)
const PASSWORD = "check-password-123";
await api("POST", "/auth/signup", null, { email: "admin@uicheck.ac.kr", password: PASSWORD, nickname: "관리자" });
await makeAdmin(OUT, "admin@uicheck.ac.kr");
const admin = await loginApi("admin@uicheck.ac.kr", PASSWORD);
const r1 = (await api("POST", `/posts/${seed.p2}/reports`, seed.buyer_token, { reason: "SPAM" })).body.id;
const r2 = (await api("POST", `/posts/${seed.p3}/reports`, seed.seller_token, { reason: "FRAUD" })).body.id;
check("준비: 신고 2건", Boolean(r1 && r2));

const browser = await startBrowser(OUT, { width: W });
const { evaluate, waitUntil, goto, screenshot, exceptions } = browser;
const setToken = (token) => evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(token)})`);
const noHorizontalScroll = () => evaluate(`document.documentElement.scrollWidth <= window.innerWidth`);
const text = (selector) => evaluate(`document.querySelector(${JSON.stringify(selector)})?.textContent ?? ""`);
const autoConfirm = () => evaluate("window.confirm = (m) => { window.lastConfirm = m; return true; }");
const card = (id) => `[...document.querySelectorAll('.report-card')].find((c) => c.querySelector('.report-card__reason').textContent.startsWith('#${id} '))`;
// 관리 메뉴: 항목 이름, 현재 화면 표시, 누르는 곳 높이
const navInfo = () =>
  evaluate(`(() => { const items = [...document.querySelectorAll("#admin-nav .admin-nav__item")];
    return { labels: items.map((a) => a.textContent), current: document.querySelector("#admin-nav [aria-current=page]")?.textContent ?? null,
      minHeight: Math.min(...items.map((a) => Math.round(a.getBoundingClientRect().height))) }; })()`);

try {
  // 1) 일반 사용자는 관리 기록 화면에 들어올 수 없다.
  await goto("/static/index.html");
  await setToken(seed.buyer_token);
  await goto("/static/admin-log.html", "location.pathname === '/static/index.html'");
  check("일반 사용자: 관리 기록 → 목록으로", (await evaluate("location.pathname")) === "/static/index.html");

  // 2) 신고 화면: 관리 메뉴, 강제 조치의 사유 필수
  await setToken(admin);
  await goto("/static/admin.html", "document.querySelectorAll('.report-card').length === 2");
  const nav = await navInfo();
  check("신고 화면: 관리 메뉴와 현재 화면", nav.current === "신고" && nav.labels.includes("기록"), JSON.stringify(nav));
  check("관리 메뉴: 누르는 곳 44px 이상", nav.minHeight >= 44, String(nav.minHeight));
  await autoConfirm();
  await evaluate(`${card(r1)}.querySelector('input[value=SUSPEND]').click()`);
  check("정지 선택: 사유 칸이 '(필수)'", (await evaluate(`${card(r1)}.querySelector('.field label').textContent`)) === "처리 사유 (필수)");
  await evaluate(`${card(r1)}.querySelector('button[type=submit]').click()`);
  const error = await evaluate(`${card(r1)}.querySelector('.form-error').textContent`);
  check("사유 없이 정지: 보내기 전에 안내", error.includes("처리 사유를 입력해 주세요"), error);
  check("사유 없이 정지: 서버에 보내지 않음(확인 창 없음)", (await evaluate("window.lastConfirm ?? null")) === null);
  await evaluate(`${card(r1)}.querySelector('input[value=DISMISS]').click()`);
  check("기각 선택: 사유 칸이 '(기각은 선택)'", (await evaluate(`${card(r1)}.querySelector('.field label').textContent`)) === "처리 사유 (기각은 선택)");
  await evaluate(`${card(r1)}.querySelector('input[value=SUSPEND]').click()`);
  await evaluate(`${card(r1)}.querySelector('textarea').value = '광고 글 반복'`);
  await evaluate(`${card(r1)}.querySelector('button[type=submit]').click()`);
  check("사유를 넣고 정지 처리", await waitUntil("!document.getElementById('admin-notice').hidden"), await text("#admin-notice"));
  await evaluate(`${card(r2)}.querySelector('input[value=DISMISS]').click()`);
  await evaluate(`${card(r2)}.querySelector('button[type=submit]').click()`);
  check("사유 없이 기각 처리", await waitUntil("document.querySelectorAll('.report-card').length === 0"));
  check("신고 화면 가로 넘침 없음", await noHorizontalScroll());
  await screenshot(`admin-tools-reports-${W}.png`);

  // 3) 관리 기록 화면
  await goto("/static/admin-log.html", "document.querySelectorAll('#log-list li').length === 2");
  check("기록: 2건, 최신순(기각 → 정지)", JSON.stringify(await evaluate(`[...document.querySelectorAll("#log-list .admin-badge")].map((b) => b.textContent)`)) === JSON.stringify(["신고 기각", "기간 정지"]));
  const suspendCard = await evaluate(`document.querySelectorAll("#log-list li")[1].textContent`);
  check("기록: 관리자 → 대상, 사유, 정지 일수", suspendCard.includes("관리자 → 판매자민수") && suspendCard.includes("사유: 광고 글 반복") && suspendCard.includes("1일 정지"), suspendCard);
  check("기록: 기각은 '사유 없음'", (await evaluate(`document.querySelectorAll("#log-list li")[0].textContent`)).includes("사유 없음"));
  check("기록: 이메일 없음", !(await evaluate(`document.body.textContent.includes("@uicheck.ac.kr")`)));
  check("기록: 관리 메뉴 현재 화면", (await navInfo()).current === "기록");
  check("기록 화면 가로 넘침 없음", await noHorizontalScroll());
  await screenshot(`admin-tools-log-${W}.png`);
  await evaluate(`(() => { const s = document.getElementById("filter-action"); s.value = "SUSPEND"; s.dispatchEvent(new Event("change")); })()`);
  await waitUntil("location.search.includes('action=SUSPEND') && document.querySelectorAll('#log-list li').length === 1");
  check("기록: 조치 필터(정지만 1건)", (await text("#result-summary")) === "총 1건", await text("#result-summary"));
  const tab = await evaluate(`document.querySelector(".tab-bar [aria-current=page]")?.textContent ?? ""`);
  check("하단 탭 바: 관리 화면은 '내 정보' 탭", tab.includes("내 정보"), tab);

  check("자바스크립트 오류 없음", exceptions.length === 0, exceptions.join(" | "));
} catch (error) {
  results.push(`ERROR  ${error.stack ?? error}`);
} finally {
  browser.close();
  writeFileSync(join(OUT, "admin-tools-check.txt"), results.join("\n") + "\n");
}
