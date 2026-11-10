// 모바일 사용성 확인 (WIDTH 환경변수: 375 / 390 / 430). 탭 바, 목록 검색·카드, 터치 영역 44px, 글자 16px, 입력칸 16px.
// PHASE=2이면 상세(갤러리·하단 바)와 대화(키보드·포커스)도 확인한다.
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { api, readSeed, seedExtra, sleep, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const H = 812;
const PHASE = Number(process.env.PHASE ?? 2);
const seed = readSeed(OUT);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  [${W}] ${name}${detail ? `  (${detail})` : ""}`);

// 작게 둘 수 있는 글자(배지·날짜·글자 수·탭 이름 등). 이 밖의 글자는 16px 이상이어야 한다.
const SMALL_OK = [
  ".badge", ".nav-badge", ".count-badge", ".tab-bar__label",
  ".post-card__condition", ".post-card__meta",
  ".conversation-card__time", ".conversation-card__role",
  ".message__time", ".chat__count", ".profile-card__meta", ".block-item__meta",
  ".report-card__type", ".report-card__status", ".report-card__meta", ".gallery__counter", ".chat__role",
].join(", ");

// 화면에 보이는 요소 중 규칙에 어긋나는 것을 모은다.
const AUDIT = `(() => {
  const visible = (e) => {
    if (e.getClientRects().length === 0) return false;
    const s = getComputedStyle(e);
    if (s.visibility === 'hidden' || s.opacity === '0') return false;
    if (e.closest('.visually-hidden, [aria-hidden="true"]:not(svg)')) return false;
    const r = e.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };
  const name = (e) => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && typeof e.className === 'string' ? '.' + e.className.trim().split(/\\s+/).join('.') : '') + ' "' + (e.textContent || e.value || e.getAttribute('aria-label') || '').trim().slice(0, 16) + '"';
  const small = [], tiny = [], touch = [], inputs = [];
  // 글자: 직접 글자를 가진 요소
  for (const e of document.body.querySelectorAll('*')) {
    if (!visible(e) || e.closest('svg')) continue;
    const ownText = [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!ownText) continue;
    const size = parseFloat(getComputedStyle(e).fontSize);
    if (e.closest(${JSON.stringify(SMALL_OK)})) { if (size < 12) tiny.push(name(e) + ' ' + size); }
    else if (size < 16) small.push(name(e) + ' ' + size);
  }
  // 누르는 곳: 문장 안의 링크(inline)는 WCAG 예외라 뺀다.
  for (const e of document.body.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, [role=button], label.report-card__choice')) {
    if (!visible(e)) continue;
    if (e.matches('input[type=radio], input[type=checkbox]') && e.closest('label')) continue; // 라벨 전체를 누르는 칸
    if (e.matches('input[type=file]')) continue; // 숨긴 파일 칸 (버튼 모양 label을 누른다)
    if (e.tagName === 'A' && getComputedStyle(e).display === 'inline') continue;
    const r = e.getBoundingClientRect();
    if (r.height < 43.5 || r.width < 43.5) touch.push(name(e) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
  }
  for (const e of document.body.querySelectorAll('input, select, textarea')) {
    if (!visible(e) || e.matches('input[type=radio], input[type=checkbox], input[type=file]')) continue;
    const size = parseFloat(getComputedStyle(e).fontSize);
    if (size < 16) inputs.push(name(e) + ' ' + size);
  }
  const wide = document.documentElement.scrollWidth > ${W} || [...document.body.querySelectorAll('main *, .tab-bar, .tab-bar *')].some((e) => visible(e) && e.getBoundingClientRect().right > ${W} + 0.5 && getComputedStyle(e).position !== 'absolute' && !e.closest('.gallery__track'));
  return { small, tiny, touch, inputs, wide };
})()`;

const { admin } = await seedExtra(OUT, seed);
// 카드가 한 화면에 몇 개 보이는지 보려고 글을 더 만든다. (총 9개)
for (let i = 1; i <= 6; i++) {
  await api("POST", "/posts", seed.seller_token, {
    title: `추가 교재 ${i}번 — 제목이 조금 긴 경우 두 줄까지 보이는지 확인하는 글`,
    book_title: `확인용 교재 ${i}`,
    course_name: "확인과목",
    condition: "GOOD",
    price: 1000 * i,
  });
}

const b = await startBrowser(OUT, { width: W, height: H, mobile: true });
const { evaluate, waitUntil, goto, screenshot } = b;
const setToken = (token) => evaluate(token ? `localStorage.setItem("campus-books.token", ${JSON.stringify(token)})` : "localStorage.clear()");
const ready = "document.fonts.status === 'loaded' && !document.body.textContent.includes('불러오는 중')";

async function audit(label) {
  await waitUntil(ready);
  await sleep(300);
  const a = await evaluate(AUDIT);
  check(`${label}: 가로 스크롤 없음`, !a.wide);
  check(`${label}: 본문 글자 16px 이상`, a.small.length === 0, a.small.slice(0, 6).join(" / "));
  check(`${label}: 작은 글자 예외도 12px 이상`, a.tiny.length === 0, a.tiny.slice(0, 6).join(" / "));
  check(`${label}: 누르는 곳 44px 이상`, a.touch.length === 0, a.touch.slice(0, 6).join(" / "));
  check(`${label}: 입력칸 16px 이상`, a.inputs.length === 0, a.inputs.slice(0, 6).join(" / "));
}

const tabBar = {
  visible: () => evaluate("(() => { const t = document.querySelector('.tab-bar'); return !!t && t.getClientRects().length > 0; })()"),
  current: () => evaluate("document.querySelector('.tab-bar [aria-current=page] .tab-bar__label')?.textContent ?? null"),
};

try {
  await goto("/static/index.html");

  // ---------- 비로그인 목록 ----------
  await setToken(null);
  await goto("/static/index.html", "document.querySelectorAll('.post-card').length > 0");
  check("비로그인: 탭 바 보임, '홈' 선택", (await tabBar.visible()) && (await tabBar.current()) === "홈");
  check("비로그인: 헤더에 로그인·회원가입 남음", await evaluate("[...document.querySelectorAll('.site-nav a')].filter(a => a.getClientRects().length).map(a => a.textContent).join() === '로그인,회원가입'"));
  await audit("비로그인 목록");

  // ---------- 로그인 목록: 탭 바 ----------
  await setToken(seed.buyer_token);
  await goto("/static/index.html", "document.querySelectorAll('.post-card').length > 0 && document.getElementById('nav-messages')");
  check("탭 바: 5개(홈·찜·글쓰기·쪽지·내 정보)", (await evaluate("[...document.querySelectorAll('.tab-bar__label')].map(l => l.textContent).join()")) === "홈,찜,글쓰기,쪽지,내 정보");
  check("탭 바: 화면 맨 아래 고정", await evaluate(`(() => { const r = document.querySelector('.tab-bar').getBoundingClientRect(); return Math.abs(r.bottom - ${H}) < 1 && r.left === 0 && Math.abs(r.right - ${W}) < 1 && getComputedStyle(document.querySelector('.tab-bar')).position === 'fixed'; })()`));
  check("헤더: 로그인 메뉴 숨김(탭 바가 대신)", await evaluate("document.querySelector('.site-nav').getClientRects().length === 0"));
  const unread = (await api("GET", "/conversations/unread-count", seed.buyer_token)).body.unread_count;
  await waitUntil("!document.getElementById('tab-unread').hidden");
  check("탭 바: 쪽지 배지 = 안 읽은 수", (await evaluate("document.getElementById('tab-unread').textContent")) === String(unread) && (await evaluate("document.getElementById('tab-messages').getAttribute('aria-label')")) === `쪽지, 안 읽은 메시지 ${unread}개`, `${unread}`);
  const itemSizes = await evaluate("[...document.querySelectorAll('.tab-bar__item')].map(a => { const r = a.getBoundingClientRect(); return Math.round(r.width) + 'x' + Math.round(r.height); })");
  check("탭 바: 각 탭 44px 이상", itemSizes.every((s) => s.split("x").every((n) => Number(n) >= 44)), itemSizes.join(" "));

  // 검색 한 줄
  const row = await evaluate("(() => { const t = (s) => Math.round(document.querySelector(s).getBoundingClientRect().top); return [t('#q'), t('#search-button'), t('#filter-toggle')]; })()");
  check("검색: 검색창·검색·필터 버튼이 한 줄", new Set(row).size === 1, row.join());
  check("필터: 처음에는 접힘", (await evaluate("document.getElementById('status').getClientRects().length === 0")) && (await evaluate("document.getElementById('filter-toggle').getAttribute('aria-expanded')")) === "false");
  await screenshot(`m1-${W}-list.png`);

  // 카드
  const cards = await evaluate(`(() => [...document.querySelectorAll('.post-list__item')].map(li => {
    const r = li.getBoundingClientRect(), t = li.querySelector('.post-card__thumb').getBoundingClientRect(), title = li.querySelector('.post-card__title').getBoundingClientRect();
    const heart = li.querySelector('.wish-button')?.getBoundingClientRect();
    const texts = [...li.querySelectorAll('.post-card__body > *')].map(e => e.getBoundingClientRect());
    return { top: r.top, height: r.height, thumbW: t.width, thumbH: t.height, thumbRight: t.right, titleLeft: title.left,
      heart: heart ? { w: heart.width, h: heart.height, left: heart.left, top: heart.top, bottom: heart.bottom, right: heart.right, cardRight: r.right, cardBottom: r.bottom } : null,
      overlap: heart ? texts.some(x => x.right > heart.left + 0.5 && x.bottom > heart.top + 0.5 && x.top < heart.bottom - 0.5) : false };
  }))()`);
  check("카드: 사진 96px 왼쪽, 글자는 오른쪽", cards.every((c) => Math.round(c.thumbW) === 96 && Math.round(c.thumbH) === 96 && c.thumbRight < c.titleLeft));
  check("카드: 높이 170px 이하", cards.every((c) => c.height <= 170), cards.map((c) => Math.round(c.height)).join());
  const tabTop = await evaluate("document.querySelector('.tab-bar').getBoundingClientRect().top");
  const fullyVisible = cards.filter((c) => c.top >= 0 && c.top + c.height <= tabTop).length;
  const startVisible = cards.filter((c) => c.top < tabTop).length;
  check("카드: 첫 화면에 4장 이상 보임", startVisible >= 4, `시작 ${startVisible}장, 전부 보임 ${fullyVisible}장`);
  const hearts = cards.filter((c) => c.heart);
  check("카드: 하트 44px, 오른쪽 아래, 글자와 안 겹침", hearts.length > 0 && hearts.every((c) => c.heart.w >= 44 && c.heart.h >= 44 && c.heart.cardRight - c.heart.right < 12 && c.heart.cardBottom - c.heart.bottom < 12 && !c.overlap), JSON.stringify(hearts[0]?.heart));
  await audit("로그인 목록");

  // 필터 펼치기
  await evaluate("document.getElementById('filter-toggle').click()");
  check("필터: 누르면 펼쳐짐(상태·과목·가격)", (await evaluate("['status', 'course_name', 'min_price', 'max_price'].every(id => document.getElementById(id).getClientRects().length > 0)")) && (await evaluate("document.getElementById('filter-toggle').getAttribute('aria-expanded')")) === "true");
  await audit("필터 펼친 목록");
  await screenshot(`m1-${W}-filter-open.png`);
  await evaluate("document.getElementById('status').value = 'ON_SALE'; document.getElementById('min_price').value = '1000'; document.querySelector('#filter-more button[type=submit]').click()");
  await waitUntil("location.search.includes('status=ON_SALE') && document.getElementById('result-summary').textContent.startsWith('총')");
  check("필터: 검색하면 접히고 '필터 2' 표시", (await evaluate("document.getElementById('status').getClientRects().length === 0")) && (await evaluate("document.querySelector('.filter-form__count').textContent")) === "2" && (await evaluate("document.getElementById('filter-toggle').getAttribute('aria-label')")) === "필터, 2개 적용됨");
  await goto("/static/index.html?min_price=5000&max_price=1000", "!document.getElementById('filter-error').hidden || document.querySelector('[aria-invalid=true]')");
  check("필터: 접힌 칸 오류(최소>최대)면 자동으로 펼침", (await evaluate("document.getElementById('max_price').getClientRects().length > 0")) && (await evaluate("document.getElementById('filter-toggle').getAttribute('aria-expanded')")) === "true");
  await goto("/static/index.html?q=%EC%B6%94%EA%B0%80", "document.getElementById('result-summary').textContent.startsWith('총')");
  check("검색: 검색어만이면 필터 개수 없음", await evaluate("document.querySelector('.filter-form__count').hidden && document.getElementById('q').value === '추가'"));

  // 마지막 카드·페이지 버튼이 탭 바에 가리지 않음
  await goto("/static/index.html", "document.querySelectorAll('.post-card').length > 0");
  await evaluate("window.scrollTo(0, document.documentElement.scrollHeight)");
  await sleep(200);
  check("목록 맨 아래: 페이지 버튼·마지막 카드가 탭 바 위", await evaluate("(() => { const top = document.querySelector('.tab-bar').getBoundingClientRect().top; const last = [...document.querySelectorAll('.post-list__item, .pagination > *')].pop().getBoundingClientRect(); return last.bottom <= top; })()"));

  // ---------- 탭별 화면 ----------
  const pages = [
    ["찜", "/static/wishlist.html", "찜"],
    ["쪽지함", "/static/conversations.html", "쪽지"],
    ["차단 목록", "/static/blocks.html", "내 정보"],
  ];
  for (const [label, path, tab] of pages) {
    await goto(path, ready);
    check(`${label}: 탭 바 '${tab}' 선택`, (await tabBar.visible()) && (await tabBar.current()) === tab);
    await audit(label);
  }

  // 내 정보(판매자): 로그아웃 버튼
  await setToken(seed.seller_token);
  await goto("/static/my-posts.html", "!document.getElementById('profile').hidden");
  check("내 정보: 탭 바 '내 정보' 선택", (await tabBar.current()) === "내 정보");
  check("내 정보: 로그아웃 버튼(일반 사용자는 관리 없음)", await evaluate("(() => { const t = [...document.querySelectorAll('.profile-card__actions > *')].filter(e => e.getClientRects().length).map(e => e.textContent); return t.includes('로그아웃') && !t.includes('관리'); })()"));
  await audit("내 정보(판매자)");
  await screenshot(`m1-${W}-my.png`);

  // 관리자: 내 정보 안에 관리
  await setToken(admin);
  await goto("/static/my-posts.html", "!document.getElementById('profile').hidden");
  check("관리자 내 정보: '관리' 버튼", await evaluate("[...document.querySelectorAll('.profile-card__actions a')].some(a => a.textContent === '관리' && a.getClientRects().length && a.getAttribute('href') === '/static/admin.html')"));
  await goto("/static/admin.html", ready + " && document.querySelectorAll('.report-card').length > 0");
  check("관리: 탭 바 '내 정보' 선택", (await tabBar.current()) === "내 정보");
  await audit("관리");
  await goto("/static/my-posts.html", "!document.getElementById('profile').hidden");
  await evaluate("[...document.querySelectorAll('.profile-card__actions button')].find(b => b.textContent === '로그아웃').click()");
  await waitUntil("!localStorage.getItem('campus-books.token') && document.readyState === 'complete'");
  check("내 정보: 로그아웃하면 토큰 삭제", await evaluate("!localStorage.getItem('campus-books.token')"));

  // ---------- 탭 바가 없는 화면 ----------
  await setToken(seed.buyer_token);
  const noTab = [
    ["상세", `/static/post.html?id=${seed.p1}`],
    ["대화", `/static/chat.html?id=${seed.c2}`],
    ["글쓰기", "/static/post-form.html"],
  ];
  for (const [label, path] of noTab) {
    await goto(path, ready);
    check(`${label}: 탭 바 없음`, !(await tabBar.visible()));
    await audit(label);
  }
  await setToken(null);
  for (const [label, path] of [["로그인", "/static/login.html"], ["회원가입", "/static/signup.html"]]) {
    await goto(path, ready);
    check(`${label}: 탭 바 없음`, !(await tabBar.visible()));
    await audit(label);
  }

  // =================== 2차: 상세(사진 넘기기·하단 연락 바), 대화(키보드·포커스) ===================
  if (PHASE >= 2) {
    const { send } = b;
    const center = (selector) =>
      evaluate(`(() => { const r = document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect(); return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) }; })()`);
    // 손가락으로 누르기 (터치 시작·끝 이벤트: pointerdown·touchstart·click·포커스가 실제 터치처럼 일어난다)
    const tap = async (selector) => {
      const p = await center(selector);
      await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: p.x, y: p.y }] });
      await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
      await sleep(400);
    };
    // 손가락으로 가로로 밀기. dx가 음수면 왼쪽으로 민다(다음 사진).
    const swipe = async (selector, dx) => {
      const p = await center(selector);
      const startX = p.x - Math.round(dx / 2);
      await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: startX, y: p.y }] });
      for (let i = 1; i <= 10; i++) {
        await send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: startX + Math.round((dx * i) / 10), y: p.y }] });
        await sleep(16);
      }
      await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
      await sleep(900);
    };

    // ---------- 상세: 사진 넘기기 (p1: 사진 3장) ----------
    await setToken(seed.buyer_token);
    const detailReady = "!document.getElementById('post-detail').hidden && [...document.querySelectorAll('.gallery__main')].every(i => i.complete)";
    await goto(`/static/post.html?id=${seed.p1}`, detailReady);
    await waitUntil(ready);
    await sleep(300);
    const gallery = () =>
      evaluate(`(() => { const t = document.querySelector('.gallery__track'); return { index: Math.round(t.scrollLeft / t.clientWidth), snapped: Math.abs(t.scrollLeft - Math.round(t.scrollLeft / t.clientWidth) * t.clientWidth) < 1, counter: document.querySelector('.gallery__counter').textContent, pressed: [...document.querySelectorAll('.gallery__thumb')].findIndex(b => b.getAttribute('aria-pressed') === 'true'), pageX: scrollX }; })()`);
    check("상세 사진: 사진마다 칸 너비 한 장, 3장이 가로 줄", await evaluate("(() => { const t = document.querySelector('.gallery__track'); const s = [...t.querySelectorAll('.gallery__main')]; return s.length === 3 && s.every(i => Math.abs(i.getBoundingClientRect().width - t.clientWidth) < 1) && Math.abs(t.scrollWidth - t.clientWidth * 3) < 2; })()"));
    check("상세 사진: '1 / 3'이 사진 오른쪽 아래에", await evaluate("(() => { const f = document.querySelector('.gallery__frame').getBoundingClientRect(), e = document.querySelector('.gallery__counter'), c = e.getBoundingClientRect(); return e.textContent === '1 / 3' && c.width > 0 && c.right <= f.right && c.bottom <= f.bottom && f.right - c.right < 20 && f.bottom - c.bottom < 20; })()"));
    await screenshot(`m2-${W}-detail-top.png`);
    await swipe(".gallery__track", -Math.round(W * 0.6));
    let g = await gallery();
    check("상세 사진: 왼쪽으로 밀면 2번째 사진에 딱 맞춰 멈춤", g.index === 1 && g.snapped && g.counter === "2 / 3" && g.pressed === 1 && g.pageX === 0, JSON.stringify(g));
    await swipe(".gallery__track", -Math.round(W * 0.6));
    g = await gallery();
    check("상세 사진: 한 번 더 밀면 '3 / 3'", g.index === 2 && g.snapped && g.counter === "3 / 3" && g.pressed === 2, JSON.stringify(g));
    await swipe(".gallery__track", -Math.round(W * 0.6));
    g = await gallery();
    check("상세 사진: 마지막에서 더 밀어도 그대로", g.index === 2 && g.counter === "3 / 3", JSON.stringify(g));
    await swipe(".gallery__track", Math.round(W * 0.6));
    g = await gallery();
    check("상세 사진: 오른쪽으로 밀면 이전 사진", g.index === 1 && g.snapped && g.counter === "2 / 3", JSON.stringify(g));
    await tap(".gallery__thumb:first-child");
    g = await gallery();
    check("상세 사진: 작은 사진을 누르면 그 사진으로", g.index === 0 && g.counter === "1 / 3" && g.pressed === 0, JSON.stringify(g));
    await screenshot(`m2-${W}-detail-swiped.png`);

    // ---------- 상세: 하단 연락 바 ----------
    const barInfo = () =>
      evaluate(`(() => { const b = document.querySelector('.contact-bar'); if (!b || b.hidden) return null; const r = b.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, height: r.height, position: getComputedStyle(b).position, items: [...b.querySelectorAll('.contact-bar__row > *')].map(e => e.className.split(' ')[0] + ':' + (e.textContent || '').trim()) }; })()`);
    let bar = await barInfo();
    check("연락 바: 화면 맨 아래 고정", bar !== null && bar.position === "fixed" && Math.abs(bar.bottom - H) < 1 && bar.left === 0 && Math.abs(bar.right - W) < 1, JSON.stringify(bar));
    check("연락 바: 찜 하트 · 가격 · 쪽지로 문의하기", bar !== null && bar.items.length === 3 && bar.items[0].startsWith("wish-button") && bar.items[1] === "contact-bar__price:15,000원" && bar.items[2] === "button:쪽지로 문의하기", bar?.items.join(" | "));
    check("연락 바: 바 높이 80px 이하", bar !== null && bar.height <= 80, `${Math.round(bar?.height)}px`);
    check("연락 바: 글 영역에는 오픈채팅만 남고 위쪽 하트는 바로 옮김", await evaluate("(() => { const c = document.querySelector('.post-detail__contact'); return !c.hidden && [...c.querySelectorAll('.button')].map(b => b.textContent).join() === '오픈채팅으로 연락하기' && document.querySelector('.post-detail__top .wish-button') === null && document.querySelectorAll('.wish-button').length === 1; })()"));
    const barHeart = "document.querySelector('.contact-bar .wish-button')";
    const heartBefore = await evaluate(`${barHeart}.getAttribute('aria-pressed')`);
    await tap(".contact-bar .wish-button");
    await waitUntil(`${barHeart}.getAttribute('aria-pressed') !== ${JSON.stringify(heartBefore)}`);
    const wished = (await api("GET", "/users/me/wishlist", seed.buyer_token)).body?.items?.some((p) => p.id === seed.p1);
    check("연락 바: 하트를 누르면 찜 상태가 바뀜(서버 반영)", (await evaluate(`${barHeart}.getAttribute('aria-pressed')`)) !== heartBefore && wished === (heartBefore !== "true"), `${heartBefore} → ${await evaluate(`${barHeart}.getAttribute('aria-pressed')`)}`);
    await tap(".contact-bar .wish-button"); // 원래대로
    await waitUntil(`${barHeart}.getAttribute('aria-pressed') === ${JSON.stringify(heartBefore)}`);
    await evaluate("window.scrollTo(0, document.documentElement.scrollHeight)");
    await sleep(300);
    bar = await barInfo();
    check("연락 바: 맨 아래까지 내려도 신고·차단 버튼이 바 위에 보임", await evaluate(`(() => { const r = document.querySelector('.post-detail__safety').getBoundingClientRect(); return r.bottom <= ${bar?.top ?? 0} + 0.5; })()`));
    await screenshot(`m2-${W}-detail-bottom.png`);
    await evaluate("window.scrollTo(0, 0)");

    // PC 폭으로 바뀌면(화면 회전·창 크기) 하트와 문의 버튼을 원래 자리로
    await b.setMetrics(1024, H);
    await sleep(400);
    check("상세: PC 폭으로 바꾸면 바 숨김, 하트·문의 버튼 원래 자리", await evaluate("document.querySelector('.contact-bar').hidden && !document.body.classList.contains('has-contact-bar') && !!document.querySelector('.post-detail__top .wish-button') && !!document.querySelector('.post-detail__contact-actions > #inquiry-button:first-child') && !document.querySelector('.post-detail__contact').hidden"));
    await b.setMetrics(W, H);
    await sleep(400);
    check("상세: 다시 모바일 폭이면 바로 돌아옴", (await barInfo())?.items.length === 3);

    // 문의하기 → 대화 화면
    await tap(".contact-bar #inquiry-button");
    await waitUntil("location.pathname === '/static/chat.html' && !document.getElementById('chat').hidden");
    check("연락 바: 쪽지로 문의하기 → 대화 화면", await evaluate(`location.pathname === '/static/chat.html' && location.search === '?id=${seed.c1}'`), await evaluate("location.href"));

    // 비로그인: 로그인하고 문의하기
    await setToken(null);
    await goto(`/static/post.html?id=${seed.p1}`, detailReady);
    check("비로그인 연락 바: 하트 · 가격 · '로그인하고 문의하기'(로그인 화면으로)", await evaluate("(() => { const a = document.querySelector('.contact-bar a.button'); return !document.querySelector('.contact-bar').hidden && !!document.querySelector('.contact-bar .wish-button') && !!a && a.textContent === '로그인하고 문의하기' && a.getAttribute('href').startsWith('/static/login.html'); })()"));
    await audit("비로그인 상세(연락 바)");

    // 내 글: 바 없음 (내 글 관리가 있다)
    await setToken(seed.seller_token);
    await goto(`/static/post.html?id=${seed.p1}`, "!document.getElementById('owner-panel').hidden");
    check("내 글 상세: 연락 바 없음", await evaluate("document.querySelector('.contact-bar').hidden && !document.body.classList.contains('has-contact-bar')"));

    // ---------- 대화: 키보드·포커스 ----------
    await setToken(seed.buyer_token);
    await goto(`/static/chat.html?id=${seed.c2}`, "!document.getElementById('chat').hidden");
    await waitUntil(ready);
    await sleep(400);
    const layout = () =>
      evaluate(`(() => { const r = (s) => document.querySelector(s).getBoundingClientRect(); const ta = r('#content'), btn = r('#message-form button[type=submit]'), sc = r('#chat-scroll'), s = document.getElementById('chat-scroll');
        return { taRight: Math.round(ta.right), taBottom: Math.round(ta.bottom), btnLeft: Math.round(btn.left), btnBottom: Math.round(btn.bottom), btnH: Math.round(btn.height), formBottom: Math.round(r('#message-form').bottom), scrollH: Math.round(sc.height), docH: document.documentElement.scrollHeight, vv: Math.round(visualViewport.height), header: document.getElementById('site-header').getClientRects().length > 0, back: document.querySelector('.back-link').getClientRects().length > 0, atBottom: s.scrollHeight - s.scrollTop - s.clientHeight < 2, scrollY }; })()`);
    const normal = await layout();
    check("대화: 입력창 오른쪽에 보내기 버튼(같은 줄, 48px)", normal.btnLeft >= normal.taRight && Math.abs(normal.btnBottom - normal.taBottom) <= 1 && normal.btnH >= 48, JSON.stringify(normal));
    check("대화: 페이지 스크롤 없이 화면 높이에 맞음", normal.docH <= H + 1 && normal.formBottom <= H && normal.scrollY === 0, JSON.stringify(normal));
    await screenshot(`m2-${W}-chat.png`);

    await tap("#content");
    check("대화: 입력창을 누르면 포커스 + 입력 중 표시", await evaluate("document.activeElement?.id === 'content' && document.body.classList.contains('is-typing')"));
    // 키보드가 올라온 것처럼 보이는 높이를 줄인다. (아이폰 키보드를 올리면 보이는 높이가 400px 안팎이 된다)
    const KB = 400;
    await b.setMetrics(W, KB);
    await sleep(600);
    const typing = await layout();
    check(`대화 키보드(보이는 높이 ${KB}px): 입력창·보내기 버튼이 화면 안, 페이지 안 밀림`, typing.vv === KB && typing.formBottom <= KB && typing.btnBottom <= KB && typing.docH <= KB + 1 && typing.scrollY === 0, JSON.stringify(typing));
    check("대화 키보드: 헤더·'← 쪽지함' 접고 메시지 영역 96px 이상", !typing.header && !typing.back && typing.scrollH >= 96, `메시지 영역 ${typing.scrollH}px`);
    check("대화 키보드: 마지막 메시지가 보임(맨 아래)", typing.atBottom);
    check("대화 키보드: 높이 변수 = 보이는 높이", (await evaluate("getComputedStyle(document.documentElement).getPropertyValue('--chat-viewport-height').trim()")) === `${KB}px`);
    await audit("대화(입력 중)");
    await screenshot(`m2-${W}-chat-typing.png`);

    // 글자를 입력하고 보내기 버튼을 손가락으로 누른다. 그동안 입력창에서 포커스가 한 번도 빠지지 않아야 키보드가 유지된다.
    await evaluate("window.__blurCount = 0; document.getElementById('content').addEventListener('blur', () => window.__blurCount++)");
    await send("Input.insertText", { text: "모바일에서 보낸 메시지" });
    const before = await evaluate("document.querySelectorAll('.message').length");
    await tap("#message-form button[type=submit]");
    const sent = await waitUntil(`document.querySelectorAll('.message').length > ${before} && document.querySelector('.message:last-child .message__bubble').textContent === '모바일에서 보낸 메시지'`);
    await sleep(300);
    check("대화: 보내기 버튼을 눌러 전송, 입력창 비움", sent && (await evaluate("document.getElementById('content').value")) === "");
    check("대화: 보내는 동안 입력창 포커스가 빠지지 않음(키보드 유지)", (await evaluate("window.__blurCount")) === 0 && (await evaluate("document.activeElement?.id")) === "content", `blur ${await evaluate("window.__blurCount")}회`);
    check("대화: 보낸 메시지가 보이도록 맨 아래", (await layout()).atBottom);

    // 키보드를 내림
    await evaluate("document.activeElement.blur()");
    await b.setMetrics(W, H);
    await sleep(600);
    const after = await layout();
    check("대화: 입력을 마치면 헤더 다시 보이고 높이 원래대로", after.header && after.back && after.vv === H && after.docH <= H + 1 && after.formBottom <= H, JSON.stringify(after));
  }

  check("JS 예외·콘솔 에러 없음", b.exceptions.filter((e) => !String(e).includes("Failed to load resource")).length === 0, b.exceptions.join(" / "));
} catch (error) {
  results.push(`ERROR  ${error.stack}`);
} finally {
  writeFileSync(join(OUT, "mobile-check.txt"), results.join("\n"));
  b.close();
}
