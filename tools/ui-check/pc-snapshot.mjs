// PC(1280px) 화면의 모든 보이는 요소 위치·크기·글자 크기·색을 기록한다. 변경 전후 결과를 비교해 PC 모습이 그대로인지 확인한다.
// 사용: node pc-snapshot.mjs <OUT> <결과 파일 이름>
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { readSeed, seedExtra, sleep, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const RESULT = process.argv[3];
const seed = readSeed(OUT);
const { admin } = await seedExtra(OUT, seed);
const b = await startBrowser(OUT, { width: 1280, height: 900, mobile: false });

const PAGES = [
  ["guest-index", null, "/static/index.html"],
  ["guest-post", null, `/static/post.html?id=${seed.p1}`],
  ["login", null, "/static/login.html"],
  ["signup", null, "/static/signup.html"],
  ["buyer-index", "buyer", "/static/index.html"],
  ["buyer-index-filter", "buyer", "/static/index.html?q=%EA%B5%90%EC%9E%AC&status=ON_SALE&min_price=0"],
  ["buyer-post-photos", "buyer", `/static/post.html?id=${seed.p1}`],
  ["buyer-post-nophoto", "buyer", `/static/post.html?id=${seed.p2}`],
  ["seller-own-post", "seller", `/static/post.html?id=${seed.p1}`],
  ["seller-form-new", "seller", "/static/post-form.html"],
  ["seller-form-edit", "seller", `/static/post-form.html?id=${seed.p1}`],
  ["seller-my-posts", "seller", "/static/me.html"],
  ["buyer-wishlist", "buyer", "/static/me.html?tab=wishlist"],
  ["buyer-blocks", "buyer", "/static/blocks.html"],
  ["buyer-conversations", "buyer", "/static/conversations.html"],
  ["buyer-chat", "buyer", `/static/chat.html?id=${seed.c2}`],
  ["admin-reports", "admin", "/static/admin.html"],
  ["admin-index", "admin", "/static/index.html"],
];
const TOKENS = { buyer: seed.buyer_token, seller: seed.seller_token, admin };

// 요소마다 "부모 경로 + 태그.클래스:n번째"를 키로, 보이는 요소의 위치·크기와 주요 스타일을 기록한다.
const SNAPSHOT = `(() => {
  const out = {};
  const keyOf = (e) => {
    const parts = [];
    for (let n = e; n && n !== document.body; n = n.parentElement) {
      const index = [...n.parentElement.children].indexOf(n);
      parts.unshift(n.tagName.toLowerCase() + (n.id ? '#' + n.id : '') + (n.classList.length ? '.' + [...n.classList].sort().join('.') : '') + ':' + index);
    }
    return parts.join('>');
  };
  for (const e of document.body.querySelectorAll('*')) {
    if (e.closest('script, svg *')) continue;
    if (e.getClientRects().length === 0) continue;
    const r = e.getBoundingClientRect();
    const s = getComputedStyle(e);
    if (s.visibility === 'hidden') continue;
    const round = (v) => Math.round(v * 2) / 2;
    out[keyOf(e)] = {
      box: [round(r.left + scrollX), round(r.top + scrollY), round(r.width), round(r.height)].join(','),
      style: [s.fontSize, s.fontWeight, s.lineHeight, s.color, s.backgroundColor, s.borderRadius, s.padding, s.position, s.display].join('|'),
      text: e.children.length === 0 ? (e.textContent || '').trim().slice(0, 40) : '',
    };
  }
  return out;
})()`;

const result = {};
await b.goto("/static/index.html");
for (const [name, who, path] of PAGES) {
  await b.evaluate(who ? `localStorage.setItem("campus-books.token", ${JSON.stringify(TOKENS[who])})` : "localStorage.clear()");
  await b.goto(path);
  // 데이터 로딩·이미지·폰트가 끝날 때까지 기다린다.
  await b.waitUntil("document.fonts.status === 'loaded' && ![...document.querySelectorAll('img')].some(i => !i.complete) && !document.body.textContent.includes('불러오는 중')", 8000);
  await sleep(700);
  result[name] = await b.evaluate(SNAPSHOT);
  await b.screenshot(`pc-${RESULT}-${name}.png`);
}
writeFileSync(join(OUT, `${RESULT}.json`), JSON.stringify(result));
console.log(`${RESULT}: ${Object.entries(result).map(([k, v]) => `${k}=${Object.keys(v).length}`).join(" ")}`);
console.log("exceptions:", b.exceptions.filter((e) => !String(e).includes("Failed to load resource")).length);
b.close();
