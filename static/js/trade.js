// 거래 관련 창: 판매 완료 때 구매자 고르기(상세 화면). 신고 창과 같은 <dialog> 모양을 쓴다.
// 요소는 모두 createElement로 만들고 값은 textContent로 넣는다.
import { redirectToLogin } from "./auth.js";
import { el } from "./ui.js";

// "선택 안 함" 라디오의 값. 서버에는 buyer_id: null로 보낸다.
const NO_BUYER = "none";

/**
 * 구매자 고르기 창. 보내기에 성공하면 send의 결과, 취소하면 null로 끝나는 Promise를 돌려준다.
 * @param {{
 *   heading: string,
 *   intro: string,
 *   candidates: {id: number, nickname: string}[],
 *   currentBuyer: {id: number, nickname: string} | null,
 *   preselect: boolean,
 *   submitText: string,
 *   send: (buyerId: number | null) => Promise,
 * }} options
 *   preselect: 지금 구매자(없으면 "선택 안 함")를 미리 골라 둘지. 판매 완료 창은 실수로 넘기지 않게 비워 둔다.
 */
export function openBuyerDialog({ heading, intro, candidates, currentBuyer, preselect, submitText, send }) {
  const titleId = "buyer-dialog-title";
  // 지금 구매자가 그사이 후보에서 빠졌어도(차단 등) 목록에는 보여서 그대로 둘 수 있게 한다.
  const people = [...candidates];
  if (currentBuyer !== null && !people.some((person) => person.id === currentBuyer.id)) people.unshift(currentBuyer);
  const checkedValue = preselect ? String(currentBuyer?.id ?? NO_BUYER) : null;

  const option = (value, label) =>
    el(
      "label",
      { className: "report-dialog__reason" },
      el("input", { type: "radio", name: "buyer", value, checked: value === checkedValue }),
      el("span", { text: label }),
    );
  const group = el(
    "fieldset",
    { className: "report-dialog__reasons" },
    el("legend", { text: "거래한 사람" }),
    ...people.map((person) => option(String(person.id), person.nickname)),
    option(NO_BUYER, "선택 안 함 (오프라인 거래 등)"),
  );
  const hint =
    people.length === 0
      ? el("p", { className: "field-hint", text: "이 글로 쪽지를 주고받은 사람이 없어요." })
      : el("p", { className: "field-hint", text: "고른 사람과는 서로 한 번씩 거래 후기를 남길 수 있어요." });
  const errorText = el("p", { className: "form-error", attrs: { role: "alert" }, hidden: true });
  const cancelButton = el("button", { type: "button", className: "button", text: "취소" });
  const submitButton = el("button", { type: "submit", className: "button button--primary", text: submitText });

  const form = el(
    "form",
    { className: "report-dialog__form", noValidate: true },
    el("h2", { id: titleId, className: "report-dialog__title", text: heading }),
    el("p", { className: "report-dialog__target", text: intro }),
    group,
    hint,
    errorText,
    el("div", { className: "report-dialog__actions" }, cancelButton, submitButton),
  );
  const dialog = el("dialog", { className: "report-dialog", attrs: { "aria-labelledby": titleId } }, form);
  document.body.append(dialog);

  return new Promise((resolve) => {
    let result = null;
    cancelButton.addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => {
      dialog.remove();
      resolve(result);
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      errorText.hidden = true;
      const value = form.elements.buyer.value;
      if (!value) {
        errorText.textContent = "거래한 사람을 고르거나 “선택 안 함”을 골라 주세요.";
        errorText.hidden = false;
        group.querySelector("input").focus();
        return;
      }
      submitButton.disabled = true;
      try {
        result = await send(value === NO_BUYER ? null : Number(value));
        dialog.close();
      } catch (error) {
        if (error.status === 401) {
          dialog.close();
          redirectToLogin();
          return;
        }
        // 400(후보 아님), 409(이미 판매 완료·후기가 있음)는 서버 메시지를 그대로 보여준다.
        errorText.textContent = error.message;
        errorText.hidden = false;
        submitButton.disabled = false;
      }
    });

    dialog.showModal();
    (group.querySelector("input:checked") ?? group.querySelector("input")).focus();
  });
}
