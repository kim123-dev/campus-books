// 거래 후기 쓰기(쪽지 화면)와 프로필 화면을 모바일 폭(기본 375px)으로 확인한다.
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { api, loginApi, makeAdmin, readSeed, sleep, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const seed = readSeed(OUT);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);

// 준비: 판매자가 p1을 쪽지 상대(구매자)에게 판매 완료한다.
const buyer = (await api("GET", "/users/me", seed.buyer_token)).body;
const sold = await api("PATCH", `/posts/${seed.p1}/status`, seed.seller_token, { status: "SOLD", buyer_id: buyer.id });
check("준비: 구매자 지정 판매 완료", sold.status === 200, String(sold.status));

const browser = await startBrowser(OUT, { width: W });
const { evaluate, waitUntil, goto, screenshot, exceptions } = browser;
const setToken = (token) => evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(token)})`);
const noHorizontalScroll = () => evaluate(`document.documentElement.scrollWidth <= window.innerWidth`);
const text = (selector) => evaluate(`document.querySelector(${JSON.stringify(selector)})?.textContent ?? ""`);

try {
  // 1) 쪽지 화면의 후기 줄과 후기 창
  await goto("/static/index.html");
  await setToken(seed.buyer_token);
  await goto(`/static/chat.html?id=${seed.c1}`, "!document.querySelector('#chat-review').hidden");
  check("쪽지 화면에 후기 줄", (await text("#chat-review")).includes("후기를 남겨 주세요"), await text("#chat-review"));
  const button = await evaluate(`(() => { const r = document.querySelector("#chat-review button")?.getBoundingClientRect(); return r ? { h: Math.round(r.height), right: Math.round(r.right) } : null; })()`);
  check("후기 버튼 높이 44px 이상, 화면 안", button && button.h >= 44 && button.right <= W, JSON.stringify(button));
  check("쪽지 화면 가로 넘침 없음", await noHorizontalScroll());
  await screenshot(`review-chat-${W}.png`);

  await evaluate(`document.querySelector("#chat-review button").click()`);
  await waitUntil("document.querySelector('dialog[open]')");
  const dialog = await evaluate(`(() => { const r = document.querySelector("dialog[open]").getBoundingClientRect();
    return { left: Math.round(r.left), right: Math.round(r.right), rows: [...document.querySelectorAll("dialog[open] .report-dialog__reason")].map((x) => Math.round(x.getBoundingClientRect().height)),
      fontSize: getComputedStyle(document.querySelector("#review-content")).fontSize }; })()`);
  check("후기 창이 화면 안", dialog.left >= 15 && dialog.right <= W - 15, `${dialog.left}~${dialog.right}`);
  check("평가 줄 높이 44px 이상", dialog.rows.every((h) => h >= 44), JSON.stringify(dialog.rows));
  check("입력칸 글자 16px 이상(iOS 확대 방지)", parseFloat(dialog.fontSize) >= 16, dialog.fontSize);
  await evaluate(`[...document.querySelectorAll("dialog[open] button")].find((b) => b.textContent === "후기 남기기").click()`);
  await sleep(200);
  check("평가 없이 누르면 안내", (await text("dialog[open] .form-error")).includes("골라 주세요"));
  await screenshot(`review-dialog-${W}.png`);

  await evaluate(`document.querySelector("dialog[open] input[value='GOOD']").click()`);
  await evaluate(`(() => { const t = document.querySelector("#review-content"); t.value = "약속 시간을 잘 지켜 주셨어요"; t.dispatchEvent(new Event("input")); })()`);
  await evaluate(`[...document.querySelectorAll("dialog[open] button")].find((b) => b.textContent === "후기 남기기").click()`);
  const done = await waitUntil("document.querySelector('#chat-review')?.textContent.includes('남겼어요')");
  check("작성 후 '남겼어요'와 상대 프로필 링크", done && (await evaluate(`Boolean(document.querySelector("#chat-review a[href*='user.html']"))`)));

  // 2) 상세 화면의 판매자 링크 → 프로필
  await goto(`/static/post.html?id=${seed.p1}`, "document.querySelector('.post-detail__seller-link')");
  const href = await evaluate(`document.querySelector(".post-detail__seller-link").getAttribute("href")`);
  check("상세의 판매자 이름이 프로필 링크", /^\/static\/user\.html\?id=\d+$/.test(href), href);
  await goto(href, "document.querySelector('#review-list li')");
  check("프로필 닉네임", (await text("#profile-name")) === "판매자민수", await text("#profile-name"));
  // 기본 학점 3.5에서 좋아요 하나에 +0.1
  check("좋아요 후기 1개: 매너 학점 3.6 / 4.5, B+", (await text("#profile-manner .manner-gpa")).replace(/\s+/g, "") === "매너학점3.6/4.5B+", await text("#profile-manner"));
  check("받은 후기 표시", (await text("#review-list")).includes("약속 시간을 잘 지켜") && (await text("#review-list")).includes("판매자로서"));
  check("판매 중인 글만(판매 완료 p1 제외)", await evaluate(`![...document.querySelectorAll("#post-list a")].some((a) => a.href.endsWith("id=${seed.p1}"))`));
  check("프로필에 이메일 없음", !(await evaluate(`document.body.textContent.includes("@uicheck.ac.kr")`)));
  check("프로필 가로 넘침 없음", await noHorizontalScroll());
  await screenshot(`review-profile-${W}.png`);

  // 3) 판매자가 자기 프로필에서 받은 후기를 신고 → 관리자가 숨김
  await setToken(seed.seller_token);
  await goto(href, "document.querySelector('#review-list .review__report')");
  check("남이 쓴 후기에 신고 버튼", await evaluate(`Boolean(document.querySelector("#review-list .review__report"))`));
  await evaluate(`document.querySelector("#review-list .review__report").click()`);
  await waitUntil("document.querySelector('dialog[open]')");
  await evaluate(`document.querySelector("dialog[open] input[value='ABUSE']").click()`);
  await evaluate(`[...document.querySelectorAll("dialog[open] button")].find((b) => b.textContent === "신고하기").click()`);
  const reported = await waitUntil("!document.querySelector('#review-list .safety-notice').hidden");
  check("후기 신고 접수 안내", reported, await text("#review-list .safety-notice"));
  check("후기 카드 가로 넘침 없음", await noHorizontalScroll());
  await screenshot(`review-reported-${W}.png`);

  const PASSWORD = "check-password-123";
  await api("POST", "/auth/signup", null, { email: "admin@uicheck.ac.kr", password: PASSWORD, nickname: "관리자" });
  await makeAdmin(OUT, "admin@uicheck.ac.kr");
  await setToken(await loginApi("admin@uicheck.ac.kr", PASSWORD));
  await goto("/static/admin.html", "document.querySelector('.report-card')");
  check("관리 화면에 후기 신고 카드", (await text(".report-card__type")) === "후기 신고", await text(".report-card__type"));
  check("후기 내용 표시", (await text(".report-card")).includes("약속 시간을 잘 지켜"));
  const choices = await evaluate(`[...document.querySelectorAll(".report-card__choice span")].map((s) => s.textContent)`);
  check("조치: 기각·후기 숨김·기간 정지(글 삭제 없음)", JSON.stringify(choices) === JSON.stringify(["기각", "후기 숨김", "기간 정지"]), JSON.stringify(choices));
  check("관리 화면 가로 넘침 없음", await noHorizontalScroll());
  await screenshot(`review-admin-${W}.png`);
  await evaluate("window.confirm = (m) => { window.lastConfirm = m; return true; }");
  await evaluate(`document.querySelector(".report-card input[value='HIDE_REVIEW']").click()`);
  await evaluate(`document.querySelector(".report-card textarea").value = "욕설이 담긴 후기"`);
  await evaluate(`document.querySelector(".report-card form").requestSubmit()`);
  // 기본 탭은 미처리 신고만 보여 처리된 카드는 목록에서 빠진다. 처리 완료 안내로 확인한다.
  const hidden = await waitUntil(`document.body.textContent.includes("후기 숨김(으)로 처리했습니다")`);
  check("후기 숨김 처리", hidden);
  check("확인 창 문구", (await evaluate("window.lastConfirm ?? ''")).includes("매너 학점에서 이 후기를 뺍니다"));
  await goto(href, "document.querySelector('#reviews-summary').textContent !== '불러오는 중…'");
  check("숨긴 후기는 프로필에서 빠짐", (await text("#reviews-summary")) === "받은 후기가 없어요.", await text("#reviews-summary"));
  check("숨긴 후기는 매너 학점에서도 빠져 기본 학점 3.5", (await text("#profile-manner")).includes("3.5") && (await text("#profile-manner")).includes("기본 학점"), await text("#profile-manner"));

  // 없는 사용자 확인은 일부러 404를 내므로, 그 전까지의 오류만 본다.
  check("스크립트 오류 없음", exceptions.length === 0, exceptions.join(" | "));

  // 4) 없는 사용자
  await goto("/static/user.html?id=99999", "!document.querySelector('#page-error').hidden");
  check("없는 사용자는 안내", (await text("#page-error-text")).includes("찾을 수 없습니다"));
} catch (error) {
  results.push(`ERROR ${error.stack}`);
} finally {
  browser.close();
  writeFileSync(join(OUT, "review-check.txt"), results.join("\n") + "\n");
}
