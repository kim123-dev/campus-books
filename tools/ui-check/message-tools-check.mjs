// 쪽지 도구(쪽지함 "⋯" 메뉴: 신고·차단·나가기)를 헤드리스 Chrome으로 확인한다.
// 사용: WIDTH=375 tools/ui-check/run.sh message-tools-check
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { api, readSeed, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const seed = readSeed(OUT);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);

const b = await startBrowser(OUT, { width: W });
const dialogs = [];
b.listeners.push((msg) => {
  if (msg.method === "Page.javascriptDialogOpening") {
    dialogs.push(msg.params.message);
    b.send("Page.handleJavaScriptDialog", { accept: true });
  }
});
const noScroll = () => b.evaluate(`document.documentElement.scrollWidth <= ${W}`);
const inboxReady = "document.getElementById('result-summary') && !document.getElementById('result-summary').textContent.includes('불러오는 중')";
const cards = () => b.evaluate(`[...document.querySelectorAll('.conversation-card')].map((a) => new URL(a.href).searchParams.get('id'))`);
const menuOf = (id) => `document.querySelector('a.conversation-card[href$="id=${id}"]').parentElement.querySelector('.conversation-menu-button')`;
const menuItems = () => b.evaluate(`[...document.querySelectorAll('dialog.action-menu .action-menu__item')].map((x) => x.textContent)`);
const choose = (label) => b.evaluate(`[...document.querySelectorAll('dialog.action-menu .action-menu__item')].find((x) => x.textContent === ${JSON.stringify(label)}).click()`);

try {
  await b.goto("/static/index.html");
  await b.evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(seed.buyer_token)})`);
  await b.goto("/static/conversations.html", inboxReady + " && document.querySelector('.conversation-card')");
  const before = await cards();
  check("쪽지함: 카드마다 '⋯' 메뉴 버튼", (await b.evaluate("document.querySelectorAll('.conversation-menu-button').length")) === before.length && before.length > 0, `${before.length}개`);
  const size = await b.evaluate(`(() => { const r = ${menuOf(before[0])}.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; })()`);
  check("쪽지함: 메뉴 버튼 44px 이상", size[0] >= 44 && size[1] >= 44, JSON.stringify(size));
  check("쪽지함: 메뉴 버튼은 카드 링크 밖", await b.evaluate(`!${menuOf(before[0])}.closest('a')`));
  check("쪽지함: 메뉴 버튼 이름에 상대 닉네임", (await b.evaluate(`${menuOf(before[0])}.getAttribute('aria-label')`)).includes("님과의 대화 메뉴"));
  check(`${W}px: 쪽지함 가로 스크롤 없음`, await noScroll());

  // 메뉴 열기: 사용자 신고·차단·대화방 나가기·취소
  await b.evaluate(`${menuOf(before[0])}.click()`);
  await b.waitUntil("document.querySelector('dialog.action-menu[open]')");
  check("메뉴: 사용자 신고·차단·대화방 나가기·취소", JSON.stringify(await menuItems()) === JSON.stringify(["사용자 신고", "차단", "대화방 나가기", "취소"]), JSON.stringify(await menuItems()));
  const itemHeights = await b.evaluate(`[...document.querySelectorAll('dialog.action-menu .action-menu__item')].map((x) => Math.round(x.getBoundingClientRect().height))`);
  check("메뉴: 항목 44px 이상", itemHeights.every((h) => h >= 44), JSON.stringify(itemHeights));
  check(`${W}px: 메뉴가 화면 안에`, await b.evaluate(`(() => { const r = document.querySelector('dialog.action-menu').getBoundingClientRect(); return r.left >= 0 && r.right <= ${W}; })()`));
  await b.screenshot(`message-tools-menu-${W}.png`);
  await choose("취소");
  check("메뉴: 취소하면 닫히고 초점이 버튼으로", await b.waitUntil(`!document.querySelector('dialog.action-menu') && document.activeElement === ${menuOf(before[0])}`));

  // 사용자 신고 → 신고 창 → 접수 안내
  await b.evaluate(`${menuOf(before[0])}.click()`);
  await b.waitUntil("document.querySelector('dialog.action-menu[open]')");
  await choose("사용자 신고");
  await b.waitUntil("document.querySelector('dialog.report-dialog:not(.action-menu)[open]')");
  await b.evaluate(`(() => { const d = document.querySelector('dialog.report-dialog:not(.action-menu)'); d.querySelector('input[value=SPAM]').click(); d.querySelector('form').requestSubmit(); })()`);
  check("신고: 접수 안내", await b.waitUntil(`document.getElementById('inbox-notice').textContent.includes('신고가 접수되었습니다')`));

  // 대화방 나가기 → 확인 창 → 목록에서 사라짐, 상대에게는 남음
  const target = before[0];
  dialogs.length = 0;
  await b.evaluate(`${menuOf(target)}.click()`);
  await b.waitUntil("document.querySelector('dialog.action-menu[open]')");
  await choose("대화방 나가기");
  check("나가기: 목록에서 사라짐", await b.waitUntil(`!document.querySelector('a.conversation-card[href$="id=${target}"]') && document.getElementById('inbox-notice').textContent.includes('대화방에서 나갔어요')`));
  check("나가기: 확인 창에 '상대에게는 그대로' 안내", dialogs.length === 1 && dialogs[0].includes("상대에게는 그대로 남아요"), dialogs.join(" / "));
  const sellerList = await api("GET", "/conversations", seed.seller_token);
  check("나가기: 판매자 목록에는 그대로", sellerList.body.items.some((c) => String(c.id) === target));
  await b.screenshot(`message-tools-left-${W}.png`);

  // 상대가 새 쪽지 → 다시 나타나고 이전 대화는 숨김
  await api("POST", `/conversations/${target}/messages`, seed.seller_token, { content: "다시 연락드려요" });
  await b.goto("/static/conversations.html", inboxReady + " && document.querySelector('.conversation-card')");
  check("다시 나타남: 새 쪽지가 오면 목록에 다시", (await cards()).includes(target));
  await b.goto(`/static/chat.html?id=${target}`, "document.querySelectorAll('.message').length > 0");
  const texts = await b.evaluate(`[...document.querySelectorAll('.message__bubble')].map((m) => m.textContent)`);
  check("다시 나타남: 대화에는 나간 뒤 메시지만", JSON.stringify(texts) === JSON.stringify(["다시 연락드려요"]), JSON.stringify(texts).slice(0, 200));

  const jsErrors = b.exceptions.filter((e) => !String(e).startsWith("Failed to load resource"));
  check("JS 에러 없음", jsErrors.length === 0, jsErrors.join(" | "));
} catch (error) {
  results.push(`ERROR  ${error.message}`);
} finally {
  b.close();
  writeFileSync(join(OUT, "message-tools-check.txt"), results.join("\n") + "\n");
  console.log(results.join("\n"));
}
