// 로그인 상태 처리: 공통 헤더, 로그인 후 돌아갈 주소, 로그아웃.
// 토큰 보관 자체는 token.js가 맡는다.
import { getMe } from "./api.js";
import { clearToken, getToken } from "./token.js";
import { el } from "./ui.js";

export const LOGIN_PAGE = "/static/login.html";
export const SIGNUP_PAGE = "/static/signup.html";
const HOME_PAGE = "/static/index.html";

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
  if (url.pathname === LOGIN_PAGE || url.pathname === SIGNUP_PAGE) return HOME_PAGE;
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

// 로그인·가입 화면끼리 오갈 때는 그 화면이 받은 next를 그대로 넘긴다.
function currentNext() {
  const { pathname, search, hash } = window.location;
  if (pathname === LOGIN_PAGE || pathname === SIGNUP_PAGE) return getNextFromUrl();
  return pathname + search + hash;
}

// ---------- 공통 헤더 ----------

/**
 * 모든 화면 위쪽의 공통 헤더를 그린다.
 * 토큰이 있으면 /users/me로 확인해 "닉네임 · 로그아웃"을, 아니면 "로그인 · 회원가입"을 보여준다.
 * @returns {Promise<object|null>} 로그인한 사용자 정보 (다른 화면에서 "내 글인지" 판단할 때 쓰도록)
 */
export async function renderHeader(container) {
  const nav = el("nav", { className: "site-nav", attrs: { "aria-label": "주요 메뉴" } });
  container.replaceChildren(
    el(
      "div",
      { className: "container site-header__inner" },
      el("a", { className: "site-logo", href: HOME_PAGE, text: "Campus Books" }),
      nav,
    ),
  );

  // 토큰이 없으면 서버에 물어볼 필요가 없다.
  if (!getToken()) {
    nav.replaceChildren(...loggedOutLinks());
    return null;
  }

  try {
    const me = await getMe();
    nav.replaceChildren(...loggedInItems(me));
    return me;
  } catch {
    // 401이면 api.js가 이미 토큰을 지웠다.
    // 서버 연결 실패(0)는 일시적일 수 있으므로 토큰은 남겨 두고 로그인 링크만 보여준다.
    nav.replaceChildren(...loggedOutLinks());
    return null;
  }
}

function loggedOutLinks() {
  return [
    el("a", { href: authPageUrl(LOGIN_PAGE), text: "로그인" }),
    el("a", { href: authPageUrl(SIGNUP_PAGE), text: "회원가입" }),
  ];
}

// "글쓰기", "내 글" 링크는 해당 화면을 만드는 7-4, 7-5단계에서 추가한다.
function loggedInItems(me) {
  const logoutButton = el("button", { type: "button", className: "link-button", text: "로그아웃" });
  logoutButton.addEventListener("click", logout);
  return [el("span", { className: "site-nav__user", text: `${me.nickname}님` }), logoutButton];
}

/**
 * 로그아웃. 서버에는 로그아웃 API가 없으므로(JWT는 서버가 상태를 저장하지 않음) 토큰만 지운다.
 * 현재 화면을 다시 불러와 로그아웃 상태로 그리게 한다.
 */
export function logout() {
  clearToken();
  window.location.reload();
}
