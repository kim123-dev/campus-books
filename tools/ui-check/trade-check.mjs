// 판매 완료 때 구매자 고르기, 구매자 변경, 판매 중으로 되돌리기를 모바일 폭(기본 375px)으로 확인한다.
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { api, readSeed, sleep, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const seed = readSeed(OUT);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);

const browser = await startBrowser(OUT, { width: W });
const { evaluate, waitUntil, goto, screenshot, exceptions } = browser;
const setToken = (token) => evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(token)})`);
const clickText = (selector, text) =>
  evaluate(`[...document.querySelectorAll(${JSON.stringify(selector)})].find((b) => b.textContent.trim() === ${JSON.stringify(text)})?.click() ?? "none"`);
// 열린 창의 크기와 가로 넘침, 줄 높이(손가락으로 누르기 쉬운지)
const dialogLayout = () =>
  evaluate(`(() => {
    const d = document.querySelector("dialog[open]");
    if (!d) return null;
    const r = d.getBoundingClientRect();
    const rows = [...d.querySelectorAll(".report-dialog__reason")].map((x) => Math.round(x.getBoundingClientRect().height));
    return { left: Math.round(r.left), right: Math.round(r.right), rows, labels: [...d.querySelectorAll(".report-dialog__reason span")].map((s) => s.textContent),
      overflow: d.scrollWidth > d.clientWidth + 1, checked: d.querySelector("input:checked")?.value ?? null };
  })()`);

try {
  await goto("/static/index.html");
  await setToken(seed.seller_token);
  await goto(`/static/post.html?id=${seed.p1}`, "document.querySelector('#owner-actions button')");

  // 1) 판매 완료 창
  await clickText("#owner-actions button", "판매 완료로 변경");
  await waitUntil("document.querySelector('dialog[open]')");
  let layout = await dialogLayout();
  check("판매 완료 창이 열림", layout !== null);
  check("후보에 쪽지 보낸 구매자, 마지막에 선택 안 함", JSON.stringify(layout?.labels) === JSON.stringify(["구매자지은", "선택 안 함 (오프라인 거래 등)"]), JSON.stringify(layout?.labels));
  check("미리 골라 두지 않음", layout?.checked === null);
  check("창이 화면 안(좌우 16px)", layout && layout.left >= 15 && layout.right <= W - 15, `${layout?.left}~${layout?.right}`);
  check("창 가로 넘침 없음", layout && !layout.overflow);
  check("선택 줄 높이 44px 이상", layout && layout.rows.every((h) => h >= 44), JSON.stringify(layout?.rows));
  await screenshot(`trade-sell-dialog-${W}.png`);

  await clickText("dialog[open] button", "판매 완료");
  await sleep(200);
  const emptyError = await evaluate(`document.querySelector("dialog[open] .form-error:not([hidden])")?.textContent ?? ""`);
  check("고르지 않고 누르면 안내", emptyError.includes("선택 안 함"), emptyError);

  await evaluate(`document.querySelector("dialog[open] input[value]:not([value='none'])").click()`);
  await clickText("dialog[open] button", "판매 완료");
  const sold = await waitUntil("document.querySelector('#buyer-line')?.textContent.includes('구매자지은')");
  check("판매 완료 후 거래한 사람 표시", sold, await evaluate(`document.querySelector('#buyer-line')?.textContent ?? ""`));
  check("판매 완료 배지", await evaluate(`document.querySelector(".post-detail__top .badge")?.textContent === "판매 완료"`));
  check("거래한 사람 줄 가로 넘침 없음", await evaluate(`document.documentElement.scrollWidth <= window.innerWidth`));
  await screenshot(`trade-sold-${W}.png`);

  // 2) 구매자 변경 → 선택 안 함
  await clickText("#buyer-line button", "구매자 변경");
  await waitUntil("document.querySelector('dialog[open]')");
  layout = await dialogLayout();
  check("변경 창은 지금 구매자를 미리 골라 둠", layout?.checked !== null && layout?.checked !== "none", String(layout?.checked));
  await evaluate(`document.querySelector("dialog[open] input[value='none']").click()`);
  await clickText("dialog[open] button", "변경");
  const reset = await waitUntil("document.querySelector('#buyer-line')?.textContent.includes('선택 안 함')");
  check("선택 안 함으로 되돌림", reset);
  check("되돌린 뒤에는 변경 버튼 없음", await evaluate(`!document.querySelector("#buyer-line button")`));
  await screenshot(`trade-reset-${W}.png`);

  // 3) 판매 중으로 되돌리기: 버튼 모양, 확인 창(취소하면 그대로), 되돌린 뒤 판매 중
  const revertButton = () =>
    evaluate(`(() => {
      const b = [...document.querySelectorAll("#owner-actions button")].find((x) => x.textContent.trim() === "판매 중으로 되돌리기");
      if (!b) return null;
      const r = b.getBoundingClientRect();
      return { height: Math.round(r.height), bg: getComputedStyle(b).backgroundColor, primary: b.classList.contains("button--primary"), disabled: b.disabled };
    })()`);
  let revert = await revertButton();
  check("판매 완료 글에 되돌리기 버튼", revert !== null);
  check("되돌리기 버튼 높이 44px 이상", revert && revert.height >= 44, String(revert?.height));
  check("되돌리기 버튼 기본색 #5B3FD6", revert?.bg === "rgb(91, 63, 214)", revert?.bg);
  check("판매 완료 안내 문구", await evaluate(`document.querySelector(".owner-panel__notice")?.textContent.includes("판매 중으로 되돌릴 수 있어요")`));
  check("되돌리기 줄 가로 넘침 없음", await evaluate(`document.documentElement.scrollWidth <= window.innerWidth`));
  await screenshot(`trade-revert-button-${W}.png`);

  await evaluate(`window.__confirms = []; window.confirm = (m) => { window.__confirms.push(m); return false; }`);
  await clickText("#owner-actions button", "판매 중으로 되돌리기");
  await sleep(300);
  check("누르면 확인 창 한 번", await evaluate(`window.__confirms.length === 1 && window.__confirms[0].includes("판매 중으로 되돌릴까요")`));
  check("취소하면 판매 완료 그대로", await evaluate(`document.querySelector(".post-detail__top .badge")?.textContent === "판매 완료"`));

  await evaluate(`window.confirm = (m) => { window.__confirms.push(m); return true; }`);
  await clickText("#owner-actions button", "판매 중으로 되돌리기");
  const reverted = await waitUntil(`document.querySelector(".post-detail__top .badge")?.textContent === "판매 중"`);
  check("확인하면 판매 중으로 되돌림", reverted);
  check("되돌린 뒤 수정 버튼이 다시 보임", await evaluate(`[...document.querySelectorAll("#owner-actions a")].some((a) => a.textContent.trim() === "수정")`));
  check("되돌린 뒤 거래한 사람 줄 없음", await evaluate(`!document.querySelector("#buyer-line")`));
  await screenshot(`trade-reverted-${W}.png`);

  // 4) 후기가 있으면: 버튼은 그대로 보이고, 누르면 409 메시지
  const buyerId = (await api("GET", "/users/me", seed.buyer_token)).body.id;
  await api("PATCH", `/posts/${seed.p1}/status`, seed.seller_token, { status: "SOLD", buyer_id: buyerId });
  const detail = await api("GET", `/conversations/${seed.c1}`, seed.buyer_token);
  const tradeId = detail.body?.trade?.trade_id;
  const review = await api("POST", `/trades/${tradeId}/reviews`, seed.buyer_token, { rating: "GOOD", content: "친절했어요" });
  check("확인용 후기 작성", review.status === 201, `${review.status}`);
  await goto(`/static/post.html?id=${seed.p1}`, "document.querySelector('#owner-actions button')");
  revert = await revertButton();
  check("후기가 있어도 되돌리기 버튼은 보임", revert !== null);
  await evaluate(`window.confirm = () => true`);
  await clickText("#owner-actions button", "판매 중으로 되돌리기");
  const blocked = await waitUntil(`document.querySelector("#action-error:not([hidden])")?.textContent.includes("후기가 이미 있어 되돌릴 수 없어요")`);
  check("누르면 후기 때문에 못 되돌린다는 안내", blocked, await evaluate(`document.querySelector("#action-error")?.textContent ?? ""`));
  check("안내 뒤에도 판매 완료 그대로", await evaluate(`document.querySelector(".post-detail__top .badge")?.textContent === "판매 완료"`));
  check("안내 뒤 버튼이 다시 눌림", (await revertButton())?.disabled === false);
  check("안내 줄 가로 넘침 없음", await evaluate(`document.documentElement.scrollWidth <= window.innerWidth`));
  await screenshot(`trade-revert-blocked-${W}.png`);

  // 4)의 409는 일부러 낸 응답이라 브라우저의 "Failed to load resource" 로그는 오류로 세지 않는다.
  const jsErrors = exceptions.filter((e) => !String(e).includes("status of 409"));
  check("스크립트 오류 없음", jsErrors.length === 0, jsErrors.join(" | "));
} catch (error) {
  results.push(`ERROR ${error.stack}`);
} finally {
  browser.close();
  writeFileSync(join(OUT, "trade-check.txt"), results.join("\n") + "\n");
}
