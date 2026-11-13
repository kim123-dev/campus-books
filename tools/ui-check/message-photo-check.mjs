// 쪽지 사진(보내기·썸네일·크게 보기·쪽지함 미리보기·관리자 신고 사진)을 헤드리스 Chrome으로 확인한다.
// 사용: WIDTH=375 tools/ui-check/run.sh message-photo-check
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { BASE, FIXTURES, api, loginApi, makeAdmin, readSeed, sleep, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const seed = readSeed(OUT);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);

const b = await startBrowser(OUT, { width: W });
const noScroll = () => b.evaluate(`document.documentElement.scrollWidth <= ${W}`);
const room = seed.c2;
const photoCount = () => b.evaluate("document.querySelectorAll('.message__photo').length");
const loadedCount = () => b.evaluate("document.querySelectorAll('.message__photo.is-loaded').length");
const rect = (sel) => b.evaluate(`(() => { const r = document.querySelector(${JSON.stringify(sel)}).getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right), Math.round(r.width), Math.round(r.height)]; })()`);

try {
  await b.goto("/static/index.html");
  await b.evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(seed.buyer_token)})`);
  await b.goto(`/static/chat.html?id=${room}`, "document.querySelectorAll('.message').length > 0");

  // ---------- 입력줄: 사진 버튼 ----------
  const photoBtn = await rect("#photo-button");
  const textareaBox = await rect("#content");
  const sendBox = await rect('#message-form button[type="submit"]');
  check("입력줄: 사진 버튼 44px 이상", photoBtn[2] >= 44 && photoBtn[3] >= 44, JSON.stringify(photoBtn));
  check(`${W}px: 사진·입력칸·보내기가 한 줄`, photoBtn[1] <= textareaBox[0] && textareaBox[1] <= sendBox[0], JSON.stringify([photoBtn, textareaBox, sendBox]));
  check(`${W}px: 대화 가로 스크롤 없음`, await noScroll());
  await b.screenshot(`message-photo-input-${W}.png`);

  // ---------- 사진 보내기 ----------
  const { root } = await b.send("DOM.getDocument", { depth: 0 });
  const { nodeId } = await b.send("DOM.querySelector", { nodeId: root.nodeId, selector: "#photo-input" });
  await b.send("DOM.setFileInputFiles", { nodeId, files: [join(FIXTURES, "a.jpg")] });
  check("보내기: 사진 메시지가 내 말풍선 쪽에 나타남", await b.waitUntil("document.querySelector('.message--mine .message__photo')", 15000));
  check("보내기: 썸네일을 받아 보여줌", await b.waitUntil("document.querySelector('.message--mine .message__photo.is-loaded img')?.naturalWidth > 0", 8000));
  check("보내기: 썸네일 주소는 blob:이고 받은 뒤 해제", await b.evaluate(`(() => { const img = document.querySelector('.message--mine .message__photo img'); return img.src.startsWith('blob:'); })()`));
  check("보내기: 버튼이 '사진'으로 돌아오고 다시 누를 수 있음", await b.waitUntil("document.getElementById('photo-button').textContent === '사진' && !document.getElementById('photo-button').disabled"));
  const thumb = await rect(".message--mine .message__photo");
  check(`${W}px: 썸네일이 화면 안`, thumb[0] >= 0 && thumb[1] <= W, JSON.stringify(thumb));
  check(`${W}px: 사진 보낸 뒤 가로 스크롤 없음`, await noScroll());
  await b.screenshot(`message-photo-sent-${W}.png`);

  // 사진 주소에 토큰 없이 접근하면 401, 공개 주소(/images)로는 열 수 없다.
  const messages = await api("GET", `/conversations/${room}/messages`, seed.buyer_token);
  const photoMessage = messages.body.items.filter((m) => m.has_image).at(-1);
  check("API: 메시지에 has_image", !!photoMessage);
  check("API: 토큰 없이 사진 요청은 401", (await fetch(`${BASE}/messages/${photoMessage.id}/image`)).status === 401);
  const withToken = await fetch(`${BASE}/messages/${photoMessage.id}/image`, { headers: { Authorization: `Bearer ${seed.buyer_token}` } });
  check("API: 참여자 요청은 200, private no-store", withToken.status === 200 && withToken.headers.get("cache-control") === "private, no-store");

  // ---------- 크게 보기 ----------
  await b.evaluate("document.querySelector('.message--mine .message__photo').click()");
  check("크게 보기: 창이 열리고 큰 사진을 받음", await b.waitUntil("document.querySelector('dialog.photo-viewer[open] img')?.naturalWidth > 400", 8000));
  const viewer = await rect("dialog.photo-viewer");
  check(`${W}px: 크게 보기 창이 화면 안`, viewer[0] >= 0 && viewer[1] <= W, JSON.stringify(viewer));
  const closeBox = await rect(".photo-viewer__close");
  check("크게 보기: 닫기 버튼 44px", closeBox[3] >= 44, JSON.stringify(closeBox));
  await b.screenshot(`message-photo-viewer-${W}.png`);
  await b.evaluate("document.querySelector('.photo-viewer__close').click()");
  check("크게 보기: 닫으면 초점이 사진으로", await b.waitUntil("!document.querySelector('dialog.photo-viewer') && document.activeElement?.classList.contains('message__photo')"));

  // ---------- 상대 화면: 사진 메시지에도 "⋯" 신고 ----------
  await b.evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(seed.seller_token)})`);
  await b.goto(`/static/chat.html?id=${room}`, "document.querySelector('.message--theirs .message__photo')");
  check("상대 화면: 사진이 상대 말풍선 쪽에", await b.waitUntil("document.querySelector('.message--theirs .message__photo.is-loaded')", 8000));
  check("상대 화면: 사진 메시지에도 '⋯'", await b.evaluate("!!document.querySelector('.message--theirs .message__photo').closest('.message').querySelector('.message__menu')"));
  check(`${W}px: 상대 화면 가로 스크롤 없음`, await noScroll());
  await b.screenshot(`message-photo-theirs-${W}.png`);

  // ---------- 쪽지함 미리보기 ----------
  await b.goto("/static/conversations.html", "document.querySelector('.conversation-card')");
  const preview = await b.evaluate(`document.querySelector('a.conversation-card[href$="id=${room}"] .conversation-card__preview').textContent`);
  check("쪽지함: 마지막 메시지가 사진이면 '사진'", preview === "사진", preview);

  // ---------- 관리자: 신고된 사진 ----------
  const reported = await api("POST", `/messages/${photoMessage.id}/reports`, seed.seller_token, { reason: "ABUSE", description: "사진 신고" });
  check("신고: 사진 메시지 신고 201", reported.status === 201, String(reported.status));
  await api("POST", "/auth/signup", null, { email: "admin@uicheck.ac.kr", password: "check-password-123", nickname: "관리자" });
  await makeAdmin(OUT, "admin@uicheck.ac.kr");
  const admin = await loginApi("admin@uicheck.ac.kr", "check-password-123");
  await b.evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(admin)})`);
  await b.goto("/static/admin.html", "document.querySelectorAll('.report-card').length > 0");
  const card = "[...document.querySelectorAll('.report-card')].find((c) => c.querySelector('.report-card__type').textContent === '쪽지 신고')";
  check("관리자: 쪽지 신고 카드에 사진", await b.waitUntil(`${card}?.querySelector('.report-card__photo')?.naturalWidth > 0`, 8000));
  await b.evaluate(`${card}.scrollIntoView({ block: 'center' })`);
  await sleep(200);
  await b.screenshot(`message-photo-admin-${W}.png`);
  check(`${W}px: 관리 화면 가로 스크롤 없음`, await noScroll());

  const jsErrors = b.exceptions.filter((e) => !String(e).startsWith("Failed to load resource"));
  check("JS 에러 없음", jsErrors.length === 0, jsErrors.join(" | "));
} catch (error) {
  results.push(`ERROR  ${error.message}`);
} finally {
  b.close();
  writeFileSync(join(OUT, "message-photo-check.txt"), results.join("\n") + "\n");
  console.log(results.join("\n"));
}
