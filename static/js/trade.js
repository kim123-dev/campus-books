// 거래 관련 창: 판매 완료 때 구매자 고르기(상세 화면), 거래 후기 쓰기(쪽지 화면). 신고 창과 같은 <dialog> 모양을 쓴다.
// 요소는 모두 createElement로 만들고 값은 textContent로 넣는다.
import { redirectToLogin } from "./auth.js";
import { el } from "./ui.js";

// "선택 안 함" 라디오의 값. 서버에는 buyer_id: null로 보낸다.
const NO_BUYER = "none";

// 서버 규칙과 같은 값. (app/schemas/review.py) 최종 검사는 서버가 한다.
const MAX_REVIEW_LENGTH = 200;
export const RATING_LABELS = { GOOD: "좋아요", BAD: "아쉬워요" };
export const REVIEWEE_ROLE_LABELS = { SELLER: "판매자로서", BUYER: "구매자로서" };

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

/**
 * 후기 쓰기 창. 남기면 true, 취소하면 false로 끝나는 Promise를 돌려준다.
 * 남긴 후기는 고치거나 지울 수 없으므로 창 안에 미리 알린다.
 * @param {{partnerNickname: string, send: (data: {rating: string, content: string}) => Promise}} options
 */
export function openReviewDialog({ partnerNickname, send }) {
  const titleId = "review-dialog-title";
  const ratingGroup = el(
    "fieldset",
    { className: "report-dialog__reasons review-dialog__ratings" },
    el("legend", { text: "거래는 어땠나요?" }),
    ...Object.entries(RATING_LABELS).map(([value, label]) =>
      el(
        "label",
        { className: "report-dialog__reason" },
        el("input", { type: "radio", name: "rating", value }),
        el("span", { text: label }),
      ),
    ),
  );
  const content = el("textarea", {
    id: "review-content",
    name: "content",
    rows: 3,
    maxLength: MAX_REVIEW_LENGTH,
    attrs: { "aria-describedby": "review-content-count" },
  });
  const counter = el("span", { id: "review-content-count", className: "report-dialog__count", text: `0 / ${MAX_REVIEW_LENGTH}` });
  const errorText = el("p", { className: "form-error", attrs: { role: "alert" }, hidden: true });
  const cancelButton = el("button", { type: "button", className: "button", text: "취소" });
  const submitButton = el("button", { type: "submit", className: "button button--primary", text: "후기 남기기" });

  const form = el(
    "form",
    { className: "report-dialog__form", noValidate: true },
    el("h2", { id: titleId, className: "report-dialog__title", text: "거래 후기" }),
    el("p", { className: "report-dialog__target", text: `${partnerNickname}님과의 거래` }),
    ratingGroup,
    el("div", { className: "field" }, el("label", { htmlFor: "review-content", text: "한마디 (선택)" }), content, counter),
    el("p", { className: "field-hint", text: "후기는 상대 프로필에 공개되고, 남긴 뒤에는 고치거나 지울 수 없어요." }),
    errorText,
    el("div", { className: "report-dialog__actions" }, cancelButton, submitButton),
  );
  const dialog = el("dialog", { className: "report-dialog", attrs: { "aria-labelledby": titleId } }, form);
  document.body.append(dialog);

  return new Promise((resolve) => {
    let written = false;
    content.addEventListener("input", () => {
      counter.textContent = `${content.value.length} / ${MAX_REVIEW_LENGTH}`;
    });
    cancelButton.addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => {
      dialog.remove();
      resolve(written);
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      errorText.hidden = true;
      const rating = form.elements.rating.value;
      if (!rating) {
        errorText.textContent = "좋아요 또는 아쉬워요를 골라 주세요.";
        errorText.hidden = false;
        ratingGroup.querySelector("input").focus();
        return;
      }
      submitButton.disabled = true;
      try {
        await send({ rating, content: content.value.trim() });
        written = true;
        dialog.close();
      } catch (error) {
        if (error.status === 401) {
          dialog.close();
          redirectToLogin();
          return;
        }
        // 409(이미 작성), 400(기간 지남), 403(정지), 404(상대 탈퇴)는 서버 메시지를 그대로 보여준다.
        errorText.textContent = error.message;
        errorText.hidden = false;
        submitButton.disabled = false;
      }
    });

    dialog.showModal();
    ratingGroup.querySelector("input").focus();
  });
}
