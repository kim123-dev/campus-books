// 비밀번호 재설정 화면: 이메일 + 복구 코드 + 새 비밀번호. 로그인하지 않은 상태에서 쓴다.
// 성공하면 쓴 코드는 사라지므로, 서버가 준 새 코드를 보여주고 저장했다고 확인하면 로그인 화면으로 보낸다.
import { resetPassword } from "../api.js";
import { LOGIN_PAGE, authPageUrl, renderHeader } from "../auth.js";
import { renderRecoveryCode } from "../recovery-code.js";
import { clearFormErrors, showFormErrors } from "../ui.js";

const form = document.getElementById("reset-form");
const errorBox = document.getElementById("reset-error");
const submitButton = form.querySelector('button[type="submit"]');

// 로그인 화면으로 돌아가도 next가 유지되게 한다.
document.getElementById("login-link").href = authPageUrl(LOGIN_PAGE);
renderHeader(document.getElementById("site-header"));

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearFormErrors(form, errorBox);
  const { email, recovery_code: code, new_password: password, new_password_confirm: confirm } = form.elements;

  // 비밀번호 확인은 서버 API에 없는 항목이라 브라우저에서만 검사한다.
  if (password.value !== confirm.value) {
    showFormErrors(form, errorBox, { fieldErrors: { new_password_confirm: "새 비밀번호가 일치하지 않습니다." } });
    confirm.focus();
    return;
  }

  setSubmitting(true);
  try {
    const { recovery_code: newCode } = await resetPassword({
      email: email.value.trim(),
      recovery_code: code.value,
      new_password: password.value,
    });
    showNewCode(newCode);
  } catch (error) {
    // 400(이메일·코드 불일치)과 429(시도 횟수 초과)는 서버 메시지를 공통 영역에, 422는 해당 칸 아래에 보여준다.
    showFormErrors(form, errorBox, error);
    setSubmitting(false);
  }
});

function showNewCode(code) {
  const box = document.getElementById("reset-code");
  form.hidden = true;
  document.getElementById("reset-switch").hidden = true;
  document.querySelector(".form-notice").textContent = "비밀번호를 바꿨습니다. 방금 쓴 복구 코드는 이제 쓸 수 없어요. 아래 새 코드를 저장해 주세요.";
  const warnBeforeLeave = (event) => event.preventDefault();
  window.addEventListener("beforeunload", warnBeforeLeave);
  renderRecoveryCode(box, code, {
    continueText: "로그인하러 가기",
    onContinue: () => {
      window.removeEventListener("beforeunload", warnBeforeLeave);
      window.location.assign(authPageUrl(LOGIN_PAGE, { reset: "1" }));
    },
  });
  box.hidden = false;
}

function setSubmitting(isSubmitting) {
  submitButton.disabled = isSubmitting;
  submitButton.textContent = isSubmitting ? "바꾸는 중…" : "비밀번호 바꾸기";
}
