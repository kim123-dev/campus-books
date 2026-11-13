// 신고 창과 차단 확인. 상세 화면(글 신고·판매자 차단)과 대화 화면(사용자 신고·상대 차단)이 함께 쓴다.
// 요소는 모두 createElement로 만들고 값은 textContent로 넣는다.
import { redirectToLogin } from "./auth.js";
import { el } from "./ui.js";

// 서버 규칙과 같은 값. (app/schemas/report.py, app/models/report.py) 최종 검사는 서버가 한다.
const MAX_DESCRIPTION = 500;
export const REPORT_REASONS = [
  ["SPAM", "광고·도배"],
  ["FRAUD", "사기 의심"],
  ["ABUSE", "욕설·괴롭힘"],
  ["INAPPROPRIATE", "부적절한 글·물품"],
  ["OTHER", "기타 (설명 필수)"],
];

export const REPORT_DONE_TEXT = "신고가 접수되었습니다. 신고한 사실과 신고자는 상대에게 알려지지 않아요.";
export const BLOCK_DONE_TEXT = "차단했습니다. 서로 쪽지를 보낼 수 없고, 이 사용자의 글은 목록에 보이지 않습니다.";
export const BLOCK_LIST_TEXT = "차단 목록은 내 정보 화면에서 확인·해제할 수 있어요.";
export const UNBLOCK_DONE_TEXT = "차단을 해제했습니다.";
const ME_PAGE = "/static/me.html";

/** 차단 전에 무엇이 달라지는지 알려주고 확인한다. 기존 삭제 확인과 같이 브라우저 확인 창을 쓴다. */
export function confirmBlock(nickname) {
  return window.confirm(
    `${nickname}님을 차단할까요?\n\n` +
      "· 서로 쪽지를 보낼 수 없어요.\n" +
      `· ${nickname}님의 글이 목록에 보이지 않아요.\n` +
      `· ${BLOCK_LIST_TEXT}`,
  );
}

export function confirmUnblock(nickname) {
  return window.confirm(`${nickname}님 차단을 해제할까요? 다시 쪽지를 주고받을 수 있고 글도 목록에 보여요.`);
}

/** 차단 완료 안내 내용. 마지막 줄에 내 정보 화면으로 가는 링크를 붙인다. */
export function blockDoneContent() {
  return [
    el("span", { className: "safety-notice__line", text: BLOCK_DONE_TEXT }),
    el(
      "span",
      { className: "safety-notice__line" },
      `${BLOCK_LIST_TEXT} `,
      el("a", { href: ME_PAGE, text: "내 정보 화면으로" }),
    ),
  ];
}

/**
 * 신고 창을 연다. 신고가 접수되면 true, 취소하면 false로 끝나는 Promise를 돌려준다.
 * 브라우저 기본 <dialog>(showModal)를 써서 Esc로 닫히고, 열려 있는 동안 뒤 화면은 누를 수 없다.
 * @param {{heading: string, targetText: string, send: (data: {reason: string, description: string}) => Promise}} options
 *   send: 서버에 신고를 보내는 함수 (글 신고 또는 사용자 신고)
 */
export function openReportDialog({ heading, targetText, send }) {
  const titleId = "report-dialog-title";
  const reasonGroup = el(
    "fieldset",
    { className: "report-dialog__reasons" },
    el("legend", { text: "신고 사유" }),
    ...REPORT_REASONS.map(([value, label]) =>
      el(
        "label",
        { className: "report-dialog__reason" },
        el("input", { type: "radio", name: "reason", value }),
        el("span", { text: label }),
      ),
    ),
  );
  const description = el("textarea", {
    id: "report-description",
    name: "description",
    rows: 4,
    maxLength: MAX_DESCRIPTION,
    attrs: { "aria-describedby": "report-description-count" },
  });
  const counter = el("span", {
    id: "report-description-count",
    className: "report-dialog__count",
    text: `0 / ${MAX_DESCRIPTION}`,
  });
  const errorText = el("p", { className: "form-error", attrs: { role: "alert" }, hidden: true });
  const cancelButton = el("button", { type: "button", className: "button", text: "취소" });
  const submitButton = el("button", { type: "submit", className: "button button--danger-solid", text: "신고하기" });

  const form = el(
    "form",
    { className: "report-dialog__form", noValidate: true },
    el("h2", { id: titleId, className: "report-dialog__title", text: heading }),
    el("p", { className: "report-dialog__target", text: targetText }),
    reasonGroup,
    el(
      "div",
      { className: "field" },
      el("label", { htmlFor: "report-description", text: "설명 (선택, 기타는 필수)" }),
      description,
      counter,
    ),
    el("p", { className: "field-hint", text: "신고한 사실과 신고자는 상대에게 알려지지 않습니다. 허위 신고는 제재될 수 있어요." }),
    errorText,
    el("div", { className: "report-dialog__actions" }, cancelButton, submitButton),
  );
  const dialog = el("dialog", { className: "report-dialog", attrs: { "aria-labelledby": titleId } }, form);
  document.body.append(dialog);

  return new Promise((resolve) => {
    let reported = false;
    const showError = (message) => {
      errorText.textContent = message;
      errorText.hidden = false;
    };

    description.addEventListener("input", () => {
      counter.textContent = `${description.value.length} / ${MAX_DESCRIPTION}`;
    });
    cancelButton.addEventListener("click", () => dialog.close());
    // Esc·취소·접수 완료 모두 close 이벤트 한 곳에서 정리한다.
    dialog.addEventListener("close", () => {
      dialog.remove();
      resolve(reported);
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      errorText.hidden = true;
      const reason = form.elements.reason.value;
      const text = description.value.trim();
      // 서버가 422로 막는 내용을 보내기 전에 알려준다.
      if (!reason) {
        showError("신고 사유를 골라 주세요.");
        reasonGroup.querySelector("input").focus();
        return;
      }
      if (reason === "OTHER" && text === "") {
        showError("기타 사유는 설명을 입력해 주세요.");
        description.focus();
        return;
      }

      submitButton.disabled = true;
      submitButton.textContent = "보내는 중…";
      try {
        await send({ reason, description: text });
        reported = true;
        dialog.close();
      } catch (error) {
        if (error.status === 401) {
          dialog.close();
          redirectToLogin();
          return;
        }
        // 409(이미 신고), 429(횟수 제한), 400(내 글), 404(그사이 삭제됨)는 서버 메시지를 그대로 보여준다.
        showError(error.message);
        submitButton.disabled = false;
        submitButton.textContent = "신고하기";
      }
    });

    dialog.showModal();
    reasonGroup.querySelector("input").focus();
  });
}

/**
 * 작은 메뉴 창(신고·차단·나가기 등)을 연다. 고른 항목의 key, 취소하면 null로 끝나는 Promise를 돌려준다.
 * 신고 창과 같은 <dialog>를 써서 Esc로 닫히고 뒤 화면은 누를 수 없다. 모바일에서는 화면 아래에서 올라온다.
 * @param {{ heading: string, items: {key: string, label: string, danger?: boolean}[] }} options
 */
export function openActionMenu({ heading, items }) {
  const titleId = "action-menu-title";
  const buttons = items.map(({ key, label, danger }) =>
    el("button", {
      type: "button",
      className: `action-menu__item${danger ? " action-menu__item--danger" : ""}`,
      text: label,
      attrs: { "data-key": key },
    }),
  );
  const cancel = el("button", { type: "button", className: "action-menu__item action-menu__cancel", text: "취소" });
  const dialog = el(
    "dialog",
    { className: "report-dialog action-menu", attrs: { "aria-labelledby": titleId } },
    el("h2", { id: titleId, className: "action-menu__title", text: heading }),
    ...buttons,
    cancel,
  );
  document.body.append(dialog);
  return new Promise((resolve) => {
    let chosen = null;
    for (const button of buttons) {
      button.addEventListener("click", () => {
        chosen = button.dataset.key;
        dialog.close();
      });
    }
    cancel.addEventListener("click", () => dialog.close());
    // 창 바깥(배경)을 누르면 닫는다. 메뉴는 고를 것만 있어 실수로 닫혀도 잃는 내용이 없다.
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener("close", () => {
      dialog.remove();
      resolve(chosen);
    });
    dialog.showModal();
    buttons[0]?.focus();
  });
}

/** 나가기 전에 무엇이 달라지는지 알려주고 확인한다. */
export function confirmLeave(nickname) {
  return window.confirm(
    `${nickname}님과의 대화방에서 나갈까요?\n\n` +
      "· 내 쪽지함에서만 사라지고, 상대에게는 그대로 남아요.\n" +
      "· 상대가 새 쪽지를 보내면 다시 나타나지만, 지금까지의 대화는 보이지 않아요.",
  );
}
