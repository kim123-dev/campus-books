// 본인 확인 질문 고르기: 가입 화면과 내 정보(등록·변경)에서 같은 모양으로 쓴다.
// 질문 목록은 서버(app/schemas/security_question.py)와 같아야 한다. 테스트(test_static)가 둘이 같은지 확인한다.
import { el } from "./ui.js";

export const PRESET_QUESTIONS = {
  CHILDHOOD_SHOP: "어릴 때 살던 동네에서 자주 가던 가게 이름은?",
  FIRST_BOOK_OR_ALBUM: "처음으로 산 책이나 음반의 제목은?",
  CHILDHOOD_FRIEND_NICKNAME: "초등학교 때 가장 친했던 친구의 별명은?",
  FIRST_PART_TIME_JOB: "처음 아르바이트한 곳의 이름은?",
  CHILDHOOD_TOY_NAME: "어릴 때 아끼던 인형이나 장난감에 붙인 이름은?",
  SCHOOL_CLUB: "중·고등학교 때 들었던 동아리 이름은?",
  FIRST_AWARD: "처음으로 받은 상장의 이름은?",
  FAMILY_RESTAURANT: "어릴 때 가족끼리 자주 가던 식당 이름은?",
  FIRST_SOLO_TRIP_STAY: "처음 혼자 여행 간 곳에서 묵은 숙소나 동네 이름은?",
};

export const ANSWER_HINT = "남이 쉽게 알 수 없는 답으로 정해 주세요. 띄어쓰기와 대소문자는 구분하지 않아요. (공백 빼고 2~20자)";
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
    el("option", { text: "질문을 골라 주세요", attrs: { value: "" } }),
    ...Object.entries(PRESET_QUESTIONS).map(([key, text]) => el("option", { text, attrs: { value: key } })),
    el("option", { text: "직접 만들기", attrs: { value: CUSTOM } }),
  );
  const customInput = el("input", {
    type: "text",
    attrs: { id: customId, name: "custom_question", maxlength: "60", autocomplete: "off", "aria-describedby": `${customId}-hint` },
  });
  const customField = el(
    "div",
    { className: "field" },
    el("label", { text: "내가 만든 질문", attrs: { for: customId } }),
    customInput,
    el("p", {
      className: "field-hint",
      text: "5~60자. 질문에 답이나 답의 힌트를 넣지 마세요. 친구·가족이 금방 맞힐 수 있는 질문도 피해 주세요.",
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
      el("label", { text: "본인 확인 질문", attrs: { for: selectId } }),
      select,
      el("p", { className: "field-hint", text: "비밀번호를 잊었을 때 이 질문의 답으로 재설정해요.", attrs: { id: `${selectId}-hint` } }),
      el("p", { className: "field-error", attrs: { "data-error-for": "question_key" }, hidden: true }),
    ),
    customField,
    el(
      "div",
      { className: "field" },
      el("label", { text: "답", attrs: { for: answerId } }),
      answerInput,
      el("p", { className: "field-hint", text: ANSWER_HINT, attrs: { id: `${answerId}-hint` } }),
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
      if (select.value === "") return { question_key: "질문을 골라 주세요." };
      if (select.value === CUSTOM && customInput.value.trim().length < 5) return { custom_question: "질문을 5자 이상 적어 주세요." };
      const length = normalizeAnswer(answerInput.value).length;
      if (length < 2) return { answer: "답은 공백을 빼고 2자 이상이어야 합니다." };
      if (length > 20) return { answer: "답은 공백을 빼고 20자 이하여야 합니다." };
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
