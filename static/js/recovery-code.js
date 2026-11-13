// 복구 코드 보여주기: 가입 직후, 비밀번호 재설정 직후, 내 정보에서 재발급한 직후에 같은 모양으로 쓴다.
// 코드 원문은 서버가 이 순간에만 보내 주고 다시 보여줄 수 없으므로, 저장했다고 확인해야 다음으로 넘어가게 한다.
import { el } from "./ui.js";

export const LOST_CODE_WARNING = "복구 코드를 잃어버리면 비밀번호를 재설정할 수 없어요.";

/**
 * 코드 상자, 복사 버튼, "안전한 곳에 저장했어요" 확인, 다음 버튼을 그린다.
 * @param {HTMLElement} container 내용을 바꿔 넣을 곳
 * @param {string} code 서버가 준 복구 코드 (ABCD-EFGH-JKMN-PQRS)
 * @param {{ continueText: string, onContinue: () => void }} options
 */
export function renderRecoveryCode(container, code, { continueText, onContinue }) {
  const codeBox = el("p", { className: "recovery-code__value", text: code, attrs: { "aria-label": `복구 코드 ${code.split("").join(" ")}` } });
  const status = el("p", { className: "recovery-code__status", attrs: { role: "status" } });
  const copyButton = el("button", { type: "button", className: "button", text: "코드 복사" });
  copyButton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(code);
      status.textContent = "복사했어요. 메모 앱이나 비밀번호 관리자에 붙여 넣어 두세요.";
    } catch {
      // http 주소나 권한 거부로 복사가 막히면 직접 옮겨 적게 한다.
      status.textContent = "복사할 수 없어요. 코드를 직접 옮겨 적어 주세요.";
    }
  });

  const checkboxId = `recovery-saved-${Math.random().toString(36).slice(2, 8)}`;
  const checkbox = el("input", { type: "checkbox", attrs: { id: checkboxId } });
  const continueButton = el("button", { type: "button", className: "button button--primary button--block", text: continueText, disabled: true });
  checkbox.addEventListener("change", () => {
    continueButton.disabled = !checkbox.checked;
  });
  continueButton.addEventListener("click", onContinue);

  container.replaceChildren(
    el(
      "div",
      { className: "recovery-code" },
      el("p", { className: "recovery-code__lead", text: "비밀번호를 잊었을 때 쓸 복구 코드예요. 지금 한 번만 보여 드려요." }),
      codeBox,
      el("div", { className: "recovery-code__actions" }, copyButton),
      status,
      el("p", { className: "recovery-code__warning", text: `${LOST_CODE_WARNING} 이메일로 다시 받을 수도 없으니 꼭 저장해 두세요.` }),
      el("label", { className: "recovery-code__check", attrs: { for: checkboxId } }, checkbox, el("span", { text: "안전한 곳에 저장했어요" })),
      continueButton,
    ),
  );
  copyButton.focus();
}
