// 알림(헤더 종·배지·종 알림 판, 알림 화면)과 찾는 교재 화면을 헤드리스 Chrome으로 확인한다.
// 종 배지 = 안 읽은 쪽지 + 안 읽은 찾는 교재 알림. 종을 누르면 종 아래 작은 판(안 읽은 쪽지 대화 + 찾는 교재 알림, 최신순).
// 알림 화면(판의 "전체 보기") = 안 읽은 쪽지 줄 + 찾는 교재 알림 목록.
// 찾는 교재 조건 등록·삭제는 따로 찾는 교재 화면(book-alerts.html, 내 정보에서 진입)에서 한다.
// 사용: WIDTH=375 tools/ui-check/run.sh alerts-check
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { api, loginApi, readSeed, sleep, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const seed = readSeed(OUT);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);

const b = await startBrowser(OUT, { width: W });
const badge = `(() => { const n = document.getElementById('nav-alerts-unread'); return n && !n.hidden ? n.textContent : ''; })()`;
const badgeOf = (n) => (n === 0 ? "" : n > 99 ? "99+" : String(n));
const unreadMessages = async () => (await api("GET", "/conversations/unread-count", seed.buyer_token)).body.unread_count;
const rect = (selector) =>
  b.evaluate(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); if (!e || !e.getClientRects().length) return null; const r = e.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), right: Math.round(r.right) }; })()`);

try {
  await b.goto("/static/index.html");
  await b.evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(seed.buyer_token)})`);

  // ---------- 내 정보 → 찾는 교재 화면에서 조건 등록 ----------
  await b.goto("/static/me.html", "!document.getElementById('account').hidden");
  check("내 정보: '찾는 교재 알림' 행은 찾는 교재 화면으로", (await b.evaluate(`document.querySelector('.settings-row[href="/static/book-alerts.html"]')?.textContent.trim()`)) === "찾는 교재 알림");
  await b.goto("/static/book-alerts.html", "document.getElementById('alert-count').textContent !== ''");
  check("찾는 교재: 제목·'찾는 교재 0/10'", (await b.evaluate(`document.querySelector('h1').textContent + '|' + document.getElementById('alerts-title').textContent`)) === "찾는 교재 알림|찾는 교재 0/10");
  check("찾는 교재: 탭 바 '내 정보' 선택", (await b.evaluate(`document.querySelector('.tab-bar [aria-current=page] .tab-bar__label')?.textContent`)) === "내 정보");
  await b.evaluate(`(() => { const f = document.getElementById('alert-form'); f.keyword.value = '네트워크'; f.max_price.value = '20000'; f.requestSubmit(); })()`);
  check("조건 등록 후 목록 1/10", await b.waitUntil(`document.getElementById('alert-count').textContent === '1/10'`));
  await b.evaluate(`(() => { const f = document.getElementById('alert-form'); f.keyword.value = '네트워크'; f.requestSubmit(); })()`);
  check("중복 키워드 에러", await b.waitUntil(`document.querySelector('[data-error-for=keyword]').textContent.includes('이미')`));
  check("찾는 교재: 가로 스크롤 없음", await b.evaluate(`document.documentElement.scrollWidth <= ${W}`));
  await b.screenshot(`book-alerts-${W}.png`);

  // ---------- 알림 화면(빈 목록): 안 읽은 쪽지 줄, 빈 화면 + 등록 버튼 ----------
  let messages = await unreadMessages();
  await b.goto("/static/alerts.html", "document.getElementById('result-summary').textContent.includes('아직 받은 알림이') && !document.getElementById('unread-messages').hidden");
  check("알림: 제목 '알림', 등록칸·조건 목록 없음", (await b.evaluate(`document.querySelector('h1').textContent`)) === "알림" && !(await b.evaluate(`document.getElementById('alert-form') || document.getElementById('alert-list')`)));
  check("알림: 맨 위 '읽지 않은 쪽지 N개' 줄 → 쪽지함", (await b.evaluate(`(() => { const a = document.querySelector('#unread-messages a'); return a.textContent + '|' + a.getAttribute('href'); })()`)) === `읽지 않은 쪽지 ${messages}개|/static/conversations.html`);
  const register = await rect("#empty-actions a");
  check("알림(빈 목록): 안내 아래 '찾는 교재 등록하기' 버튼 44px", register && register.h >= 44 && (await b.evaluate(`(() => { const a = document.querySelector('#empty-actions a'); return a.textContent === '찾는 교재 등록하기' && a.getAttribute('href') === '/static/book-alerts.html' && a.getBoundingClientRect().top >= document.getElementById('result-summary').getBoundingClientRect().bottom; })()`)), JSON.stringify(register));
  check("종: 판을 여닫는 버튼(닫힌 상태 aria-expanded=false)", (await b.evaluate(`(() => { const n = document.getElementById('nav-alerts'); return n.tagName + '|' + n.getAttribute('aria-expanded') + '|' + n.getAttribute('aria-controls'); })()`)) === "BUTTON|false|notification-panel");

  // ---------- 판매자가 맞는 글 2개, 안 맞는 글 1개 → 종 배지 = 안 읽은 쪽지 + 새 알림 2 ----------
  const post = (title, book_title, price) => api("POST", "/posts", seed.seller_token, { title, book_title, condition: "GOOD", price });
  await post("네트워크 교재 팝니다", "컴퓨터 네트워크 하향식 접근", 15000);
  await post("데이터통신 겸 네트워크", "데이터 통신과 네트워크", 18000);
  await post("비싼 네트워크 책", "네트워크 프로그래밍", 30000);

  messages = await unreadMessages();
  await b.goto("/static/index.html", "document.getElementById('nav-alerts')");
  check(`종 배지 = 쪽지 ${messages} + 알림 2`, await b.waitUntil(`${badge} === ${JSON.stringify(badgeOf(messages + 2))}`), await b.evaluate(badge));
  check("종 이름: '알림, 새 소식 N개'", (await b.evaluate(`document.getElementById('nav-alerts').getAttribute('aria-label')`)) === `알림, 새 소식 ${messages + 2}개`);
  const dot = await rect("#nav-alerts-unread");
  const bell = await rect("#nav-alerts");
  check("종 배지: 빨간 원, 종 오른쪽 위, 종 44px", dot && bell && bell.w >= 44 && bell.h >= 44 && (await b.evaluate(`getComputedStyle(document.getElementById('nav-alerts-unread')).backgroundColor`)) === "rgb(196, 36, 58)", `${JSON.stringify(dot)} ${JSON.stringify(bell)}`);
  // 헤더는 화면을 열 때 안 읽은 수 API를 종류마다 한 번씩만 부른다.
  const calls = await b.evaluate(`performance.getEntriesByType('resource').map((e) => new URL(e.name).pathname).filter((p) => p.endsWith('/unread-count'))`);
  check("헤더: 안 읽은 수 요청은 쪽지·알림 한 번씩", calls.length === 2 && new Set(calls).size === 2, calls.join(", "));
  await b.screenshot(`alerts-badge-${W}.png`);

  // ---------- 종 알림 판: 열 때만·열 때마다 불러옴, 위치·크기, 최신순, 점, 44px, 두 줄 이내 ----------
  const listCalls = () => b.evaluate(`performance.getEntriesByType('resource').map((e) => new URL(e.name).pathname).filter((p) => p === '/notifications' || p === '/conversations').length`);
  const panelOpen = "!document.getElementById('notification-panel').hidden";
  const panelReady = `${panelOpen} && document.querySelector('.notification-panel__status').hidden`;
  const openPanel = async () => {
    await b.evaluate("document.getElementById('nav-alerts').click()");
    return b.waitUntil(panelReady);
  };
  check("판: 열기 전에는 목록을 부르지 않음", (await listCalls()) === 0);
  check("판: 종을 누르면 열림, aria-expanded=true, role=dialog '알림'", (await openPanel()) && (await b.evaluate(`document.getElementById('nav-alerts').getAttribute('aria-expanded') === 'true' && document.getElementById('notification-panel').getAttribute('role') === 'dialog' && document.getElementById('notification-panel').getAttribute('aria-label') === '알림'`)));
  check("판: 열 때 쪽지 대화·찾는 교재 알림 두 목록을 한 번씩", (await listCalls()) === 2, String(await listCalls()));
  const unreadRooms = (await api("GET", "/conversations?size=50", seed.buyer_token)).body.items.filter((r) => r.unread_count > 0);
  const panel = await b.evaluate(`(() => {
    const p = document.getElementById('notification-panel'), r = p.getBoundingClientRect(), bell = document.getElementById('nav-alerts').getBoundingClientRect(), tab = document.querySelector('.tab-bar');
    const items = [...p.querySelectorAll('.notification-panel__item')];
    const times = items.map((a) => a.querySelector('time').getAttribute('datetime'));
    return {
      left: Math.round(r.left), right: Math.round(r.right), top: Math.round(r.top), bottom: Math.round(r.bottom), bellBottom: Math.round(bell.bottom),
      tabTop: Math.round(tab && tab.getClientRects().length ? tab.getBoundingClientRect().top : innerHeight),
      count: items.length, texts: items.map((a) => a.querySelector('.notification-panel__text').textContent), hrefs: items.map((a) => a.getAttribute('href')),
      sorted: times.every((t, i) => i === 0 || times[i - 1] >= t), dots: p.querySelectorAll('.notification-panel__dot').length,
      minH: Math.round(Math.min(...items.map((a) => a.getBoundingClientRect().height))),
      lines: Math.max(...items.map((a) => { const s = a.querySelector('.notification-panel__text'); return Math.round(s.scrollHeight / parseFloat(getComputedStyle(s).lineHeight)); })),
      all: p.querySelector('.notification-panel__all').textContent + '|' + p.querySelector('.notification-panel__all').getAttribute('href'),
    };
  })()`);
  check(`판: 화면 좌우 8px 여백 폭, 종 바로 아래, 하단 탭 위`, panel.left === 8 && panel.right === W - 8 && panel.top >= panel.bellBottom && panel.top - panel.bellBottom <= 8 && panel.bottom <= panel.tabTop, JSON.stringify(panel));
  check(`판: 항목 = 안 읽은 쪽지 대화 ${unreadRooms.length} + 찾는 교재 알림 2, 최신순, 모두 점`, panel.count === unreadRooms.length + 2 && panel.sorted && panel.dots === panel.count, panel.texts.join(" / "));
  check("판: 한 줄 요약 문구", panel.texts.filter((s) => s === "찾는 교재 '네트워크'에 맞는 새 글이 올라왔어요").length === 2 && (unreadRooms.length === 0 || panel.texts.includes("판매자민수님이 쪽지를 보냈어요")), panel.texts.join(" / "));
  check("판: 쪽지 항목은 대화로, 찾는 교재 항목은 글로", panel.hrefs.every((h) => /^\/static\/(chat|post)\.html\?id=\d+$/.test(h)) && panel.hrefs.filter((h) => h.startsWith("/static/post.html")).length === 2, panel.hrefs.join(" "));
  check("판: 항목 44px 이상, 요약은 두 줄 이내", panel.minH >= 44 && panel.lines <= 2, `${panel.minH}px, ${panel.lines}줄`);
  check("판: 맨 아래 '전체 보기' → 알림 화면", panel.all === "전체 보기|/static/alerts.html");
  check("판: 가로 스크롤 없음", await b.evaluate(`document.documentElement.scrollWidth <= ${W}`));
  await b.screenshot(`alerts-panel-${W}.png`);
  await b.evaluate("document.getElementById('nav-alerts').click()");
  check("판: 종을 다시 누르면 닫힘", await b.waitUntil(`document.getElementById('notification-panel').hidden && document.getElementById('nav-alerts').getAttribute('aria-expanded') === 'false'`));
  await openPanel();
  check("판: 열 때마다 다시 불러옴", (await listCalls()) === 4, String(await listCalls()));
  for (const type of ["keyDown", "keyUp"]) await b.send("Input.dispatchKeyEvent", { type, key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
  check("판: Esc로 닫히고 종으로 돌아감", await b.waitUntil(`document.getElementById('notification-panel').hidden && document.activeElement?.id === 'nav-alerts'`));
  await openPanel();
  await b.evaluate("document.querySelector('main').click()");
  check("판: 바깥을 누르면 닫힘", await b.waitUntil("document.getElementById('notification-panel').hidden"));

  // 찾는 교재 항목을 누르면 그 알림만 읽음 처리하고 글로 간다. 종 배지는 하나 줄어든다.
  await openPanel();
  await b.evaluate(`document.querySelector('.notification-panel__item[href^="/static/post.html"]').click()`);
  check("판: 찾는 교재 항목 → 해당 글 화면", await b.waitUntil("location.pathname === '/static/post.html' && !!document.getElementById('nav-alerts')", 8000));
  check("판: 그 알림만 읽음 처리, 종 배지 하나 줄어듦", await b.waitUntil(`${badge} === ${JSON.stringify(badgeOf(messages + 1))}`), await b.evaluate(badge));

  // ---------- 알림 화면: 카드 2개, 읽음 처리 후 배지에서 알림만 빠짐 ----------
  await b.goto("/static/alerts.html", "document.querySelectorAll('.notification-card').length > 0");
  check("알림 카드 2개", (await b.evaluate(`document.querySelectorAll('.notification-card').length`)) === 2);
  check("새 알림 강조(판에서 하나 읽어 1개)", (await b.evaluate(`document.querySelectorAll('.notification-card--unread').length`)) === 1);
  check("알림이 있으면 등록 버튼 숨김", await b.evaluate(`document.getElementById('empty-actions').hidden`));
  check("읽음 처리 후 배지 = 안 읽은 쪽지 수", await b.waitUntil(`${badge} === ${JSON.stringify(badgeOf(messages))}`), await b.evaluate(badge));
  const calls2 = await b.evaluate(`performance.getEntriesByType('resource').map((e) => new URL(e.name).pathname).filter((p) => p.endsWith('/conversations/unread-count'))`);
  check("알림 화면: 쪽지 수는 헤더가 받은 것을 다시 씀(1회)", calls2.length === 1, String(calls2.length));
  check("가로 스크롤 없음", await b.evaluate(`document.documentElement.scrollWidth <= ${W}`));
  await b.screenshot(`alerts-page-${W}.png`);

  // ---------- 쪽지를 읽으면 종 배지도 줄어듦 ----------
  const rooms = (await api("GET", "/conversations?size=50", seed.buyer_token)).body.items;
  const room = rooms.find((r) => r.unread_count > 0);
  if (room) {
    await b.goto(`/static/chat.html?id=${room.id}`, "document.querySelectorAll('.message').length > 0");
    const left = messages - room.unread_count;
    check("쪽지를 읽으면 종 배지도 갱신", await b.waitUntil(`${badge} === ${JSON.stringify(badgeOf(left))}`), `${await b.evaluate(badge)} (기대 ${badgeOf(left) || "숨김"})`);
  } else {
    check("쪽지를 읽으면 종 배지도 갱신", false, "안 읽은 대화방이 없음");
  }

  // ---------- 조건 삭제 ----------
  await b.goto("/static/book-alerts.html", "document.getElementById('alert-count').textContent === '1/10'");
  await b.evaluate(`document.querySelector('.alert-list .link-button--danger').click()`);
  check("조건 삭제 후 0/10", await b.waitUntil(`document.getElementById('alert-count').textContent === '0/10'`));
  // ---------- 알림이 없는 새 사용자: 판에 안내 한 줄 + 찾는 교재 등록하기 ----------
  const email = `bell-empty-${Date.now()}@uicheck.ac.kr`;
  await api("POST", "/auth/signup", null, { email, password: "bell-empty-pw-1234", nickname: `빈종${String(Date.now()).slice(-5)}` });
  const emptyToken = await loginApi(email, "bell-empty-pw-1234");
  await b.evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(emptyToken)})`);
  await b.goto("/static/index.html", "document.getElementById('nav-alerts')");
  await openPanel();
  const emptyPanel = await b.evaluate(`(() => { const p = document.getElementById('notification-panel'), a = p.querySelector('.notification-panel__register'); return { items: p.querySelectorAll('.notification-panel__item').length, text: p.querySelector('.notification-panel__empty p').textContent, link: a.textContent + '|' + a.getAttribute('href'), h: Math.round(a.getBoundingClientRect().height), shown: !p.querySelector('.notification-panel__empty').hidden }; })()`);
  check("판(빈 목록): '새 알림이 없어요' + '찾는 교재 등록하기' 44px", emptyPanel.items === 0 && emptyPanel.shown && emptyPanel.text === "새 알림이 없어요" && emptyPanel.link === "찾는 교재 등록하기|/static/book-alerts.html" && emptyPanel.h >= 44, JSON.stringify(emptyPanel));
  await b.screenshot(`alerts-panel-empty-${W}.png`);

  await sleep(200);
  check("JS 에러 없음", b.exceptions.filter((e) => !String(e).startsWith("Failed to load resource")).length === 0, b.exceptions.join(" | "));
} catch (error) {
  results.push(`ERROR  ${error.message}`);
} finally {
  b.close();
  writeFileSync(join(OUT, "alerts-check.txt"), results.join("\n") + "\n");
  console.log(results.join("\n"));
}
