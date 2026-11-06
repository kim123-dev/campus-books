// 로그인 화면: 로그인에 성공하면 토큰을 저장하고 원래 보던 화면(next)으로 돌아간다.
import { getMe, login } from "../api.js";
import { SIGNUP_PAGE, authPageUrl, getNextFromUrl, renderHeader } from "../auth.js";
import { getToken, setToken } from "../token.js";
import { clearFormErrors, showFormErrors } from "../ui.js";

const form = document.getElementById("login-form");
const errorBox = document.getElementById("login-error");
const notice = document.getElementById("login-notice");
const submitButton = form.querySelector('button[type="submit"]');
const next = getNextFromUrl();

// 가입 화면으로 갔다가 돌아와도 next가 유지되게 한다.
document.getElementById("signup-link").href = authPageUrl(SIGNUP_PAGE);

// 가입 직후에는 안내를 보여준다. 이메일은 주소에 개인정보가 남지 않도록 넘겨받지 않는다.
if (new URLSearchParams(window.location.search).get("joined") === "1") {
  notice.textContent = "가입이 완료되었습니다. 로그인해 주세요.";
  notice.hidden = false;
}

redirectIfLoggedIn();
renderHeader(document.getElementById("site-header"));

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearFormErrors(form, errorBox);
  setSubmitting(true);

  try {
    const { access_token } = await login(form.elements.username.value.trim(), form.elements.password.value);
    setToken(access_token);
    // replace를 써서, 뒤로 가기를 눌렀을 때 로그인 화면이 다시 나오지 않게 한다.
    window.location.replace(next);
  } catch (error) {
    // 401은 서버 메시지를 공통 영역에, 422는 해당 칸 아래에 보여준다.
    showFormErrors(form, errorBox, error);
    // 다시 입력하기 쉽게 비밀번호만 비운다.
    if (error.status === 401) {
      form.elements.password.value = "";
      form.elements.password.focus();
    }
    setSubmitting(false);
  }
});

// 이미 로그인한 상태로 들어오면 로그인 화면을 보여줄 필요가 없다.
// 토큰이 있어도 만료되었을 수 있으므로 서버에 확인한 뒤에만 이동한다.
async function redirectIfLoggedIn() {
  if (!getToken()) return;
  try {
    await getMe();
    window.location.replace(next);
  } catch {
    // 401이면 api.js가 토큰을 지웠으므로 로그인 화면을 그대로 쓴다.
  }
}

function setSubmitting(isSubmitting) {
  submitButton.disabled = isSubmitting;
  submitButton.textContent = isSubmitting ? "로그인 중…" : "로그인";
}
