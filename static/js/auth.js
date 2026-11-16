// 로그인 상태 처리: 공통 헤더, 로그인 후 돌아갈 주소, 로그아웃.
// 토큰 보관 자체는 token.js가 맡는다.
import { dismissResetNotice, getAlertUnreadCount, getMe, getUnreadCount } from "./api.js";
import { t } from "./i18n.js";
import { languageMenu } from "./lang-picker.js";
import { notificationBell } from "./notification-panel.js";
import { clearToken, getToken } from "./token.js";
import { el, formatMonthDayTime, icon } from "./ui.js";

export const LOGIN_PAGE = "/static/login.html";
export const SIGNUP_PAGE = "/static/signup.html";
export const RESET_PASSWORD_PAGE = "/static/reset-password.html";
// 로그인·가입·재설정 화면끼리는 next를 그대로 넘기고, 이 화면들로는 돌아가지 않는다.
const AUTH_PAGES = [LOGIN_PAGE, SIGNUP_PAGE, RESET_PASSWORD_PAGE];
const HOME_PAGE = "/static/index.html";
const LOGO_IMAGE = "/static/img/logo.png";
const POST_FORM_PAGE = "/static/post-form.html";
// 내 글·찜 목록은 내 정보 화면의 탭이다. 예전 주소(my-posts.html, wishlist.html)는 이 화면으로 넘겨준다.
const ME_PAGE = "/static/me.html";
const LEGACY_ME_PAGES = ["/static/my-posts.html", "/static/wishlist.html"];
const CONVERSATIONS_PAGE = "/static/conversations.html";
// 헤더의 "관리" 링크는 대시보드로 간다. (신고 화면 admin.html은 관리 메뉴에서)
const ADMIN_PAGE = "/static/admin-dashboard.html";
// 관리 화면(admin*.html)은 모두 하단 탭 바의 "내 정보" 탭 아래로 본다.
const ADMIN_PAGE_PREFIX = "/static/admin";
const BLOCKS_PAGE = "/static/blocks.html";
const ALERTS_PAGE = "/static/alerts.html";
const BOOK_ALERTS_PAGE = "/static/book-alerts.html";
const MAX_BADGE_COUNT = 99;

// ---------- 돌아갈 주소 (next) ----------

/**
 * next 값이 우리 사이트의 화면 주소일 때만 돌려주고, 아니면 목록 화면을 돌려준다.
 * 로그인 링크에 "//evil.com" 같은 주소를 넣어 피싱 사이트로 보내는 공격(open redirect)을 막기 위해서다.
 */
export function safeNext(raw) {
  if (typeof raw !== "string" || !raw.startsWith("/static/") || raw.includes("\\")) return HOME_PAGE;
  let url;
  try {
    url = new URL(raw, window.location.origin);
  } catch {
    return HOME_PAGE;
  }
  if (url.origin !== window.location.origin || !url.pathname.startsWith("/static/")) return HOME_PAGE;
  // 로그인·가입 화면으로 돌아가면 다시 로그인 화면을 보게 되므로 목록으로 보낸다.
  if (AUTH_PAGES.includes(url.pathname)) return HOME_PAGE;
  return url.pathname + url.search + url.hash;
}

/** 현재 주소의 ?next= 값을 검사해서 돌려준다. */
export function getNextFromUrl() {
  return safeNext(new URLSearchParams(window.location.search).get("next"));
}

/** 로그인·가입 화면 주소. 지금 보던 화면을 next로 붙여 끝나면 돌아오게 한다. */
export function authPageUrl(page, extraParams = {}) {
  const params = new URLSearchParams({ ...extraParams, next: currentNext() });
  return `${page}?${params}`;
}

// 로그인·가입·재설정 화면끼리 오갈 때는 그 화면이 받은 next를 그대로 넘긴다.
function currentNext() {
  const { pathname, search, hash } = window.location;
  if (AUTH_PAGES.includes(pathname)) return getNextFromUrl();
  return pathname + search + hash;
}

/**
 * 로그인 화면으로 보낸다. 지금 화면을 next로 붙여 로그인 후 돌아오게 한다.
 * replace를 쓰는 이유: 로그인 화면에서 뒤로 가기를 눌렀을 때 로그인이 필요한 화면으로 돌아가
 * 다시 로그인 화면으로 튕겨 나오는 일을 막기 위해서다.
 */
export function redirectToLogin() {
  window.location.replace(authPageUrl(LOGIN_PAGE));
}

// ---------- 공통 헤더 ----------

/**
 * 모든 화면 위쪽의 공통 헤더를 그린다.
 * 토큰이 있으면 /users/me로 확인해 "닉네임 · 로그아웃"을, 아니면 "로그인 · 회원가입"을 보여준다.
 * @returns {Promise<object|null>} 로그인한 사용자 정보 (다른 화면에서 "내 글인지" 판단할 때 쓰도록)
 */
export async function renderHeader(container) {
  const nav = el("nav", { className: "site-nav", attrs: { "aria-label": t("nav.main_aria") } });
  // 알림 종은 메뉴(nav) 밖에 둔다. 모바일에서는 로그인 메뉴가 숨겨져도(하단 탭 바가 대신) 종은 보여야 하기 때문이다.
  const bellSlot = el("span", { className: "site-header__bell" });
  container.replaceChildren(
    el(
      "div",
      { className: "container site-header__inner" },
      el(
        "a",
        { className: "site-logo", href: HOME_PAGE },
        // 링크 이름은 옆의 글자가 되므로 그림은 꾸밈으로 둔다(alt="").
        // 파일은 128px이라 고해상도 화면에서도 선명하고, width·height로 자리를 먼저 잡아 헤더가 흔들리지 않는다.
        el("img", { className: "site-logo__mark", src: LOGO_IMAGE, alt: "", width: 128, height: 128, decoding: "async" }),
        "Campus Books",
      ),
      // 언어 버튼은 로그인 여부와 관계없이 모든 화면에 둔다. (기능 플래그가 꺼져 있으면 null이라 그리지 않는다)
      el("div", { className: "site-header__right" }, nav, bellSlot, languageMenu()),
    ),
  );
  // 모바일 하단 탭 바는 로그인 확인을 기다리지 않고 바로 그려, 화면이 뜬 뒤 아래가 밀리지 않게 한다.
  renderTabBar();

  // 토큰이 없으면 서버에 물어볼 필요가 없다.
  if (!getToken()) {
    nav.replaceChildren(...loggedOutLinks());
    return null;
  }

  try {
    const me = await getMe();
    nav.replaceChildren(...loggedInItems(me));
    bellSlot.replaceChildren(
      notificationBell({
        button: alertBell(),
        // 판에서 찾는 교재 알림 하나를 읽으면 종 배지에서 하나를 뺀다. (다음 화면의 헤더가 서버 숫자로 다시 맞춘다)
        onAlertRead: () => {
          unreadCounts.alerts = Math.max(0, unreadCounts.alerts - 1);
          renderBellBadge();
        },
      }),
    );
    // 로그인 메뉴는 모바일에서 하단 탭 바가 대신한다. (로그인·회원가입 링크는 모바일에서도 헤더에 남긴다)
    nav.classList.add("site-nav--member");
    // 정지 중이면 모든 화면 위쪽에 언제까지인지 알려준다. 쓰기 버튼을 눌렀다가 403을 받고 나서야 알게 되지 않도록.
    const suspension = suspensionText(me);
    if (suspension !== null) {
      container.append(
        el("p", { className: "site-notice", attrs: { role: "status" } }, el("span", { className: "container", text: suspension })),
      );
    }
    if (me.password_reset_notice) container.append(resetNotice(me.password_reset_notice));
    // 배지는 헤더를 그린 뒤 따로 채운다. 기다리지 않아서, 배지 요청이 늦어도 화면이 먼저 뜬다.
    refreshUnreadBadge();
    refreshAlertBadge();
    return me;
  } catch {
    // 401이면 api.js가 이미 토큰을 지웠다.
    // 서버 연결 실패(0)는 일시적일 수 있으므로 토큰은 남겨 두고 로그인 링크만 보여준다.
    nav.replaceChildren(...loggedOutLinks());
    return null;
  }
}

// 비밀번호가 재설정된 뒤 처음 로그인했을 때 한 번 보여준다. 본인이 하지 않은 재설정을 알아챌 수 있게 하기 위해서다.
// "확인"을 누르면 서버에 기록하고 다시 보여주지 않는다.
function resetNotice({ reset_at: resetAt, method }) {
  const how = method === "SERVER" ? t("notice.reset_by_server") : t("notice.reset_by_question");
  const box = el(
    "p",
    { className: "site-notice site-notice--action", attrs: { role: "status" } },
    el(
      "span",
      { className: "container" },
      el("span", {
        text: t("notice.reset", { date: formatMonthDayTime(resetAt), how }),
      }),
    ),
  );
  const button = el("button", { type: "button", className: "button button--small", text: t("common.ok") });
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await dismissResetNotice();
      box.remove();
    } catch {
      // 실패하면 다음 화면에서 다시 보인다. 버튼만 다시 누를 수 있게 한다.
      button.disabled = false;
    }
  });
  box.firstChild.append(button);
  return box;
}

function loggedOutLinks() {
  return [
    el("a", { href: authPageUrl(LOGIN_PAGE), text: t("term.login") }),
    el("a", { href: authPageUrl(SIGNUP_PAGE), text: t("term.signup") }),
  ];
}

function loggedInItems(me) {
  const logoutButton = el("button", { type: "button", className: "link-button", text: t("term.logout") });
  logoutButton.addEventListener("click", logout);
  return [
    el("a", { href: POST_FORM_PAGE, text: t("term.sell") }),
    el(
      "a",
      { href: CONVERSATIONS_PAGE, className: "site-nav__messages", attrs: { id: "nav-messages" } },
      t("term.messages"),
      el("span", { className: "nav-badge", attrs: { id: "nav-unread", "aria-hidden": "true" }, hidden: true }),
    ),
    // 관리자에게만 보인다. 링크를 숨기는 것은 편의일 뿐이고, 실제 권한은 서버가 /admin API마다 확인한다.
    // 닉네임은 따로 보여주지 않고 "내 정보" 링크 이름에 담는다. (화면 낭독기: "내 정보, 책벌레님")
    el("a", { href: ME_PAGE, className: "site-nav__me", text: t("term.me"), attrs: { "aria-label": t("nav.me_aria", { nickname: me.nickname }) } }),
    ...(me.role === "ADMIN" ? [el("a", { href: ADMIN_PAGE, text: t("term.admin") })] : []),
    logoutButton,
  ];
}

// 알림 종. PC와 모바일 모두 헤더 오른쪽에 보인다. (하단 탭 바에 넣지 않고 헤더에 둔다)
// 누르면 종 아래에 작은 알림 판이 열린다(notification-panel.js). 판 맨 아래 "전체 보기"가 알림 화면으로 간다.
// 배지는 안 읽은 쪽지 + 안 읽은 찾는 교재 알림의 합이다.
function alertBell() {
  return el(
    "button",
    {
      type: "button",
      className: "site-bell",
      attrs: { id: "nav-alerts", "aria-label": t("term.notifications") },
    },
    icon("bell"),
    el("span", { className: "nav-badge site-bell__badge", attrs: { id: "nav-alerts-unread", "aria-hidden": "true" }, hidden: true }),
  );
}

// ---------- 모바일 하단 탭 바 ----------

// also: 이 탭에서 들어가는 화면. 그 화면에서도 이 탭을 현재 탭으로 표시한다. alsoPrefix는 주소 앞부분이 같은 화면들.
// 찜은 내 정보 화면의 탭으로 옮겨 4칸으로 줄였다. 칸이 넓어져 누르기 쉽다.
// labelKey: 탭 이름의 사전 키 (헤더 메뉴와 같은 용어 term.*을 쓴다)
const TABS = [
  { href: HOME_PAGE, labelKey: "term.home", icon: "home" },
  { href: POST_FORM_PAGE, labelKey: "term.sell", icon: "plus", modifier: "write" },
  { href: CONVERSATIONS_PAGE, labelKey: "term.messages", icon: "chat", id: "tab-messages", badgeId: "tab-unread" },
  { href: ME_PAGE, labelKey: "term.me", icon: "user", also: [BLOCKS_PAGE, ALERTS_PAGE, BOOK_ALERTS_PAGE, ...LEGACY_ME_PAGES], alsoPrefix: ADMIN_PAGE_PREFIX },
];

/**
 * 모바일(768px 미만) 하단 고정 탭 바. PC에서는 CSS가 숨기고 헤더 메뉴를 쓴다.
 * 상세·대화·글쓰기·로그인·회원가입은 화면 아래를 따로 쓰므로 <body data-tab-bar="off">로 끈다.
 * 로그인이 필요한 탭은 각 화면이 로그인 화면으로 보냈다가 돌아오게 한다. (헤더 메뉴와 같은 동작)
 */
function renderTabBar() {
  if (document.body.dataset.tabBar === "off" || document.querySelector(".tab-bar")) return;
  const here = window.location.pathname;
  const items = TABS.map((tab) => {
    const current =
      here === tab.href || (tab.also ?? []).includes(here) || (tab.alsoPrefix !== undefined && here.startsWith(tab.alsoPrefix));
    const attrs = {};
    if (tab.id) attrs.id = tab.id;
    if (current) attrs["aria-current"] = "page";
    return el(
      "a",
      { className: `tab-bar__item${tab.modifier ? ` tab-bar__item--${tab.modifier}` : ""}`, href: tab.href, attrs },
      el("span", { className: "tab-bar__icon" }, icon(tab.icon)),
      el("span", { className: "tab-bar__label", text: t(tab.labelKey) }),
      tab.badgeId
        ? el("span", { className: "nav-badge tab-bar__badge", attrs: { id: tab.badgeId, "aria-hidden": "true" }, hidden: true })
        : null,
    );
  });
  document.body.append(el("nav", { className: "tab-bar", attrs: { "aria-label": t("nav.tab_aria") } }, ...items));
  // 탭 바 높이만큼 화면 아래 여백을 둔다. (CSS가 모바일에서만 적용)
  document.body.classList.add("has-tab-bar");
}

/** 정지 중이면 안내 문구, 아니면 null. 서버는 기간이 지난 정지를 null로 보내므로 날짜만 확인한다. */
export function suspensionText(me) {
  if (!me?.suspended_until) return null;
  return t("notice.suspended", { date: formatMonthDayTime(me.suspended_until) });
}

// ---------- 안 읽은 수 배지 ----------
// 종 배지 = 안 읽은 쪽지 + 안 읽은 찾는 교재 알림. 두 숫자는 이미 있는 API(쪽지·알림 안 읽은 수)로 따로 받아
// 여기에 두고 합을 그린다. 헤더는 화면을 열 때 두 API를 한 번씩만 부르고, 읽은 뒤에는 각 화면이 해당 숫자만 다시 받는다.
const unreadCounts = { messages: 0, alerts: 0 };
// 가장 최근의 "안 읽은 쪽지 수" 요청. 알림 화면이 같은 숫자를 다시 묻지 않고 이것을 기다린다.
let messageCountRequest = null;

function badgeText(count) {
  return count > MAX_BADGE_COUNT ? `${MAX_BADGE_COUNT}+` : String(count);
}

function renderBellBadge() {
  const link = document.getElementById("nav-alerts");
  const badge = document.getElementById("nav-alerts-unread");
  if (!link || !badge) return;
  const count = unreadCounts.messages + unreadCounts.alerts;
  badge.textContent = badgeText(count);
  badge.hidden = count === 0;
  // 배지 숫자는 화면 낭독기에서 숨기고, 링크 이름에 뜻을 담아 읽어 준다.
  link.setAttribute("aria-label", count > 0 ? t("nav.notifications_unread_aria", { count }) : t("term.notifications"));
}

/**
 * 안 읽은 찾는 교재 알림 수를 다시 받아 종 배지를 고친다. 알림 화면이 모두 읽음 처리한 뒤에도 부른다.
 * 배지는 보조 정보라 실패해도 화면에 에러를 띄우지 않고 그 숫자만 0으로 본다.
 */
export async function refreshAlertBadge() {
  if (!document.getElementById("nav-alerts")) return;
  try {
    ({ unread_count: unreadCounts.alerts } = await getAlertUnreadCount());
  } catch {
    unreadCounts.alerts = 0;
  }
  renderBellBadge();
}

/** 안 읽은 쪽지 수. 헤더가 이미 물어본 것이 있으면 그 결과를 쓴다. 실패하거나 로그인 전이면 null. */
export function unreadMessageCount() {
  return messageCountRequest ?? refreshUnreadBadge();
}

/**
 * 헤더·하단 탭 바의 "쪽지" 배지와 종 배지를 다시 채운다. 대화 화면이 메시지를 읽은 뒤에도 부른다.
 * 배지는 보조 정보라 실패해도 화면에 에러를 띄우지 않고 배지만 숨긴다. 받은 숫자(실패면 null)를 돌려준다.
 */
export async function refreshUnreadBadge() {
  // 헤더(PC)와 하단 탭 바(모바일)의 "쪽지"에 같은 숫자를 넣는다.
  const pairs = [
    ["nav-messages", "nav-unread"],
    ["tab-messages", "tab-unread"],
  ]
    .map(([linkId, badgeId]) => [document.getElementById(linkId), document.getElementById(badgeId)])
    .filter(([link, badge]) => link && badge);
  // 로그인하지 않았으면 헤더에 쪽지 링크가 없다. 탭 바만 있어도 숫자를 물어보지 않는다.
  if (!document.getElementById("nav-messages") || pairs.length === 0) return null;

  const request = getUnreadCount().then(
    ({ unread_count: n }) => n,
    () => null,
  );
  messageCountRequest = request;
  const result = await request;
  // 그사이 더 새 요청이 있었으면 그쪽이 그린다.
  if (request !== messageCountRequest) return result;
  const count = result ?? 0;
  for (const [link, badge] of pairs) {
    badge.textContent = badgeText(count);
    badge.hidden = count === 0;
    // 배지 숫자는 화면 낭독기에서 숨기고, 링크 이름에 뜻을 담아 읽어 준다.
    link.setAttribute("aria-label", count > 0 ? t("nav.messages_unread_aria", { count }) : t("term.messages"));
  }
  unreadCounts.messages = count;
  renderBellBadge();
  return result;
}

/**
 * 로그아웃. 서버에는 로그아웃 API가 없으므로(JWT는 서버가 상태를 저장하지 않음) 토큰만 지운다.
 * 현재 화면을 다시 불러와 로그아웃 상태로 그리게 한다.
 */
export function logout() {
  clearToken();
  window.location.reload();
}
