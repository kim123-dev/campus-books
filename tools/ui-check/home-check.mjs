// 목록 화면(홈) 확인: 배너(비로그인 큰 배너 / 로그인 얇은 띠), 한 줄 검색과 필터 펼치기, 글이 없을 때의 "첫 교재 올리기".
// 사용: WIDTH=375 tools/ui-check/run.sh home-check   (PC는 WIDTH=1280)
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { api, readSeed, startBrowser } from "./lib.mjs";

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
  // ---------- 비로그인: 큰 배너 ----------
  await goto("/static/index.html");
  await setToken(null);
  await goto("/static/index.html", `${ready} && document.querySelector('.home-hero__image').complete`);
  const hero = await rect(".home-hero");
  const image = await rect(".home-hero__image");
  const button = await rect(".home-hero__button");
  check("비로그인: 배너 보임(문구·보조 문구·버튼·그림)", hero && (await visible(".home-hero__guest.home-hero__title")) && (await visible(".home-hero__sub")) && button && image, JSON.stringify(hero));
  check("비로그인: 띠 문구는 숨김", !(await visible(".home-hero__member")));
  check(`비로그인: 그림 ${MOBILE ? 104 : 240}px, 4:3, 문구 오른쪽`, image && image.w === (MOBILE ? 104 : 240) && image.h === (MOBILE ? 78 : 180) && image.left > button.right - 1, JSON.stringify(image));
  check("비로그인: 그림 alt 비움·실제 크기 지정", await evaluate("(() => { const i = document.querySelector('.home-hero__image'); return i.getAttribute('alt') === '' && i.getAttribute('width') === '480' && i.getAttribute('height') === '360' && i.naturalWidth === 480; })()"));
  check("비로그인: 배너가 제목 위", hero.bottom <= (await rect(".page-title")).top);
  check("비로그인: 버튼은 글쓰기 화면으로", (await evaluate("document.querySelector('.home-hero__button').getAttribute('href')")) === "/static/post-form.html");
  if (MOBILE) check("비로그인: 버튼 44px 이상", button.h >= 44, JSON.stringify(button));
  check("비로그인: 가로 스크롤 없음", await noHScroll());
  const guestShift = await layoutShift();
  check("비로그인: 배너 때문에 밀림 없음", guestShift.hero === 0 && (await rect(".home-hero")).h === hero.h, JSON.stringify(guestShift));
  check("비로그인: 페이지 전체 밀림 없음(CLS < 0.01)", guestShift.total < 0.01, JSON.stringify(guestShift));
  await screenshot(`home-guest-${W}.png`);

  // ---------- 로그인: 얇은 띠 ----------
  await setToken(seed.buyer_token);
  await goto("/static/index.html", `${ready} && document.getElementById('site-header').textContent.length > 0`);
  const strip = await rect(".home-hero");
  check("로그인: <html data-signed-in>", await evaluate("document.documentElement.hasAttribute('data-signed-in')"));
  check("로그인: 띠 문구·버튼만(그림·소개 문구 숨김)", (await visible(".home-hero__member")) && (await visible(".home-hero__button")) && !(await visible(".home-hero__image")) && !(await visible(".home-hero__sub")));
  check(`로그인: 띠 높이 ${MOBILE ? 52 : 64}px 이하·한 줄`, strip && strip.h <= (MOBILE ? 52 : 64) && (await rect(".home-hero__member")).top >= strip.top, JSON.stringify(strip));
  const memberShift = await layoutShift();
  check("로그인: 배너(띠) 때문에 밀림 없음", memberShift.hero === 0, JSON.stringify(memberShift));
  check("로그인: 페이지 전체 밀림 없음(CLS < 0.01)", memberShift.total < 0.01, JSON.stringify(memberShift));
  check("로그인: 가로 스크롤 없음", await noHScroll());
  await screenshot(`home-member-${W}.png`);

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
