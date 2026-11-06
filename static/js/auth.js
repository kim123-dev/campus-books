// 로그인 토큰 보관과 공통 헤더 그리기.
// 토큰은 localStorage에 둔다. 새 탭과 새로고침에서도 로그인이 유지되기 때문이다.
// 대신 XSS에 노출될 수 있으므로, 화면에 값을 넣을 때는 항상 textContent만 쓴다. (ui.js 참고)
import { el } from "./ui.js";

const TOKEN_KEY = "campus-books.token";

// 사생활 보호 모드 등에서 localStorage 접근이 막혀도 화면이 멈추지 않게 try로 감싼다.
export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // 저장에 실패하면 이번 페이지에서만 로그인되지 않은 상태로 동작한다.
  }
}

export function clearToken() {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // 지울 수 없는 환경이면 지울 토큰도 없다.
  }
}

/** 모든 화면 위쪽의 공통 헤더. 로그인 상태 표시는 7-2단계에서 추가한다. */
export function renderHeader(container) {
  const nav = el(
    "nav",
    { className: "site-nav", attrs: { "aria-label": "주요 메뉴" } },
    el("a", { href: "/static/login.html", text: "로그인" }),
    el("a", { href: "/static/signup.html", text: "회원가입" }),
  );
  container.replaceChildren(
    el(
      "div",
      { className: "container site-header__inner" },
      el("a", { className: "site-logo", href: "/static/index.html", text: "Campus Books" }),
      nav,
    ),
  );
}
