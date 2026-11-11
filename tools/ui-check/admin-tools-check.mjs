// 관리 화면(메뉴·대시보드·신고 처리 사유·관리 기록·사용자 관리)을 모바일 폭(기본 375px)으로 확인한다.
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { api, loginApi, makeAdmin, readSeed, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const seed = readSeed(OUT);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);

// 준비: 관리자 계정과 신고 2건 (구매자가 판매자의 글 p2를, 판매자가 구매자의 글 p3를 신고)
const PASSWORD = "check-password-123";
await api("POST", "/auth/signup", null, { email: "admin@uicheck.ac.kr", password: PASSWORD, nickname: "관리자" });
await makeAdmin(OUT, "admin@uicheck.ac.kr");
const admin = await loginApi("admin@uicheck.ac.kr", PASSWORD);
const r1 = (await api("POST", `/posts/${seed.p2}/reports`, seed.buyer_token, { reason: "SPAM" })).body.id;
const r2 = (await api("POST", `/posts/${seed.p3}/reports`, seed.seller_token, { reason: "FRAUD" })).body.id;
check("준비: 신고 2건", Boolean(r1 && r2));

const browser = await startBrowser(OUT, { width: W });
const { evaluate, waitUntil, goto, screenshot, exceptions } = browser;
const setToken = (token) => evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(token)})`);
const noHorizontalScroll = () => evaluate(`document.documentElement.scrollWidth <= window.innerWidth`);
const text = (selector) => evaluate(`document.querySelector(${JSON.stringify(selector)})?.textContent ?? ""`);
const autoConfirm = () => evaluate("window.confirm = (m) => { window.lastConfirm = m; return true; }");
const card = (id) => `[...document.querySelectorAll('.report-card')].find((c) => c.querySelector('.report-card__reason').textContent.startsWith('#${id} '))`;
// 관리 메뉴: 항목 이름, 현재 화면 표시, 누르는 곳 높이
const navInfo = () =>
  evaluate(`(() => { const items = [...document.querySelectorAll("#admin-nav .admin-nav__item")];
    return { labels: items.map((a) => a.textContent), current: document.querySelector("#admin-nav [aria-current=page]")?.textContent ?? null,
      minHeight: Math.min(...items.map((a) => Math.round(a.getBoundingClientRect().height))) }; })()`);

try {
  // 1) 일반 사용자는 관리 기록 화면에 들어올 수 없다.
  await goto("/static/index.html");
  await setToken(seed.buyer_token);
  await goto("/static/admin-log.html", "location.pathname === '/static/index.html'");
  check("일반 사용자: 관리 기록 → 목록으로", (await evaluate("location.pathname")) === "/static/index.html");

  // 1-2) 대시보드: 헤더의 "관리" 링크, 숫자 타일
  await setToken(admin);
  await goto("/static/index.html", "document.querySelector('.site-nav a[href*=admin]')");
  const adminLink = await evaluate(`document.querySelector('.site-nav a[href*=admin]').getAttribute('href')`);
  check("헤더 '관리' 링크는 대시보드", adminLink === "/static/admin-dashboard.html", adminLink);
  await goto("/static/admin-dashboard.html", "!document.getElementById('dashboard').hidden");
  const tiles = await evaluate(`Object.fromEntries([...document.querySelectorAll(".stat-tile")].map((t) => [t.querySelector(".stat-tile__label").textContent, t.querySelector(".stat-tile__value").textContent]))`);
  check("대시보드: 미처리 신고 2, 가입자 3, 전체 글 3, 판매 중 3", tiles["미처리 신고"] === "2" && tiles["가입자"] === "3" && tiles["전체 글"] === "3" && tiles["판매 중"] === "3", JSON.stringify(tiles));
  check("대시보드: 오늘 가입 3·오늘 작성 3", tiles["오늘 가입"] === "3" && tiles["오늘 작성"] === "3", JSON.stringify(tiles));
  check("대시보드: 미처리 신고에 '처리 필요' 이름표", (await text(".stat-tile--alert .stat-tile__alert")) === "처리 필요");
  const grid = await evaluate(`(() => { const t = [...document.querySelectorAll("#stat-users .stat-tile")].map((x) => x.getBoundingClientRect()); return { cols: new Set(t.map((r) => Math.round(r.left))).size, minH: Math.min(...t.map((r) => Math.round(r.height))) }; })()`);
  check("대시보드: 375px에서 타일 2열, 높이 44px 이상", grid.cols === 2 && grid.minH >= 44, JSON.stringify(grid));
  check("대시보드: 관리 메뉴 현재 화면", (await navInfo()).current === "대시보드");
  check("대시보드 가로 넘침 없음", await noHorizontalScroll());
  await screenshot(`admin-tools-dashboard-${W}.png`);
  await evaluate(`document.querySelector(".stat-tile--link").click()`);
  await waitUntil("location.pathname === '/static/admin.html'");
  check("미처리 신고 타일 → 신고 화면", (await evaluate("location.pathname + location.search")) === "/static/admin.html?status=PENDING");

  // 2) 신고 화면: 관리 메뉴, 강제 조치의 사유 필수
  await setToken(admin);
  await goto("/static/admin.html", "document.querySelectorAll('.report-card').length === 2");
  const nav = await navInfo();
  check("신고 화면: 관리 메뉴와 현재 화면", nav.current === "신고" && nav.labels.includes("기록"), JSON.stringify(nav));
  check("관리 메뉴: 누르는 곳 44px 이상", nav.minHeight >= 44, String(nav.minHeight));
  await autoConfirm();
  await evaluate(`${card(r1)}.querySelector('input[value=SUSPEND]').click()`);
  check("정지 선택: 사유 칸이 '(필수)'", (await evaluate(`${card(r1)}.querySelector('.field label').textContent`)) === "처리 사유 (필수)");
  await evaluate(`${card(r1)}.querySelector('button[type=submit]').click()`);
  const error = await evaluate(`${card(r1)}.querySelector('.form-error').textContent`);
  check("사유 없이 정지: 보내기 전에 안내", error.includes("처리 사유를 입력해 주세요"), error);
  check("사유 없이 정지: 서버에 보내지 않음(확인 창 없음)", (await evaluate("window.lastConfirm ?? null")) === null);
  await evaluate(`${card(r1)}.querySelector('input[value=DISMISS]').click()`);
  check("기각 선택: 사유 칸이 '(기각은 선택)'", (await evaluate(`${card(r1)}.querySelector('.field label').textContent`)) === "처리 사유 (기각은 선택)");
  await evaluate(`${card(r1)}.querySelector('input[value=SUSPEND]').click()`);
  await evaluate(`${card(r1)}.querySelector('textarea').value = '광고 글 반복'`);
  await evaluate(`${card(r1)}.querySelector('button[type=submit]').click()`);
  check("사유를 넣고 정지 처리", await waitUntil("!document.getElementById('admin-notice').hidden"), await text("#admin-notice"));
  await evaluate(`${card(r2)}.querySelector('input[value=DISMISS]').click()`);
  await evaluate(`${card(r2)}.querySelector('button[type=submit]').click()`);
  check("사유 없이 기각 처리", await waitUntil("document.querySelectorAll('.report-card').length === 0"));
  check("신고 화면 가로 넘침 없음", await noHorizontalScroll());
  await screenshot(`admin-tools-reports-${W}.png`);

  // 3) 관리 기록 화면
  await goto("/static/admin-log.html", "document.querySelectorAll('#log-list li').length === 2");
  check("기록: 2건, 최신순(기각 → 정지)", JSON.stringify(await evaluate(`[...document.querySelectorAll("#log-list .admin-badge")].map((b) => b.textContent)`)) === JSON.stringify(["신고 기각", "기간 정지"]));
  const suspendCard = await evaluate(`document.querySelectorAll("#log-list li")[1].textContent`);
  check("기록: 관리자 → 대상, 사유, 정지 일수", suspendCard.includes("관리자 → 판매자민수") && suspendCard.includes("사유: 광고 글 반복") && suspendCard.includes("1일 정지"), suspendCard);
  check("기록: 기각은 '사유 없음'", (await evaluate(`document.querySelectorAll("#log-list li")[0].textContent`)).includes("사유 없음"));
  check("기록: 이메일 없음", !(await evaluate(`document.body.textContent.includes("@uicheck.ac.kr")`)));
  check("기록: 관리 메뉴 현재 화면", (await navInfo()).current === "기록");
  check("기록 화면 가로 넘침 없음", await noHorizontalScroll());
  await screenshot(`admin-tools-log-${W}.png`);
  await evaluate(`(() => { const s = document.getElementById("filter-action"); s.value = "SUSPEND"; s.dispatchEvent(new Event("change")); })()`);
  await waitUntil("location.search.includes('action=SUSPEND') && document.querySelectorAll('#log-list li').length === 1");
  check("기록: 조치 필터(정지만 1건)", (await text("#result-summary")) === "총 1건", await text("#result-summary"));
  const tab = await evaluate(`document.querySelector(".tab-bar [aria-current=page]")?.textContent ?? ""`);
  check("하단 탭 바: 관리 화면은 '내 정보' 탭", tab.includes("내 정보"), tab);

  // 4) 관리 기록의 대상 사용자 → 사용자 상세
  await evaluate(`document.querySelector("#log-list .admin-user-link").click()`);
  await waitUntil("location.pathname === '/static/admin-user.html' && !document.getElementById('user-detail').hidden");
  check("기록의 대상 이름 → 사용자 상세", (await text("#user-title")) === "판매자민수", await text("#user-title"));

  // 5) 사용자 목록: 이메일, 상태 이름표, 검색·필터
  await goto("/static/admin-users.html", "document.querySelectorAll('#user-list li').length === 3");
  check("사용자 목록: 3명, 메뉴 현재 화면", (await navInfo()).current === "사용자");
  const sellerCard = await evaluate(`[...document.querySelectorAll("#user-list li")].find((li) => li.textContent.includes("판매자민수")).textContent`);
  check("사용자 목록: 이메일·정지 이름표·글 수", sellerCard.includes("seller@uicheck.ac.kr") && sellerCard.includes("까지 정지") && sellerCard.includes("글 2개"), sellerCard);
  check("사용자 목록 가로 넘침 없음", await noHorizontalScroll());
  await screenshot(`admin-tools-users-${W}.png`);
  await evaluate(`(() => { const s = document.getElementById("filter-status"); s.value = "SUSPENDED"; s.dispatchEvent(new Event("change")); })()`);
  await waitUntil("location.search.includes('status=SUSPENDED') && document.querySelectorAll('#user-list li').length === 1");
  check("상태 필터: 정지 중 1명", (await text("#user-list li .admin-card__title")) === "판매자민수");
  await evaluate(`document.getElementById("filter-status").value = ""; document.getElementById("search-q").value = "BUYER@uicheck"; document.querySelector("#user-search button[type=submit]").click()`);
  await waitUntil("location.search.includes('q=') && document.querySelectorAll('#user-list li').length === 1");
  check("이메일 검색(대소문자 무시)", (await text("#user-list li .admin-card__title")) === "구매자지은");
  await evaluate(`document.getElementById("search-q").value = "없는사람"; document.querySelector("#user-search button[type=submit]").click()`);
  await waitUntil("document.getElementById('result-summary').textContent.includes('없습니다')");
  check("검색 결과 없음 안내", (await text("#result-summary")) === "조건에 맞는 사용자가 없습니다.");

  // 6) 사용자 상세: 계정 정보, 활동 수, 정지 이력, 신고 화면 필터로 이어짐
  await goto("/static/admin-users.html?q=판매자", "document.querySelectorAll('#user-list li').length === 1");
  await evaluate(`document.querySelector("#user-list .admin-card__title").click()`);
  await waitUntil("!document.getElementById('user-detail').hidden");
  const infoText = await text("#user-info");
  check("상세: 이메일·번호", infoText.includes("seller@uicheck.ac.kr") && infoText.includes("#"), infoText);
  const counts = await evaluate(`Object.fromEntries([...document.querySelectorAll("#user-counts .stat-tile")].map((t) => [t.querySelector(".stat-tile__label").textContent, t.querySelector(".stat-tile__value").textContent]))`);
  check("상세: 글 2·받은 신고 1·미처리 0", counts["작성한 글"] === "2" && counts["받은 신고"] === "1" && counts["미처리 신고"] === "0", JSON.stringify(counts));
  const history = await text("#suspension-list");
  check("상세: 정지 이력(사유 포함)", history.includes("기간 정지") && history.includes("광고 글 반복"), history);
  check("상세: 메뉴는 '사용자'가 아님(상세는 메뉴에 없음)", (await navInfo()).current === null);
  check("상세 가로 넘침 없음", await noHorizontalScroll());
  await screenshot(`admin-tools-user-${W}.png`);
  await evaluate(`[...document.querySelectorAll("#user-counts a")].find((a) => a.textContent.includes("받은 신고")).click()`);
  await waitUntil("location.pathname === '/static/admin.html' && document.querySelectorAll('.report-card').length === 1");
  check("받은 신고 → 그 사용자 신고만", (await text("#filter-user")).includes("신고당한 것만 보는 중"), await text("#filter-user"));
  const tabHref = await evaluate(`document.querySelector('.tabs__item[data-status=PENDING]').getAttribute('href')`);
  check("신고 탭이 사용자 필터를 유지", tabHref.includes("reported_user_id="), tabHref);
  check("신고 카드의 대상 이름은 상세 링크", (await evaluate(`document.querySelector(".report-card__people strong a")?.getAttribute("href") ?? ""`)).startsWith("/static/admin-user.html?id="));

  // 7) 사용자 상세에서 정지 해제·직접 정지 (사유 필수, 확인 창)
  await goto("/static/admin-users.html?q=판매자", "document.querySelectorAll('#user-list li').length === 1");
  await evaluate(`document.querySelector("#user-list .admin-card__title").click()`);
  await waitUntil("!document.getElementById('user-detail').hidden");
  check("상세(정지 중): 정지·정지 해제 폼", Boolean(await evaluate(`document.getElementById("suspend-form") && document.getElementById("unsuspend-form")`)));
  await autoConfirm();
  await evaluate(`window.lastConfirm = null; document.querySelector("#unsuspend-form button[type=submit]").click()`);
  check("사유 없이 해제: 보내기 전에 안내", (await text("#unsuspend-form .form-error")) === "사유를 입력해 주세요." && (await evaluate("window.lastConfirm")) === null);
  await evaluate(`document.getElementById("unsuspend-form-reason").value = "소명 확인"; document.querySelector("#unsuspend-form button[type=submit]").click()`);
  await waitUntil("!document.getElementById('action-notice').hidden");
  check("정지 해제 → 안내·해제 폼 사라짐·이름표 없음", (await text("#action-notice")) === "정지를 해제했습니다." && !(await evaluate(`Boolean(document.getElementById("unsuspend-form"))`)) && (await text("#user-badges")) === "", await text("#action-notice"));
  check("정지 이력: 해제가 맨 위", (await text("#suspension-list li:first-child")).includes("정지 해제") && (await text("#suspension-list li:first-child")).includes("소명 확인"));
  await evaluate(`document.getElementById("suspend-days").value = "7"; document.getElementById("suspend-form-reason").value = "거래 약속 반복 파기"; document.querySelector("#suspend-form button[type=submit]").click()`);
  await waitUntil("document.getElementById('action-notice').textContent.includes('까지 정지했습니다')");
  check("직접 정지: 확인 창에 기간·사유", (await evaluate("window.lastConfirm")).includes("7일 정지") && (await evaluate("window.lastConfirm")).includes("거래 약속 반복 파기"));
  check("직접 정지 → 정지 이름표", (await text("#user-badges")).includes("까지 정지"));
  check("상세(조치 폼) 가로 넘침 없음", await noHorizontalScroll());
  await screenshot(`admin-tools-user-actions-${W}.png`);
  // 관리자 상세에는 조치가 없다.
  await goto("/static/admin-users.html?status=ADMIN", "document.querySelectorAll('#user-list li').length === 1");
  await evaluate(`document.querySelector("#user-list .admin-card__title").click()`);
  await waitUntil("!document.getElementById('user-detail').hidden");
  check("관리자 상세: 조치 칸 없음", await evaluate(`document.getElementById("user-actions").hidden`));

  // 8) 후기 관리: 숨긴 후기 → 숨김 해제
  // 준비(API): 판매자 정지를 풀고, p1을 구매자에게 판매 완료 → 구매자 후기 → 판매자가 신고 → 관리자가 숨김
  const sellerId = (await api("GET", "/users/me", seed.seller_token)).body.id;
  const buyerId = (await api("GET", "/users/me", seed.buyer_token)).body.id;
  await api("POST", `/admin/users/${sellerId}/unsuspend`, admin, { reason: "후기 확인 준비" });
  await api("PATCH", `/posts/${seed.p1}/status`, seed.seller_token, { status: "SOLD", buyer_id: buyerId });
  const tradeId = (await api("GET", `/conversations/${seed.c1}`, seed.buyer_token)).body.trade.trade_id;
  const reviewId = (await api("POST", `/trades/${tradeId}/reviews`, seed.buyer_token, { rating: "BAD", content: "약속 시간에 늦었어요" })).body.id;
  const r3 = (await api("POST", `/reviews/${reviewId}/reports`, seed.seller_token, { reason: "ABUSE" })).body.id;
  const hid = await api("POST", `/admin/reports/${r3}/resolve`, admin, { action: "HIDE_REVIEW", note: "욕설 의심" });
  check("준비: 후기 숨김", hid.status === 200, JSON.stringify(hid.body));
  await goto("/static/admin-reviews.html", "document.querySelectorAll('#review-list li').length === 1");
  check("후기 관리: 메뉴 현재 화면 '후기', 기본은 숨긴 후기", (await navInfo()).current === "후기" && (await text(".tabs__item[aria-current=page]")) === "숨긴 후기");
  const reviewCard = await text("#review-list li");
  check("후기 카드: 작성자 → 받은 사람, 내용, 숨김 표시", reviewCard.includes("구매자지은 → 판매자민수") && reviewCard.includes("약속 시간에 늦었어요") && reviewCard.includes("숨김"), reviewCard);
  check("후기 관리 가로 넘침 없음", await noHorizontalScroll());
  await screenshot(`admin-tools-reviews-${W}.png`);
  await autoConfirm();
  await evaluate(`window.lastConfirm = null; document.querySelector("#unhide-${reviewId} button[type=submit]").click()`);
  check("사유 없이 숨김 해제: 안내", (await text(`#unhide-${reviewId} .form-error`)) === "사유를 입력해 주세요." && (await evaluate("window.lastConfirm")) === null);
  await evaluate(`document.getElementById("unhide-${reviewId}-reason").value = "욕설 아님"; document.querySelector("#unhide-${reviewId} button[type=submit]").click()`);
  await waitUntil("!document.getElementById('admin-notice').hidden && document.getElementById('result-summary').textContent === '숨긴 후기가 없습니다.'");
  check("숨김 해제 → 안내, 숨긴 후기 목록에서 빠짐", (await text("#admin-notice")).includes("숨김을 해제했습니다"));
  const profileReviews = (await api("GET", `/users/${sellerId}/reviews`, null)).body.items.length;
  check("숨김 해제 → 프로필 후기에 다시 보임", profileReviews === 1, String(profileReviews));
  await goto(`/static/admin-user.html?id=${sellerId}`, "!document.getElementById('user-detail').hidden");
  await evaluate(`[...document.querySelectorAll("#user-counts a")].find((a) => a.textContent.includes("받은 후기")).click()`);
  await waitUntil("location.pathname === '/static/admin-reviews.html' && document.querySelectorAll('#review-list li').length === 1");
  check("상세 '받은 후기' → 그 사용자 후기(전체 탭)", (await text(".tabs__item[aria-current=page]")) === "전체" && (await text("#filter-user")).includes("받은 후기만"));

  // 9) 글 관리: 검색, 미처리 신고 표시, 삭제 창(사유 필수) → 확인 창 → 삭제, 신고 함께 처리
  const p4 = (await api("POST", "/posts", seed.buyer_token, { title: "수상한 교재 판매", book_title: "회로이론", condition: "GOOD", price: 5000 })).body.id;
  const r4 = (await api("POST", `/posts/${p4}/reports`, seed.seller_token, { reason: "FRAUD" })).body.id;
  check("준비: 글 p4와 신고", Boolean(p4 && r4));
  await goto("/static/admin-posts.html", "document.querySelectorAll('#post-list li').length === 4");
  const postNav = await navInfo();
  check("글 관리: 메뉴 6개·현재 화면 '글'", postNav.labels.length === 6 && postNav.current === "글", JSON.stringify(postNav));
  check("글 관리 가로 넘침 없음(메뉴 6개)", await noHorizontalScroll());
  await evaluate(`document.getElementById("search-q").value = "회로"; document.querySelector("#post-search button[type=submit]").click()`);
  await waitUntil("location.search.includes('q=') && document.querySelectorAll('#post-list li').length === 1");
  check("글 검색(교재명)", (await text("#post-list li")).includes("수상한 교재 판매") && (await text("#post-list li")).includes("미처리 신고 1건"), await text("#post-list li"));
  await screenshot(`admin-tools-posts-${W}.png`);
  await evaluate(`document.querySelector("#post-list li .button--danger").click()`);
  await waitUntil("document.querySelector('dialog.admin-dialog')?.open === true");
  await autoConfirm();
  await evaluate(`window.lastConfirm = null; document.querySelector("#admin-dialog-form button[type=submit]").click()`);
  check("삭제 창: 사유 없이 → 안내, 확인 창 없음", (await text("#admin-dialog-form .form-error")) === "사유를 입력해 주세요." && (await evaluate("window.lastConfirm")) === null);
  check("삭제 창 가로 넘침 없음", await noHorizontalScroll());
  await screenshot(`admin-tools-post-dialog-${W}.png`);
  await evaluate(`document.getElementById("admin-dialog-form-reason").value = "사기 의심 글"; document.querySelector("#admin-dialog-form button[type=submit]").click()`);
  await waitUntil("!document.querySelector('dialog.admin-dialog') && !document.getElementById('admin-notice').hidden");
  check("삭제 확인 창: 신고 함께 처리 안내·사유", (await evaluate("window.lastConfirm")).includes("미처리 신고 1건") && (await evaluate("window.lastConfirm")).includes("사기 의심 글"));
  check("삭제 → 안내(신고 1건 함께 처리)", (await text("#admin-notice")).includes("미처리 신고 1건을 함께 처리"), await text("#admin-notice"));
  await waitUntil("document.getElementById('result-summary').textContent === '조건에 맞는 글이 없습니다.'");
  check("삭제한 글은 목록에서 빠짐", (await api("GET", `/posts/${p4}`, null)).status === 404);
  // 취소: 창을 닫으면 아무 일도 없다.
  await goto("/static/admin-posts.html", "document.querySelectorAll('#post-list li').length === 3");
  await evaluate(`document.querySelector("#post-list li .button--danger").click()`);
  await waitUntil("document.querySelector('dialog.admin-dialog')?.open === true");
  await evaluate(`[...document.querySelectorAll("#admin-dialog-form button")].find((b) => b.textContent === "취소").click()`);
  await waitUntil("!document.querySelector('dialog.admin-dialog')");
  check("삭제 창 취소 → 글 그대로", (await evaluate(`document.querySelectorAll('#post-list li').length`)) === 3);

  check("자바스크립트 오류 없음", exceptions.length === 0, exceptions.join(" | "));
} catch (error) {
  results.push(`ERROR  ${error.stack ?? error}`);
} finally {
  browser.close();
  writeFileSync(join(OUT, "admin-tools-check.txt"), results.join("\n") + "\n");
}
