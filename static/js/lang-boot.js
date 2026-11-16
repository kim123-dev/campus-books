// 화면 언어를 정하는 작은 스크립트. 모든 화면의 <head>에서 CSS·모듈보다 먼저 실행된다(모듈이 아님).
// 화면을 그리기 전에 <html lang>을 정해 두어야, 한국어가 잠깐 보였다가 바뀌는 깜빡임을 막을 수 있기 때문이다.
// 사전을 불러와 글자를 바꾸는 일은 i18n.js가 한다. 여기서는 언어를 정하고, 사전을 미리 받기 시작만 한다.
(function () {
  // 기능 플래그: 켜면 언어 선택 버튼(헤더 🌐·내 정보 언어 칸)을 보이고, 저장된 값이 없을 때 브라우저 언어를 따른다.
  // 끄면 둘 다 숨기고 한국어로 시작한다. 꺼져 있어도 확인용으로 ?lang=en 주소나 localStorage 값으로는 바꿀 수 있다.
  var LANG_SWITCH_ENABLED = true;
  // 키 이름은 i18n.js와 같아야 한다. (tests/test_i18n.py가 확인)
  var STORAGE_KEY = "campus-books.lang";
  var DEFAULT_LANG = "ko";
  var PENDING_TIMEOUT_MS = 1500;

  // "en-US" → "en", "zh-TW" → "zh-CN"처럼 지원하는 언어로 맞춘다. 지원하지 않으면 null.
  // 중국어는 간체만 준비했으므로 번체 지역(zh-TW 등)도 간체로 보여준다. 한국어보다는 읽기 쉽기 때문이다.
  function normalize(value) {
    if (typeof value !== "string") return null;
    var lower = value.toLowerCase();
    if (lower === "ko" || lower.indexOf("ko-") === 0) return "ko";
    if (lower === "en" || lower.indexOf("en-") === 0) return "en";
    if (lower === "zh" || lower.indexOf("zh-") === 0) return "zh-CN";
    return null;
  }

  function readStored() {
    try {
      return normalize(localStorage.getItem(STORAGE_KEY));
    } catch (e) {
      return null; // 사생활 보호 모드 등에서 저장소가 막히면 저장하지 않은 것으로 본다.
    }
  }

  function store(lang) {
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch (e) {
      // 저장이 막혀도 이번 화면은 고른 언어로 보인다.
    }
  }

  function fromBrowser() {
    var list = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language];
    for (var i = 0; i < list.length; i++) {
      var lang = normalize(list[i]);
      if (lang) return lang;
    }
    return null;
  }

  // 순서: 주소의 ?lang= (확인용, 고른 값은 저장) → 저장된 값 → 브라우저 언어(플래그가 켜졌을 때만) → 한국어
  var lang = null;
  try {
    var queryLang = new URLSearchParams(window.location.search).get("lang");
    lang = normalize(queryLang);
    if (lang) store(lang);
  } catch (e) {
    lang = null;
  }
  if (!lang) lang = readStored();
  if (!lang && LANG_SWITCH_ENABLED) lang = fromBrowser();
  if (!lang) lang = DEFAULT_LANG;

  var root = document.documentElement;
  root.setAttribute("lang", lang);
  if (LANG_SWITCH_ENABLED) root.setAttribute("data-lang-switch", "");

  // 사전을 미리 받기 시작한다. i18n.js가 같은 주소를 fetch하면 받아 둔 응답을 쓴다.
  var preload = document.createElement("link");
  preload.rel = "preload";
  preload.as = "fetch";
  preload.crossOrigin = "anonymous";
  preload.href = "/static/i18n/" + lang + ".json";
  document.head.appendChild(preload);

  // HTML 원문은 한국어라 한국어는 숨길 필요가 없다. 다른 언어는 사전을 적용할 때까지 화면을 숨긴다.
  // i18n.js가 적용을 마치면 표시를 떼고, 사전을 받지 못해도 화면이 영영 안 보이는 일이 없게 시간이 지나면 뗀다.
  if (lang !== DEFAULT_LANG) {
    root.setAttribute("data-i18n-pending", "");
    setTimeout(function () {
      root.removeAttribute("data-i18n-pending");
    }, PENDING_TIMEOUT_MS);
  }
})();
