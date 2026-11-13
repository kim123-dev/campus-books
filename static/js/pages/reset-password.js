// 비밀번호 재설정 화면 (로그인하지 않은 상태)
// 1단계 이메일 → 그 계정의 질문, 2단계 답 확인(맞으면 10분짜리 확인증), 3단계 새 비밀번호.
// 가입하지 않은 이메일에도 서버가 그럴듯한 질문과 같은 실패 응답을 주므로, 화면도 계정이 있는지 따로 알려주지 않는다.
import { getResetQuestion, resetPassword, verifyResetAnswer } from "../api.js";
import { LOGIN_PAGE, authPageUrl, renderHeader } from "../auth.js";
import { clearFormErrors, showFormErrors } from "../ui.js";

const questionForm = document.getElementById("question-form");
const questionError = document.getElementById("question-error");
const verifyForm = document.getElementById("verify-form");
const verifyError = document.getElementById("verify-error");
const verifyButton = document.getElementById("verify-button");
const verifyOk = document.getElementById("verify-ok");
const answerInput = document.getElementById("answer");
const resetForm = document.getElementById("reset-form");
const resetError = document.getElementById("reset-error");
let email = "";
// 답이 맞았을 때 서버가 준 일회용 확인증. 화면 안에만 두고 저장하지 않는다.
let resetToken = null;

// 로그인 화면으로 돌아가도 next가 유지되게 한다.
document.getElementById("login-link").href = authPageUrl(LOGIN_PAGE);
renderHeader(document.getElementById("site-header"));

// ---------- 1단계: 이메일 → 질문 ----------

questionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearFormErrors(questionForm, questionError);
  const submit = questionForm.querySelector("[type=submit]");
  submit.disabled = true;
  try {
    // 서버도 소문자로 맞춘다. 2단계에 보여줄 때도 같은 모양으로 보여준다.
    const value = questionForm.elements.email.value.trim().toLowerCase();
    const { question } = await getResetQuestion(value);
    email = value;
    showVerifyStep(question);
  } catch (error) {
    // 422(이메일 형식)는 칸 아래에, 429(요청 횟수 초과)는 공통 영역에 보여준다.
    showFormErrors(questionForm, questionError, error);
  } finally {
    submit.disabled = false;
  }
});

function showVerifyStep(question) {
  document.getElementById("reset-email").textContent = email;
  document.getElementById("reset-question").textContent = question;
  questionForm.hidden = true;
  verifyForm.hidden = false;
  answerInput.focus();
}

// 이메일을 잘못 넣었을 때 처음(1단계)으로 돌아간다. 받은 확인증도 버린다.
document.getElementById("change-email").addEventListener("click", () => {
  resetToken = null;
  verifyForm.reset();
  resetForm.reset();
  clearFormErrors(verifyForm, verifyError);
  clearFormErrors(resetForm, resetError);
  setVerified(false);
  verifyForm.hidden = true;
  questionForm.hidden = false;
  questionForm.elements.email.focus();
});

// ---------- 2단계: 답 확인 ----------

verifyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (resetToken !== null) return;
  clearFormErrors(verifyForm, verifyError);
  if (answerInput.value.trim() === "") {
    showFormErrors(verifyForm, verifyError, { fieldErrors: { answer: "답을 입력해 주세요." } });
    return;
  }

  verifyButton.disabled = true;
  verifyButton.textContent = "확인 중…";
  try {
    const { reset_token: token } = await verifyResetAnswer({ email, answer: answerInput.value });
    resetToken = token;
    setVerified(true);
    resetForm.elements.new_password.focus();
  } catch (error) {
    // 틀린 답(400, 남은 시도 횟수 포함)과 잠김(429, 남은 시간)은 답 칸 바로 아래에 보여준다.
    const message = error.status === 400 || error.status === 429 ? error.message : null;
    if (message) showFormErrors(verifyForm, verifyError, { fieldErrors: { answer: message } });
    else showFormErrors(verifyForm, verifyError, error);
    verifyButton.disabled = false;
    verifyButton.textContent = "인증 확인";
  }
});

// 확인되면 답 칸을 잠그고 새 비밀번호 칸을 보여준다. 틀린 동안에는 새 비밀번호 칸이 보이지 않는다.
function setVerified(verified) {
  answerInput.readOnly = verified;
  verifyOk.hidden = !verified;
  verifyButton.hidden = verified;
  verifyButton.disabled = false;
  verifyButton.textContent = "인증 확인";
  resetForm.hidden = !verified;
}

// ---------- 3단계: 새 비밀번호 ----------

resetForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearFormErrors(resetForm, resetError);
  const { new_password: password, new_password_confirm: confirm } = resetForm.elements;

  // 비밀번호 확인은 서버 API에 없는 항목이라 브라우저에서만 검사한다.
  if (password.value !== confirm.value) {
    showFormErrors(resetForm, resetError, { fieldErrors: { new_password_confirm: "새 비밀번호가 일치하지 않습니다." } });
    confirm.focus();
    return;
  }

  const submit = resetForm.querySelector("[type=submit]");
  submit.disabled = true;
  submit.textContent = "바꾸는 중…";
  try {
    await resetPassword({ reset_token: resetToken, new_password: password.value });
    window.location.assign(authPageUrl(LOGIN_PAGE, { reset: "1" }));
  } catch (error) {
    // 확인증이 만료(10분)됐으면(400) 공통 영역에 안내하고 답을 다시 확인하게 한다. 422는 해당 칸 아래에.
    if (error.status === 400) {
      resetToken = null;
      setVerified(false);
      answerInput.focus();
    }
    showFormErrors(resetForm.hidden ? verifyForm : resetForm, resetForm.hidden ? verifyError : resetError, error);
    submit.disabled = false;
    submit.textContent = "비밀번호 바꾸기";
  }
});
