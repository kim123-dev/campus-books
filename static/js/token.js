// 로그인 토큰 보관만 맡는다.
// api.js(토큰을 헤더에 넣음)와 auth.js(헤더에 로그인 상태 표시, getMe 호출)가 함께 쓰므로,
// 두 파일이 서로를 불러오는 순환 참조를 피하려고 따로 떼어 두었다.
// 토큰은 localStorage에 둔다. 새 탭과 새로고침에서도 로그인이 유지되기 때문이다.
// 대신 XSS에 노출될 수 있으므로, 화면에 값을 넣을 때는 항상 textContent만 쓴다. (ui.js 참고)

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

/**
 * 다른 탭에서 로그인·로그아웃해 토큰이 바뀌면 callback을 부른다.
 * 토큰은 탭끼리 공유되므로, 열려 있던 화면이 모르는 사이에 다른 계정의 토큰으로 요청하게 된다.
 * (storage 이벤트는 값을 바꾼 탭이 아닌 다른 탭에서만 온다)
 */
export function onTokenChangedInOtherTab(callback) {
  window.addEventListener("storage", (event) => {
    // key가 null이면 다른 탭이 localStorage 전체를 비웠다.
    if (event.key === TOKEN_KEY || event.key === null) callback();
  });
}

export function clearToken() {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // 지울 수 없는 환경이면 지울 토큰도 없다.
  }
}
