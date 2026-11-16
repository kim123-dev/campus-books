// 언어 선택 UI: 헤더의 🌐 버튼(모든 화면, 로그인 전에도)과 내 정보 화면의 "언어" 칸.
// 둘 다 기능 플래그(LANG_SWITCH_ENABLED)가 꺼져 있으면 그리지 않는다.
// 언어 이름은 그 언어로 쓴다("English", "简体中文"). 지금 화면 언어를 못 읽는 사람도 자기 언어를 찾을 수 있게 하기 위해서다.
import { LANG, LANGUAGES, LANG_SWITCH_ENABLED, setLanguage, t } from "./i18n.js";
import { el, icon } from "./ui.js";

/** 헤더 오른쪽의 언어 버튼과 펼침 목록. 플래그가 꺼져 있으면 null. */
export function languageMenu() {
  if (!LANG_SWITCH_ENABLED) return null;
  const menuId = "lang-menu";
  const button = el(
    "button",
    {
      type: "button",
      className: "site-lang",
      attrs: { "aria-label": t("lang.button_aria"), "aria-haspopup": "true", "aria-expanded": "false", "aria-controls": menuId },
    },
    icon("globe"),
  );
  const menu = el(
    "ul",
    { className: "lang-menu", attrs: { id: menuId }, hidden: true },
    ...LANGUAGES.map(({ code, name }) => el("li", {}, languageButton(code, name, "lang-menu__item"))),
  );
  const wrap = el("div", { className: "site-lang-wrap" }, button, menu);

  const close = () => {
    menu.hidden = true;
    button.setAttribute("aria-expanded", "false");
  };
  button.addEventListener("click", () => {
    const open = menu.hidden;
    menu.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
    if (open) menu.querySelector("[aria-current]")?.focus();
  });
  // 지금 언어를 다시 고르거나, 목록 밖을 누르거나, Esc를 누르면 닫는다.
  menu.addEventListener("click", (event) => {
    if (event.target.closest("[aria-current]")) close();
  });
  document.addEventListener("click", (event) => {
    if (!menu.hidden && !wrap.contains(event.target)) close();
  });
  wrap.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !menu.hidden) {
      close();
      button.focus();
    }
  });
  return wrap;
}

/** 내 정보 화면의 언어 버튼 묶음. 플래그가 꺼져 있으면 null. */
export function languageOptions() {
  if (!LANG_SWITCH_ENABLED) return null;
  return el(
    "div",
    { className: "lang-options", attrs: { role: "group", "aria-label": t("lang.title") } },
    ...LANGUAGES.map(({ code, name }) => languageButton(code, name, "button lang-options__item")),
  );
}

// 언어 하나의 버튼. 지금 언어는 aria-current로 표시하고, 누르면 저장한 뒤 화면을 다시 불러온다.
function languageButton(code, name, className) {
  const current = code === LANG;
  const button = el("button", {
    type: "button",
    className,
    text: name,
    // 언어 이름을 그 언어의 발음으로 읽게 한다.
    attrs: { lang: code, ...(current ? { "aria-current": "true" } : {}) },
  });
  button.addEventListener("click", () => {
    if (!current) setLanguage(code);
  });
  return button;
}
