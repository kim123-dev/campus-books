// 화면 문구 번역. 사전은 static/i18n/<언어>.json이고, 외부 번역 API는 쓰지 않는다.
// 언어는 lang-boot.js가 <html lang>에 정해 둔다. 이 모듈은 그 언어의 사전을 받아 t()로 문구를 돌려준다.
//
// 사전 규칙
// - 키: "영역.항목" (예: "nav.main_aria", "err.status.404"). 세 언어 파일의 키 목록이 같아야 한다.
// - {name}: 부를 때 넘긴 값으로 바꾼다. 세 언어에서 이름이 같아야 한다.
// - {@키}: 다른 항목(주로 term.* 용어)을 그대로 끼워 넣는다. 용어를 한곳에서만 정해 일관되게 쓰기 위해서다.
// - 값이 {"one": ..., "other": ...}이면 {count}로 복수형을 고른다. (한국어·중국어는 문자열 하나)
// (tests/test_i18n.py가 이 규칙을 검사한다)

export const LANGUAGES = [
  { code: "ko", name: "한국어" },
  { code: "en", name: "English" },
  { code: "zh-CN", name: "简体中文" },
];
const DEFAULT_LANG = "ko";
// lang-boot.js와 같은 키. 언어를 바꿀 때 여기에 저장한다.
const STORAGE_KEY = "campus-books.lang";
// 숫자·날짜 형식에 쓰는 지역
const LOCALES = { ko: "ko-KR", en: "en-US", "zh-CN": "zh-CN" };
const REF = /\{@([\w.]+)\}/g;
const PLACEHOLDER = /\{(\w+)\}/g;

/** 언어 선택 버튼을 보여줄지. 기능 플래그는 lang-boot.js의 상수 하나다. */
export const LANG_SWITCH_ENABLED = document.documentElement.hasAttribute("data-lang-switch");

const requested = LANGUAGES.some(({ code }) => code === document.documentElement.lang) ? document.documentElement.lang : DEFAULT_LANG;
const loaded = await loadMessages(requested);

/** 지금 화면 언어. 사전을 받지 못해 한국어로 돌아갔으면 "ko"다. */
export const LANG = loaded.lang;
export const LOCALE = LOCALES[LANG];
const messages = loaded.messages;
const pluralRules = new Intl.PluralRules(LOCALE);

// 사전을 받은 뒤 HTML에 적어 둔 문구를 바꾸고, lang-boot.js가 숨겨 둔 화면을 보인다.
// 모듈은 문서를 다 읽은 뒤 실행되므로 이 시점에 HTML 요소가 모두 있다.
document.documentElement.setAttribute("lang", LANG);
if (LANG !== DEFAULT_LANG) applyI18n(document);
document.documentElement.removeAttribute("data-i18n-pending");

// 고른 언어 사전을 받지 못하면 한국어 사전으로, 그것도 안 되면 빈 사전(키가 보임)으로 둔다.
async function loadMessages(lang) {
  for (const candidate of lang === DEFAULT_LANG ? [lang] : [lang, DEFAULT_LANG]) {
    try {
      const response = await fetch(`/static/i18n/${candidate}.json`);
      if (response.ok) return { lang: candidate, messages: resolveRefs(await response.json()) };
    } catch {
      // 다음 후보로 넘어간다.
    }
  }
  return { lang: DEFAULT_LANG, messages: {} };
}

// {@키}를 미리 풀어 둔다. 부를 때마다 풀지 않아도 되게 하기 위해서다.
function resolveRefs(raw) {
  const expand = (text, depth = 0) =>
    depth > 5 ? text : text.replace(REF, (whole, key) => (typeof raw[key] === "string" ? expand(raw[key], depth + 1) : whole));
  const result = {};
  for (const [key, value] of Object.entries(raw)) {
    result[key] =
      typeof value === "string" ? expand(value) : Object.fromEntries(Object.entries(value).map(([form, text]) => [form, expand(text)]));
  }
  return result;
}

/**
 * 키의 문구. params의 값으로 {name}을 바꾸고, 복수형 항목이면 params.count로 고른다.
 * 사전에 없는 키는 키 이름을 그대로 돌려준다(빠진 번역이 눈에 띄게).
 */
export function t(key, params = {}) {
  let value = messages[key];
  if (value === undefined) return key;
  if (typeof value !== "string") value = value[pluralRules.select(Number(params.count))] ?? value.other;
  return value.replace(PLACEHOLDER, (whole, name) => (name in params ? String(params[name]) : whole));
}

/**
 * t()와 같지만 {name} 자리에 요소(Node)도 끼울 수 있다. 문장 가운데 아이콘·링크가 들어가는 곳에 쓴다.
 * 돌려주는 배열(문자열과 Node)은 el()의 자식이나 append()에 그대로 넘긴다. HTML 문자열은 만들지 않는다.
 */
export function tNodes(key, params = {}) {
  const parts = [];
  let last = 0;
  const text = t(key, Object.fromEntries(Object.entries(params).filter(([, value]) => !(value instanceof Node))));
  for (const match of text.matchAll(PLACEHOLDER)) {
    const value = params[match[1]];
    if (!(value instanceof Node)) continue;
    parts.push(text.slice(last, match.index), value);
    last = match.index + match[0].length;
  }
  parts.push(text.slice(last));
  return parts.filter((part) => part !== "");
}

/**
 * HTML에 적어 둔 번역 표시를 적용한다. HTML 문자열을 해석하지 않고 textContent와 setAttribute만 쓴다.
 * - data-i18n="키": 글자를 바꾼다.
 * - data-i18n-attr="placeholder:키;aria-label:키": 속성을 바꾼다.
 * - <meta name="i18n-title" content="키">: 문서 제목(<title>)을 바꾼다. <title> 태그는 원문 그대로 두기 위해 키를 따로 적는다.
 */
export function applyI18n(root) {
  const titleKey = root.querySelector?.('meta[name="i18n-title"]')?.getAttribute("content");
  if (titleKey) document.title = t(titleKey);
  for (const node of root.querySelectorAll("[data-i18n]")) node.textContent = t(node.dataset.i18n);
  for (const node of root.querySelectorAll("[data-i18n-attr]")) {
    for (const pair of node.dataset.i18nAttr.split(";")) {
      const [attr, key] = pair.split(":").map((part) => part.trim());
      if (attr && key) node.setAttribute(attr, t(key));
    }
  }
}

/** 언어를 바꾼다. 저장한 뒤 화면을 다시 불러와, JS가 그린 문장까지 모두 새 언어로 그리게 한다. */
export function setLanguage(code) {
  const url = new URL(window.location.href);
  try {
    localStorage.setItem(STORAGE_KEY, code);
    // 주소에 ?lang=이 남아 있으면 저장한 값보다 먼저 적용되므로 지운다.
    url.searchParams.delete("lang");
  } catch {
    // 저장이 막혔으면 주소의 ?lang=으로 이번 화면만이라도 바꿔 보여준다.
    url.searchParams.set("lang", code);
  }
  // 주소가 같으면(#이 붙은 주소 포함) replace가 다시 불러오지 않으므로 reload를 쓴다.
  if (url.href === window.location.href) window.location.reload();
  else window.location.replace(url);
}

// ---------- 숫자·날짜 ----------

/** 언어에 맞는 숫자 형식 (12000 → "12,000") */
export function formatNumber(value) {
  return new Intl.NumberFormat(LOCALE).format(value);
}

/** 언어에 맞는 날짜·시각 형식. options는 Intl.DateTimeFormat과 같다. 시각은 모든 언어에서 24시간제로 쓴다. */
export function formatDateWith(date, options) {
  return new Intl.DateTimeFormat(LOCALE, { hourCycle: "h23", ...options }).format(date);
}

/** "3일 전", "3 days ago", "3天前". value는 음수면 과거다. unit: "day" | "hour" | "minute" 등 */
export function formatRelative(value, unit) {
  return new Intl.RelativeTimeFormat(LOCALE, { numeric: "always" }).format(value, unit);
}
