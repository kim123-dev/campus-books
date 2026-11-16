// 학교 관리 화면 (관리자 전용): 학교 추가, 이름·순서 수정, 비활성/다시 활성.
// 비활성 학교는 새로 고를 수 없지만, 이미 연결된 글·사용자의 학교 표시는 그대로 남는다. (서버 규칙)
import { handleAuthError, startAdminPage } from "../admin-common.js";
import { adminCreateSchool, adminListSchools, adminUpdateSchool } from "../api.js";
import { clearFormErrors, el, formatDate, showFormErrors } from "../ui.js";

const main = document.getElementById("admin-main");
const notice = document.getElementById("admin-notice");
const summary = document.getElementById("result-summary");
const listError = document.getElementById("list-error");
const list = document.getElementById("school-list");
const addForm = document.getElementById("school-add-form");

init();

async function init() {
  if ((await startAdminPage(main)) === null) return;
  addForm.addEventListener("submit", onAdd);
  load();
}

function showNotice(text) {
  notice.textContent = text;
  notice.hidden = false;
}

async function onAdd(event) {
  event.preventDefault();
  const errorBox = addForm.querySelector(".form-error");
  clearFormErrors(addForm, errorBox);
  const name = addForm.elements.name.value.trim();
  if (name === "") {
    showFormErrors(addForm, errorBox, { message: "이름을 입력해 주세요." });
    return;
  }
  const submit = addForm.querySelector("[type=submit]");
  submit.disabled = true;
  try {
    await adminCreateSchool({ name, sort_order: Number(addForm.elements.sort_order.value || 0) });
    addForm.reset();
    showNotice(`'${name}'을(를) 추가했습니다.`);
    load();
  } catch (error) {
    if (!handleAuthError(error)) showFormErrors(addForm, errorBox, error);
  } finally {
    submit.disabled = false;
  }
}

async function load() {
  summary.textContent = "불러오는 중…";
  listError.hidden = true;
  list.replaceChildren();
  let items;
  try {
    ({ items } = await adminListSchools());
  } catch (error) {
    if (handleAuthError(error)) return;
    summary.textContent = "";
    listError.textContent = error.message;
    listError.hidden = false;
    return;
  }
  const active = items.filter((school) => school.is_active).length;
  summary.textContent = `총 ${items.length}개 · 활성 ${active}개`;
  list.replaceChildren(...items.map(schoolCard));
}

/** 학교 하나: 이름·순서 고치기 + 비활성/다시 활성 */
function schoolCard(school) {
  const nameId = `school-${school.id}-name`;
  const orderId = `school-${school.id}-order`;
  const name = el("input", { id: nameId, type: "text", value: school.name, maxLength: 100, autocomplete: "off" });
  const order = el("input", { id: orderId, type: "number", value: String(school.sort_order), min: 0, max: 9999 });
  const error = el("p", { className: "form-error", attrs: { role: "alert" }, hidden: true });
  const save = el("button", { type: "button", className: "button", text: "저장" });
  const toggle = el("button", {
    type: "button",
    className: school.is_active ? "button button--danger" : "button",
    text: school.is_active ? "비활성" : "다시 활성",
  });

  const run = async (data, done) => {
    error.hidden = true;
    save.disabled = true;
    toggle.disabled = true;
    try {
      await adminUpdateSchool(school.id, data);
      showNotice(done);
      load();
    } catch (failure) {
      if (handleAuthError(failure)) return;
      error.textContent = failure.fieldErrors ? Object.values(failure.fieldErrors).join(" ") : failure.message;
      error.hidden = false;
      save.disabled = false;
      toggle.disabled = false;
    }
  };
  save.addEventListener("click", () => {
    const newName = name.value.trim();
    if (newName === "") {
      error.textContent = "이름을 입력해 주세요.";
      error.hidden = false;
      return;
    }
    run({ name: newName, sort_order: Number(order.value || 0) }, `'${newName}'을(를) 저장했습니다.`);
  });
  toggle.addEventListener("click", () => {
    run({ is_active: !school.is_active }, school.is_active ? `'${school.name}'을(를) 비활성으로 바꿨습니다.` : `'${school.name}'을(를) 다시 활성으로 바꿨습니다.`);
  });

  return el(
    "li",
    { className: "card admin-card" },
    el(
      "div",
      { className: "admin-card__head" },
      el("h3", { className: "admin-card__title", text: school.name }),
      el("span", { className: "admin-badge", text: school.is_active ? "활성" : "비활성" }),
    ),
    el("p", { className: "admin-card__meta", text: `학교 #${school.id} · 추가 ${formatDate(school.created_at)}` }),
    el("div", { className: "field" }, el("label", { htmlFor: nameId, text: "이름" }), name),
    el("div", { className: "field" }, el("label", { htmlFor: orderId, text: "순서" }), order),
    error,
    el("div", { className: "admin-card__actions" }, save, toggle),
  );
}
