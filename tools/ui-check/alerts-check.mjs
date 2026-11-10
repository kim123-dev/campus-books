// 찾는 교재 알림(헤더 종·배지, 알림 화면)을 헤드리스 Chrome으로 확인한다.
// 사용: WIDTH=375 tools/ui-check/run.sh alerts-check
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { api, readSeed, sleep, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const seed = readSeed(OUT);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);

const b = await startBrowser(OUT, { width: W });
const badge = `(() => { const n = document.getElementById('nav-alerts-unread'); return n && !n.hidden ? n.textContent : ''; })()`;

try {
  await b.goto("/static/index.html");
  await b.evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(seed.buyer_token)})`);

  // 화면에서 조건 등록
  await b.goto("/static/alerts.html", "document.getElementById('alert-count').textContent !== ''");
  check("종 아이콘 보임", await b.evaluate(`(() => { const r = document.getElementById('nav-alerts')?.getBoundingClientRect(); return !!r && r.width > 0 && r.right <= ${W}; })()`));
  check("빈 알림 안내", await b.waitUntil(`document.getElementById('result-summary').textContent.includes('아직 받은 알림이')`));
  await b.evaluate(`(() => { const f = document.getElementById('alert-form'); f.keyword.value = '네트워크'; f.max_price.value = '20000'; f.requestSubmit(); })()`);
  check("조건 등록 후 목록 1/10", await b.waitUntil(`document.getElementById('alert-count').textContent === '1/10'`));
  await b.evaluate(`(() => { const f = document.getElementById('alert-form'); f.keyword.value = '네트워크'; f.requestSubmit(); })()`);
  check("중복 키워드 에러", await b.waitUntil(`document.querySelector('[data-error-for=keyword]').textContent.includes('이미')`));

  // 판매자가 맞는 글 2개, 안 맞는 글 1개를 쓴다.
  const post = (title, book_title, price) =>
    api("POST", "/posts", seed.seller_token, { title, book_title, condition: "GOOD", price });
  await post("네트워크 교재 팝니다", "컴퓨터 네트워크 하향식 접근", 15000);
  await post("데이터통신 겸 네트워크", "데이터 통신과 네트워크", 18000);
  await post("비싼 네트워크 책", "네트워크 프로그래밍", 30000);

  await b.goto("/static/index.html", "document.getElementById('nav-alerts')");
  check("헤더 배지 2", await b.waitUntil(`${badge} === '2'`), await b.evaluate(badge));
  await b.screenshot(`alerts-badge-${W}.png`);

  await b.goto("/static/alerts.html", "document.querySelectorAll('.notification-card').length > 0");
  check("알림 카드 2개", (await b.evaluate(`document.querySelectorAll('.notification-card').length`)) === 2);
  check("새 알림 강조", (await b.evaluate(`document.querySelectorAll('.notification-card--unread').length`)) === 2);
  check("읽음 처리 후 배지 사라짐", await b.waitUntil(`${badge} === ''`));
  check("가로 스크롤 없음", await b.evaluate(`document.documentElement.scrollWidth <= ${W}`));
  await b.screenshot(`alerts-page-${W}.png`);

  // 조건 삭제
  await b.evaluate(`document.querySelector('.alert-list .link-button--danger').click()`);
  check("조건 삭제 후 0/10", await b.waitUntil(`document.getElementById('alert-count').textContent === '0/10'`));
  await sleep(200);
  check("JS 에러 없음", b.exceptions.filter((e) => !String(e).startsWith("Failed to load resource")).length === 0, b.exceptions.join(" | "));
} catch (error) {
  results.push(`ERROR  ${error.message}`);
} finally {
  b.close();
  writeFileSync(join(OUT, "alerts-check.txt"), results.join("\n") + "\n");
  console.log(results.join("\n"));
}
