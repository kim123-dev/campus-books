// 회원가입 화면: 이메일·비밀번호·닉네임과 본인 확인 질문(비밀번호를 잊었을 때 쓴다)을 받는다.
// 가입하면 로그인 화면으로 보낸다. (원래 보던 화면 next는 그대로 넘긴다)
import { getMe, signup } from "../api.js";
import { LOGIN_PAGE, authPageUrl, getNextFromUrl, renderHeader } from "../auth.js";
import { renderSecurityQuestionFields } from "../security-question.js";
import { getToken } from "../token.js";
import { clearFormErrors, showFormErrors } from "../ui.js";

const form = document.getElementById("signup-form");
const errorBox = document.getElementById("signup-error");
const submitButton = form.querySelector('button[type="submit"]');
const question = renderSecurityQuestionFields(document.getElementById("signup-question"), { idPrefix: "signup" });

// 로그인 화면으로 갔다가 돌아와도 next가 유지되게 한다.
document.getElementById("login-link").href = authPageUrl(LOGIN_PAGE);

redirectIfLoggedIn();
renderHeader(document.getElementById("site-header"));

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearFormErrors(form, errorBox);

  const { email, password, password_confirm: passwordConfirm, nickname } = form.elements;

  // 비밀번호 확인은 서버 API에 없는 항목이라 브라우저에서만 검사한다.
  // (그 밖의 입력 규칙은 서버가 검사하고, 그 메시지를 칸 아래에 보여준다)
  if (password.value !== passwordConfirm.value) {
    showFormErrors(form, errorBox, { fieldErrors: { password_confirm: "비밀번호가 일치하지 않습니다." } });
    passwordConfirm.focus();
    return;
  }
  const questionErrors = question.check();
  if (questionErrors !== null) {
    showFormErrors(form, errorBox, { fieldErrors: questionErrors });
    return;
  }

  setSubmitting(true);
  try {
    await signup({
      email: email.value.trim(),
      password: password.value,
      nickname: nickname.value,
      security_question: question.value(),
    });
    window.location.assign(authPageUrl(LOGIN_PAGE, { joined: "1" }));
  } catch (error) {
    // 409(이메일·닉네임 중복)는 서버 메시지를 공통 영역에, 422는 해당 칸 아래에 보여준다.
    showFormErrors(form, errorBox, error);
    setSubmitting(false);
  }
});

// 이미 로그인한 상태라면 가입 화면 대신 원래 화면으로 보낸다.
async function redirectIfLoggedIn() {
  if (!getToken()) return;
  try {
    await getMe();
    window.location.replace(getNextFromUrl());
  } catch {
    // 토큰이 만료되었으면(401) 가입 화면을 그대로 쓴다.
  }
}

function setSubmitting(isSubmitting) {
  submitButton.disabled = isSubmitting;
  submitButton.textContent = isSubmitting ? "가입 중…" : "가입하기";
}
