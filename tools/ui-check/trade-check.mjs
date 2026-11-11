// 판매 완료 때 구매자 고르기와 구매자 변경을 모바일 폭(기본 375px)으로 확인한다.
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { readSeed, sleep, startBrowser } from "./lib.mjs";

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

  check("스크립트 오류 없음", exceptions.length === 0, exceptions.join(" | "));
} catch (error) {
  results.push(`ERROR ${error.stack}`);
} finally {
  browser.close();
  writeFileSync(join(OUT, "trade-check.txt"), results.join("\n") + "\n");
}
