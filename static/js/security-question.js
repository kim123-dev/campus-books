// 본인 확인 질문 고르기: 가입 화면과 내 정보(등록·변경)에서 같은 모양으로 쓴다.
// 질문 목록(영문 키)은 서버(app/schemas/security_question.py)와 같아야 한다. 질문 문장은 사전의 question.<키>에 있고,
// 테스트(test_static)가 키 목록과 한국어 문장이 서버와 같은지 확인한다. 서버에는 키만 보내므로 화면 언어와 관계없다.
import { t } from "./i18n.js";
import { el } from "./ui.js";

export const PRESET_QUESTION_KEYS = [
  "CHILDHOOD_SHOP",
  "FIRST_BOOK_OR_ALBUM",
  "CHILDHOOD_FRIEND_NICKNAME",
  "FIRST_PART_TIME_JOB",
  "CHILDHOOD_TOY_NAME",
  "SCHOOL_CLUB",
  "FIRST_AWARD",
  "FAMILY_RESTAURANT",
  "FIRST_SOLO_TRIP_STAY",
];
const CUSTOM = "__custom";

// 서버와 같은 규칙으로 정리한다. 화면에서 미리 길이를 알려주는 데만 쓰고, 최종 검사는 서버가 한다.
export function normalizeAnswer(value) {
  return value.normalize("NFKC").toLowerCase().replace(/\s+/gu, "");
}

/**
 * 질문 고르기 칸(목록 + 직접 만들기)과 답 칸을 container에 그린다.
 * 서버 오류는 칸 이름(question_key, custom_question, answer, security_question) 아래에 나온다.
 * @returns {{ value: () => object, check: () => Record<string, string> | null, reset: () => void }}
 */
export function renderSecurityQuestionFields(container, { idPrefix }) {
  const selectId = `${idPrefix}-question`;
  const customId = `${idPrefix}-custom-question`;
  const answerId = `${idPrefix}-answer`;

  const select = el(
    "select",
    { attrs: { id: selectId, name: "question_key", "aria-describedby": `${selectId}-hint` } },
    el("option", { text: t("sq.placeholder"), attrs: { value: "" } }),
    ...PRESET_QUESTION_KEYS.map((key) => el("option", { text: t(`question.${key}`), attrs: { value: key } })),
    el("option", { text: t("sq.custom"), attrs: { value: CUSTOM } }),
  );
  const customInput = el("input", {
    type: "text",
    attrs: { id: customId, name: "custom_question", maxlength: "60", autocomplete: "off", "aria-describedby": `${customId}-hint` },
  });
  const customField = el(
    "div",
    { className: "field" },
    el("label", { text: t("sq.custom_label"), attrs: { for: customId } }),
    customInput,
    el("p", {
      className: "field-hint",
      text: t("sq.custom_hint"),
      attrs: { id: `${customId}-hint` },
    }),
    el("p", { className: "field-error", attrs: { "data-error-for": "custom_question" }, hidden: true }),
  );
  customField.hidden = true;
  const answerInput = el("input", {
    type: "text",
    attrs: { id: answerId, name: "answer", maxlength: "100", autocomplete: "off", spellcheck: "false", "aria-describedby": `${answerId}-hint` },
  });

  select.addEventListener("change", () => {
    // 질문을 다시 골랐으니 "질문을 골라 주세요" 같은 지난 안내는 지운다.
    const error = container.querySelector('[data-error-for="question_key"]');
    error.hidden = true;
    error.textContent = "";
    customField.hidden = select.value !== CUSTOM;
    if (!customField.hidden) customInput.focus();
  });

  container.replaceChildren(
    el(
      "div",
      { className: "field" },
      el("label", { text: t("term.security_question"), attrs: { for: selectId } }),
      select,
      el("p", { className: "field-hint", text: t("sq.hint"), attrs: { id: `${selectId}-hint` } }),
      el("p", { className: "field-error", attrs: { "data-error-for": "question_key" }, hidden: true }),
    ),
    customField,
    el(
      "div",
      { className: "field" },
      el("label", { text: t("field.answer"), attrs: { for: answerId } }),
      answerInput,
      el("p", { className: "field-hint", text: t("sq.answer_hint"), attrs: { id: `${answerId}-hint` } }),
      el("p", { className: "field-error", attrs: { "data-error-for": "answer" }, hidden: true }),
    ),
    // 질문과 답을 함께 본 검사(답이 질문에 들어 있음 등)는 이 칸에 나온다.
    el("p", { className: "field-error", attrs: { "data-error-for": "security_question" }, hidden: true }),
  );

  return {
    value() {
      const answer = answerInput.value;
      return select.value === CUSTOM ? { custom_question: customInput.value.trim(), answer } : { question_key: select.value, answer };
    },
    // 서버에 보내기 전에 빈 칸과 길이만 확인한다. 문제가 없으면 null.
    check() {
      if (select.value === "") return { question_key: t("sq.choose") };
      if (select.value === CUSTOM && customInput.value.trim().length < 5) return { custom_question: t("sq.custom_too_short") };
      const length = normalizeAnswer(answerInput.value).length;
      if (length < 2) return { answer: t("sq.answer_too_short") };
      if (length > 20) return { answer: t("sq.answer_too_long") };
      return null;
    },
    reset() {
      select.value = "";
      customInput.value = "";
      answerInput.value = "";
      customField.hidden = true;
    },
  };
}
