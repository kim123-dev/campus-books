// 목록 화면(홈) 확인: 배너(비로그인 큰 배너 / 로그인 얇은 띠), 학교가 빈 사용자의 학교 안내, 한 줄 검색과 필터 펼치기, 판매 완료 기본 숨김·토글, 글이 없을 때의 "첫 교재 올리기".
// 사용: WIDTH=375 tools/ui-check/run.sh home-check   (PC는 WIDTH=1280)
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { api, readSeed, sleep, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const H = W < 768 ? 812 : 900;
const MOBILE = W < 768;
const seed = readSeed(OUT);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  [${W}] ${name}${detail ? `  (${detail})` : ""}`);

const b = await startBrowser(OUT, { width: W, height: H, mobile: MOBILE });
const { evaluate, waitUntil, goto, screenshot } = b;
const ready = "document.getElementById('result-summary').textContent !== '' && !document.getElementById('result-summary').textContent.includes('불러오는 중')";
const setToken = (token) => evaluate(token ? `localStorage.setItem('campus-books.token', ${JSON.stringify(token)})` : "localStorage.removeItem('campus-books.token')");
const rect = (selector) =>
  evaluate(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); if (!e || !e.getClientRects().length) return null; const r = e.getBoundingClientRect(); return { top: Math.round(r.top), bottom: Math.round(r.bottom), left: Math.round(r.left), right: Math.round(r.right), w: Math.round(r.width), h: Math.round(r.height) }; })()`);
const visible = (selector) => evaluate(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); return Boolean(e && e.getClientRects().length); })()`);
const noHScroll = () => evaluate("document.documentElement.scrollWidth <= innerWidth");
// 배너 때문에 화면이 밀렸는지. 로그인 확인을 기다리는 동안 배너 모양(높이)이 바뀌면 배너가 밀림 원인으로 잡힌다.
// 페이지 전체 CLS도 함께 본다. 헤더는 JS가 그리므로, CSS가 헤더 높이를 미리 잡아 두지 않으면 헤더가 채워질 때 아래 전체가 밀린다.
const layoutShift = () =>
  evaluate(`new Promise((resolve) => { let total = 0, hero = 0;
    new PerformanceObserver((l) => { for (const e of l.getEntries()) { if (e.hadRecentInput) continue; total += e.value;
      if (e.sources.some((s) => String(s.node?.className ?? '').includes('home-hero') && (s.previousRect.height !== s.currentRect.height || s.previousRect.top !== s.currentRect.top))) hero += e.value; } }).observe({ type: 'layout-shift', buffered: true });
    setTimeout(() => resolve({ hero: Math.round(hero * 1000) / 1000, total: Math.round(total * 1000) / 1000 }), 800); })`);

try {
  // ---------- 배너 없음: 헤더 바로 아래 제목, 화면 밀림 없음 ----------
  for (const token of [null, seed.buyer_token]) {
    const who = token ? "로그인" : "비로그인";
    await goto("/static/index.html");
    await setToken(token);
    await goto("/static/index.html", `${ready} && document.getElementById('site-header').textContent.length > 0`);
    check(`${who}: 배너 없음`, (await evaluate("document.querySelector('.home-hero')")) === null);
    check(`${who}: 제목이 헤더 바로 아래`, (await rect(".page-title")).top - (await rect(".site-header")).bottom <= 40);
    const shift = await layoutShift();
    check(`${who}: 페이지 전체 밀림 없음(CLS < 0.01)`, shift.total < 0.01, JSON.stringify(shift));
    check(`${who}: 가로 스크롤 없음`, await noHScroll());
    await screenshot(`home-${token ? "member" : "guest"}-${W}.png`);
  }

  // ---------- 학교 안내: 로그인했는데 내 학교가 비었을 때만 제목 아래 작은 줄, 닫으면 다시 안 뜸 ----------
  const hintShown = () => evaluate("Boolean(document.querySelector('.school-hint'))");
  const hintReady = `${ready} && document.getElementById('site-header').textContent.length > 0`;
  await setToken(null);
  await goto("/static/index.html", hintReady);
  check("학교 안내: 비로그인에는 없음", !(await hintShown()));
  await setToken(seed.buyer_token);
  await evaluate("localStorage.removeItem('campus-books.school-hint-dismissed')");
  await goto("/static/index.html", hintReady);
  check("학교 안내: 내 학교가 없으면 보임", await waitUntil("Boolean(document.querySelector('.school-hint'))"));
  const hint = await evaluate(`(() => { const h = document.querySelector('.school-hint'), r = h.getBoundingClientRect(), t = document.querySelector('.page-title').getBoundingClientRect(),
    f = document.getElementById('filter-form').getBoundingClientRect(), a = h.querySelector('.school-hint__link'), c = h.querySelector('.school-hint__close'), txt = h.querySelector('.school-hint__text');
    return { h: Math.round(r.height), belowTitle: r.top >= t.bottom - 1 && r.bottom <= f.top + 1, text: txt.textContent, href: a.getAttribute('href'), linkH: Math.round(a.getBoundingClientRect().height),
      close: [Math.round(c.getBoundingClientRect().width), Math.round(c.getBoundingClientRect().height)], closeLabel: c.getAttribute('aria-label'), right: Math.round(r.right),
      lines: Math.round(txt.getBoundingClientRect().height / parseFloat(getComputedStyle(txt).lineHeight)) }; })()`);
  check("학교 안내: 문구·'선택하기' → 내 정보 학교 설정", hint.text === "학교를 선택하면 같은 학교 글을 모아 볼 수 있어요 선택하기" && hint.href === "/static/me.html#school-row", JSON.stringify(hint));
  check("학교 안내: 제목과 검색 사이, 작은 줄(높이 64px 이하, 두 줄 이내), 화면 안", hint.belowTitle && hint.h <= 64 && hint.lines <= 2 && hint.right <= W, JSON.stringify(hint));
  check("학교 안내: 닫기 44px·이름, 링크 44px", hint.close[0] >= 44 && hint.close[1] >= 44 && hint.closeLabel === "학교 안내 닫기" && hint.linkH >= 44, JSON.stringify(hint));
  check("학교 안내: 가로 스크롤 없음", await noHScroll());
  await screenshot(`home-school-hint-${W}.png`);
  await evaluate("document.querySelector('.school-hint__link').click()");
  check("학교 안내: '선택하기' → 내 정보에서 학교 목록이 펼쳐짐", await waitUntil("location.pathname === '/static/me.html' && document.querySelectorAll('#school-options button').length > 0 && !document.getElementById('school-panel').hidden", 8000));
  await goto("/static/index.html", hintReady);
  await waitUntil("Boolean(document.querySelector('.school-hint'))");
  await evaluate("document.querySelector('.school-hint__close').click()");
  check("학교 안내: 닫으면 사라지고 기록", !(await hintShown()) && (await evaluate("localStorage.getItem('campus-books.school-hint-dismissed')")) === "1");
  await goto("/static/index.html", hintReady);
  await sleep(500);
  check("학교 안내: 닫은 뒤 다시 열어도 안 보임", !(await hintShown()));
  // 내 학교가 있는 사용자(판매자)에게는 보이지 않는다.
  await evaluate("localStorage.removeItem('campus-books.school-hint-dismissed')");
  const schools = (await api("GET", "/schools")).body.items;
  await api("PUT", "/users/me/school", seed.seller_token, { school_id: schools[0].id });
  await setToken(seed.seller_token);
  await goto("/static/index.html", hintReady);
  await sleep(500);
  check("학교 안내: 내 학교가 있으면 안 보임", !(await hintShown()));
  await setToken(seed.buyer_token);
  await evaluate("localStorage.setItem('campus-books.school-hint-dismissed', '1')");
  await goto("/static/index.html", hintReady);

  // ---------- 한 줄 검색 + 필터 펼치기 ----------
  const row = await evaluate("['#q', '#search-button', '#filter-toggle'].map(s => Math.round(document.querySelector(s).getBoundingClientRect().top))");
  check("검색: 검색창·검색 버튼·필터 버튼이 한 줄", row.every((t) => t === row[0]), row.join());
  check("검색: \"검색어\" 라벨은 화면에서 숨김", (await rect(".filter-form__search > label")).h <= 1);
  check("필터: 처음에는 접힘", !(await visible("#status")) && (await evaluate("document.getElementById('filter-toggle').getAttribute('aria-expanded')")) === "false");
  await evaluate("document.getElementById('filter-toggle').click()");
  const fields = await evaluate("['status', 'course_name', 'min_price', 'max_price'].map(id => { const r = document.getElementById(id).getBoundingClientRect(); return r.width > 0 ? Math.round(r.top) : null; })");
  check("필터: 누르면 상태·과목명·가격 칸이 펼쳐짐", fields.every((t) => t !== null) && (await evaluate("document.getElementById('filter-toggle').getAttribute('aria-expanded')")) === "true", fields.join());
  if (!MOBILE) check("필터(PC): 펼친 4칸이 한 줄", fields.every((t) => t === fields[0]), fields.join());
  check("필터: 펼쳐도 가로 스크롤 없음", await noHScroll());
  await screenshot(`home-filter-open-${W}.png`);
  await evaluate("(() => { const f = document.getElementById('filter-form'); f.status.value = 'ON_SALE'; f.min_price.value = '0'; f.requestSubmit(); })()");
  await waitUntil(ready);
  check("필터: 검색하면 접히고 '필터 2' 표시", !(await visible("#status")) && (await evaluate("document.querySelector('.filter-form__count').textContent")) === "2");
  check("필터: 검색 결과가 있으면 빈 화면 버튼 없음", !(await visible("#empty-actions")));

  // ---------- 판매 완료 기본 숨김 + "판매 완료 글도 보기" ----------
  await api("PATCH", `/posts/${seed.p2}/status`, seed.seller_token, { status: "SOLD" });
  const titles = () => evaluate("[...document.querySelectorAll('#post-list .post-card__title, #post-list h2, #post-list h3')].map(e => e.textContent)");
  const totalText = () => evaluate("document.getElementById('result-summary').textContent");
  const cardCount = () => evaluate("document.querySelectorAll('#post-list > li').length");
  await goto("/static/index.html", ready);
  const hiddenTotal = (await api("GET", "/posts?include_sold=false&size=50")).body.total;
  check("판매 완료: 기본은 숨김(카드 수 = 총 N개 = API 숨김 수)", (await cardCount()) === hiddenTotal && (await totalText()).includes(String(hiddenTotal)) && !(await titles()).includes("운영체제 공룡책"), `${await totalText()} / ${await cardCount()} / ${hiddenTotal}`);
  await evaluate("document.getElementById('filter-toggle').click()");
  const sold = await rect(".filter-check");
  check("판매 완료 토글: 기본 꺼짐, 누르는 줄 44px, 화면 안", (await evaluate("document.getElementById('show_sold').checked")) === false && sold && sold.h >= 44 && sold.right <= W, JSON.stringify(sold));
  await evaluate("document.getElementById('show_sold').checked = true");
  await screenshot(`home-filter-sold-${W}.png`);
  await evaluate("document.getElementById('filter-form').requestSubmit()");
  await waitUntil(`${ready} && new URLSearchParams(location.search).get('show_sold') === '1'`);
  await waitUntil(ready);
  const allTotal = (await api("GET", "/posts?size=50")).body.total;
  check("판매 완료 토글: 켜면 주소에 show_sold=1, 총 N개·카드에 판매 완료 포함", (await cardCount()) === allTotal && (await totalText()).includes(String(allTotal)) && allTotal === hiddenTotal + 1, `${await totalText()} / ${allTotal}`);
  check("판매 완료 토글: 필터 개수에는 세지 않음", (await evaluate("document.querySelector('.filter-form__count').hidden")) === true);
  await goto("/static/index.html?show_sold=1", ready);
  check("판매 완료 토글: 새로고침해도 켜진 상태 유지", (await evaluate("document.getElementById('show_sold').checked")) === true);
  await goto(`/static/index.html?q=${encodeURIComponent("운영체제")}`, ready);
  check("검색: 판매 완료 글은 검색 결과에서도 기본 숨김", (await cardCount()) === 0);
  await goto(`/static/index.html?q=${encodeURIComponent("운영체제")}&show_sold=1`, ready);
  check("검색: 토글을 켜면 검색 결과에 판매 완료 포함", (await cardCount()) === 1);
  check("판매 완료 토글: 가로 스크롤 없음", await noHScroll());

  // ---------- 글이 하나도 없을 때 ----------
  for (const id of [seed.p1, seed.p2]) await api("DELETE", `/posts/${id}`, seed.seller_token);
  await api("DELETE", `/posts/${seed.p3}`, seed.buyer_token);
  const left = (await api("GET", "/posts?size=50")).body.items;
  for (const post of left) await api("DELETE", `/posts/${post.id}`, seed.seller_token);
  await setToken(null);
  await goto("/static/index.html?q=%EC%97%86%EB%8A%94%EC%B1%85", ready);
  check("검색 결과 없음: 버튼 없음(그림·문구만)", !(await visible("#empty-actions")) && (await visible(".empty-state__image")));
  await goto("/static/index.html", `${ready} && document.querySelector('.empty-state__image')?.complete`);
  const emptyButton = await rect("#empty-actions a");
  const summary = await rect("#result-summary");
  check("글 없음: '첫 교재 올리기' 버튼이 문구 아래", emptyButton && emptyButton.top >= summary.bottom && (await evaluate("document.querySelector('#empty-actions a').textContent")) === "첫 교재 올리기", JSON.stringify(emptyButton));
  check("글 없음: 버튼 가운데", emptyButton && Math.abs(emptyButton.left - summary.left - (summary.right - emptyButton.right)) <= 1, JSON.stringify({ emptyButton, summary }));
  check("글 없음: 버튼은 글쓰기 화면으로", (await evaluate("document.querySelector('#empty-actions a').getAttribute('href')")) === "/static/post-form.html");
  await screenshot(`home-empty-${W}.png`);
  await evaluate("document.querySelector('#empty-actions a').click()");
  await waitUntil("location.pathname === '/static/login.html'");
  check("글 없음(비로그인): 버튼을 누르면 로그인 화면, 로그인 뒤 글쓰기로", (await evaluate("new URLSearchParams(location.search).get('next')")) === "/static/post-form.html", await evaluate("location.pathname + location.search"));

  check("JS 예외 없음", b.exceptions.length === 0, b.exceptions.join(" / "));
} catch (error) {
  results.push(`ERROR  ${error.stack}`);
} finally {
  writeFileSync(join(OUT, "home-check.txt"), results.join("\n"));
  console.log(results.join("\n"));
  b.close();
}
