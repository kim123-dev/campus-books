// 비밀번호 재설정 화면 (로그인하지 않은 상태): 1단계 이메일 → 그 계정의 질문, 2단계 답 + 새 비밀번호.
// 가입하지 않은 이메일에도 서버가 그럴듯한 질문을 주므로, 화면도 계정이 있는지 따로 알려주지 않는다.
import { getResetQuestion, resetPassword } from "../api.js";
import { LOGIN_PAGE, authPageUrl, renderHeader } from "../auth.js";
import { clearFormErrors, showFormErrors } from "../ui.js";

const questionForm = document.getElementById("question-form");
const questionError = document.getElementById("question-error");
const resetForm = document.getElementById("reset-form");
const resetError = document.getElementById("reset-error");
let email = "";

// 로그인 화면으로 돌아가도 next가 유지되게 한다.
document.getElementById("login-link").href = authPageUrl(LOGIN_PAGE);
renderHeader(document.getElementById("site-header"));

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
    showStep2(question);
  } catch (error) {
    // 422(이메일 형식)는 칸 아래에, 429(요청 횟수 초과)는 공통 영역에 보여준다.
    showFormErrors(questionForm, questionError, error);
  } finally {
    submit.disabled = false;
  }
});

function showStep2(question) {
  document.getElementById("reset-email").textContent = email;
  document.getElementById("reset-question").textContent = question;
  questionForm.hidden = true;
  resetForm.hidden = false;
  resetForm.elements.answer.focus();
}

// 이메일을 잘못 넣었을 때 1단계로 돌아간다.
document.getElementById("change-email").addEventListener("click", () => {
  resetForm.reset();
  clearFormErrors(resetForm, resetError);
  resetForm.hidden = true;
  questionForm.hidden = false;
  questionForm.elements.email.focus();
});

resetForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearFormErrors(resetForm, resetError);
  const { answer, new_password: password, new_password_confirm: confirm } = resetForm.elements;

  if (answer.value.trim() === "") {
    showFormErrors(resetForm, resetError, { fieldErrors: { answer: "답을 입력해 주세요." } });
    return;
  }
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
    await resetPassword({ email, answer: answer.value, new_password: password.value });
    window.location.assign(authPageUrl(LOGIN_PAGE, { reset: "1" }));
  } catch (error) {
    // 400(이메일·답 불일치)과 429(잠김·횟수 초과)는 서버 메시지를 공통 영역에, 422는 해당 칸 아래에 보여준다.
    showFormErrors(resetForm, resetError, error);
    submit.disabled = false;
    submit.textContent = "비밀번호 바꾸기";
  }
});
