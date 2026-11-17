// 쪽지 빠른 문장 칩 확인 (375px): 빈 대화 + 구매자에게만 칩 3개, 누르면 입력칸에 채우고 포커스(전송 안 함),
// 쓰던 글 뒤에 붙임, 메시지가 생기면 사라짐, 입력 중(키보드)에는 한 줄 가로 스크롤, 영어·중국어 넘침 없음.
// 사용: tools/ui-check/run.sh quick-reply-check
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { api, readSeed, sleep, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const seed = readSeed(OUT);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  [${W}] ${name}${detail ? `  (${detail})` : ""}`);

const b = await startBrowser(OUT, { width: W, height: 812, mobile: true });
const { evaluate, waitUntil, goto, screenshot, send } = b;
// 실제 손가락 누름(터치). 화면 밖 탭에서 focus()만 부르면 focus 이벤트가 안 와 입력 중 표시가 켜지지 않는다.
const tap = async (selector) => {
  const p = await evaluate(`(() => { const r = document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`);
  await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: p.x, y: p.y }] });
  await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await sleep(400);
};
const setToken = (token) => evaluate(`localStorage.setItem('campus-books.token', ${JSON.stringify(token)})`);
const chatReady = "!document.getElementById('chat').hidden && !document.documentElement.hasAttribute('data-i18n-pending')";
const chips = () =>
  evaluate(`(() => { const box = document.getElementById('quick-replies');
    const items = [...box.querySelectorAll('.chat__quick-chip')].map((c) => { const r = c.getBoundingClientRect(), cs = getComputedStyle(c);
      return { text: c.textContent, h: Math.round(r.height), top: Math.round(r.top), left: r.left, right: r.right, radius: cs.borderTopLeftRadius, inside: c.scrollWidth <= c.clientWidth + 1 }; });
    const r = box.getBoundingClientRect();
    return { shown: !box.hidden && box.getClientRects().length > 0, items, boxH: Math.round(r.height), boxRight: r.right, scrollable: box.scrollWidth > box.clientWidth,
      wrap: getComputedStyle(box).flexWrap, wide: document.documentElement.scrollWidth > innerWidth }; })()`);

try {
  // 판매자의 새 글에 구매자가 문의만 하고 아직 메시지를 보내지 않은 빈 대화
  const post = (await api("POST", "/posts", seed.seller_token, { title: "빈 대화 확인용 교재", book_title: "확인용", condition: "GOOD", price: 1000 })).body;
  const conv = (await api("POST", `/posts/${post.id}/conversations`, seed.buyer_token)).body;

  await goto("/static/index.html");
  await setToken(seed.buyer_token);
  await goto(`/static/chat.html?id=${conv.id}`, chatReady);
  let c = await chips();
  check("구매자·빈 대화: 칩 3개 표시", c.shown && c.items.map((i) => i.text).join("|") === "아직 있나요?|가격 조정 가능한가요?|언제 만날 수 있나요?", JSON.stringify(c.items.map((i) => i.text)));
  check("칩: 높이 44px 이상, 모서리 8px", c.items.every((i) => i.h >= 44 && i.radius === "8px"), JSON.stringify(c.items.map((i) => [i.h, i.radius])));
  check("칩: 화면 안, 가로 스크롤 없음", c.items.every((i) => i.left >= 0 && i.right <= W) && !c.wide);
  check("칩: 입력 줄 위", (await evaluate("document.getElementById('quick-replies').getBoundingClientRect().bottom <= document.getElementById('content').getBoundingClientRect().top + 1")));
  await screenshot(`chat-quick-replies-${W}.png`);

  // 누르면 채우기만 하고 보내지 않음 + 포커스
  await tap(".chat__quick-chip:first-child");
  const filled = await evaluate("({ value: document.getElementById('content').value, focused: document.activeElement === document.getElementById('content'), messages: document.querySelectorAll('.message').length })");
  check("칩 누름: 입력칸에 채우고 포커스, 전송 안 함", filled.value === "아직 있나요?" && filled.focused && filled.messages === 0, JSON.stringify(filled));
  c = await chips();
  check("입력 중(키보드): 칩이 한 줄 가로 스크롤", c.shown && c.wrap === "nowrap" && new Set(c.items.map((i) => i.top)).size === 1 && c.boxH <= 60 && !c.wide, JSON.stringify({ wrap: c.wrap, boxH: c.boxH }));
  await screenshot(`chat-quick-replies-typing-${W}.png`);
  // 한 줄 가로 스크롤이라 세 번째 칩은 밀어서 보이게 한 뒤 누른다.
  await evaluate("document.querySelector('.chat__quick-chip:last-child').scrollIntoView({ inline: 'end', block: 'nearest' })");
  await tap(".chat__quick-chip:last-child");
  const appended = await evaluate("document.getElementById('content').value");
  check("쓰던 글이 있으면 뒤에 붙임", appended === "아직 있나요? 언제 만날 수 있나요?", appended);

  // 보내면 메시지가 생기고 칩은 사라진다.
  await evaluate("document.getElementById('message-form').requestSubmit()");
  await waitUntil("document.querySelectorAll('.message').length === 1");
  check("메시지가 생기면 칩 사라짐", !(await chips()).shown);

  // 판매자 쪽 빈 대화에는 칩이 없다.
  const post2 = (await api("POST", "/posts", seed.seller_token, { title: "판매자 쪽 확인용", book_title: "확인용", condition: "GOOD", price: 1000 })).body;
  const conv2 = (await api("POST", `/posts/${post2.id}/conversations`, seed.buyer_token)).body;
  await setToken(seed.seller_token);
  await goto(`/static/chat.html?id=${conv2.id}`, chatReady);
  check("판매자·빈 대화: 칩 없음", !(await chips()).shown);

  // 영어·중국어: 칩 문구가 넘치지 않는지 (구매자, 빈 대화)
  await setToken(seed.buyer_token);
  for (const lang of ["en", "zh-CN"]) {
    await goto(`/static/chat.html?id=${conv2.id}&lang=${lang}`, chatReady);
    c = await chips();
    check(`${lang}: 칩 3개, 화면·칩 안에 다 보임`, c.shown && c.items.length === 3 && c.items.every((i) => i.left >= 0 && i.right <= W && i.inside && i.h >= 44) && !c.wide, JSON.stringify(c.items.map((i) => i.text)));
    await screenshot(`chat-quick-replies-${lang}-${W}.png`);
  }
  check("JS 예외 없음", b.exceptions.length === 0, b.exceptions.join(" / "));
} catch (error) {
  results.push(`ERROR  ${error.stack}`);
} finally {
  writeFileSync(join(OUT, "quick-reply-check.txt"), results.join("\n"));
  console.log(results.join("\n"));
  b.close();
}
