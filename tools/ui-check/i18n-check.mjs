// 화면 언어 확인 (375px): 한국어 기본, ?lang=·저장된 값으로 바꾸기, 영어·중국어 탭 이름과 헤더가 넘치지 않는지,
// 서버 오류의 번역 문장 + 한국어 원문, 내 정보의 비밀번호 틀림 표시,
// 기능 플래그를 켰을 때(확인용으로 lang-boot.js를 바꿔 받음)의 브라우저 언어 따르기와 언어 선택 버튼.
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT, readSeed, sleep, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const seed = readSeed(OUT);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  [${W}] ${name}${detail ? `  (${detail})` : ""}`);

const b = await startBrowser(OUT, { width: W, height: 812, mobile: true });
const { evaluate, waitUntil, goto, screenshot, send, exceptions, listeners } = b;
const TOKEN_KEY = "campus-books.token";
const LANG_KEY = "campus-books.lang";
const settled = "!document.documentElement.hasAttribute('data-i18n-pending') && document.querySelector('.tab-bar') && document.fonts.status === 'loaded'";
const homeReady = `${settled} && document.querySelectorAll('.post-card').length > 0`;

// 탭 이름이 칸 안에 한 줄로 들어가는지, 화면 전체에 가로 스크롤이 없는지
const layout = () =>
  evaluate(`(() => {
    const tabs = [...document.querySelectorAll('.tab-bar__item')].map((item) => {
      const label = item.querySelector('.tab-bar__label');
      const l = label.getBoundingClientRect(), i = item.getBoundingClientRect();
      const oneLine = l.height < parseFloat(getComputedStyle(label).fontSize) * 1.9;
      return { text: label.textContent, fits: l.left >= i.left - 0.5 && l.right <= i.right + 0.5 && oneLine && i.height >= 44 };
    });
    const header = [...document.querySelectorAll('.site-header *')].every((n) => n.getBoundingClientRect().right <= ${W} + 0.5);
    return { tabs, header, wide: document.documentElement.scrollWidth > ${W}, lang: document.documentElement.lang };
  })()`);
const texts = (selector) => evaluate(`[...document.querySelectorAll(${JSON.stringify(selector)})].map((n) => n.textContent.trim())`);

try {
  // ---------- 한국어 기본 ----------
  await goto("/static/index.html");
  await evaluate("localStorage.clear()");
  await goto("/static/index.html", homeReady);
  let l = await layout();
  check("기본: <html lang=ko>, 탭 4칸 한국어", l.lang === "ko" && l.tabs.map((t) => t.text).join("|") === "홈|글쓰기|쪽지|내 정보", l.tabs.map((t) => t.text).join("|"));
  check("기본: 플래그가 꺼져 있어 언어 버튼 없음", !(await evaluate("!!document.querySelector('.site-lang')")));
  const koCards = await texts(".post-card .badge, .post-card__condition, .post-card__price");
  check("기본: 카드 문구가 예전과 같음", koCards.includes("판매 중") && koCards.includes("책 상태 상") && koCards.includes("15,000원") && koCards.includes("무료 나눔"), koCards.join(", "));

  // ---------- ?lang=en (확인용) → 저장되어 다음 화면도 영어 ----------
  await goto("/static/index.html?lang=en", homeReady);
  l = await layout();
  check("?lang=en: <html lang=en>, 탭 영어", l.lang === "en" && l.tabs.map((t) => t.text).join("|") === "Home|Sell|Messages|My page", l.tabs.map((t) => t.text).join("|"));
  check("en: 탭 이름이 칸 안 한 줄, 44px 이상", l.tabs.every((t) => t.fits), JSON.stringify(l.tabs));
  check("en: 헤더 안 넘침, 가로 스크롤 없음", l.header && !l.wide);
  const enCards = await texts(".post-card .badge, .post-card__condition, .post-card__price");
  check("en: 상태·책 상태·가격 (가격은 '원' 유지)", enCards.includes("For sale") && enCards.includes("Condition: Good") && enCards.includes("15,000원") && enCards.includes("Free"), enCards.join(", "));
  check("en: 로그인 전 헤더 링크", (await texts(".site-nav a")).join("|") === "Log in|Sign up");
  check("en: localStorage에 저장", (await evaluate(`localStorage.getItem("${LANG_KEY}")`)) === "en");
  await screenshot(`i18n-${W}-en-home.png`);
  await goto("/static/index.html", homeReady);
  check("저장된 값: 주소에 ?lang이 없어도 영어", (await evaluate("document.documentElement.lang")) === "en");

  // ---------- 서버 오류: 번역 문장 + 한국어 원문 ----------
  await goto("/static/login.html", settled);
  await evaluate(`(() => {
    const f = document.getElementById('login-form');
    f.elements.username.value = 'nobody@uicheck.ac.kr';
    f.elements.password.value = 'wrong-password-123';
    f.requestSubmit();
  })()`);
  await waitUntil("!document.querySelector('#login-form .form-error').hidden");
  const loginError = await evaluate(`(() => {
    const box = document.querySelector('#login-form .form-error'), small = box.querySelector('.error-original');
    return { main: box.firstChild?.textContent, original: small?.textContent, lang: small?.getAttribute('lang'), size: small ? parseFloat(getComputedStyle(small).fontSize) : 0, color: small ? getComputedStyle(small).color : '' };
  })()`);
  check(
    "en 로그인 실패: 401 번역 문장 + 한국어 원문(lang=ko, 작은 회색)",
    loginError.main?.startsWith("Your login details") && /[가-힣]/.test(loginError.original ?? "") && loginError.lang === "ko" && loginError.size < 15 && loginError.color === "rgb(92, 99, 112)",
    JSON.stringify(loginError),
  );
  await screenshot(`i18n-${W}-en-login-error.png`);

  // ---------- 중국어 ----------
  await goto("/static/index.html?lang=zh-CN", homeReady);
  l = await layout();
  check("?lang=zh-CN: 탭 중국어", l.lang === "zh-CN" && l.tabs.map((t) => t.text).join("|") === "首页|发布|私信|我的", l.tabs.map((t) => t.text).join("|"));
  check("zh-CN: 탭 이름이 칸 안 한 줄, 헤더 안 넘침", l.tabs.every((t) => t.fits) && l.header && !l.wide);
  check("zh-CN: 가격 '원' 유지", (await texts(".post-card__price")).includes("15,000원"));
  await screenshot(`i18n-${W}-zh-home.png`);

  // ---------- 로그인한 화면 (영어) ----------
  await evaluate(`localStorage.setItem("${TOKEN_KEY}", ${JSON.stringify(seed.seller_token)})`);
  await goto("/static/index.html?lang=en", `${homeReady} && !!document.getElementById('nav-alerts')`);
  await waitUntil("document.getElementById('tab-messages').getAttribute('aria-label')");
  const aria = await evaluate("({ bell: document.getElementById('nav-alerts').getAttribute('aria-label'), tab: document.getElementById('tab-messages').getAttribute('aria-label') })");
  check("en 로그인: 알림 종·쪽지 탭 이름(복수형)", aria.bell.startsWith("Book alerts") && /^Messages(, \d+ unread messages?)?$/.test(aria.tab), JSON.stringify(aria));
  l = await layout();
  check("en 로그인: 헤더 안 넘침, 가로 스크롤 없음", l.header && !l.wide);

  // 내 정보: 가입일 형식, 언어 칸은 숨김(플래그 꺼짐), 본인 확인 질문 저장 때 비밀번호 틀림은 칸 아래에 번역 문구
  const meReady = `${settled} && !document.getElementById('account').hidden`;
  const wrongPassword = async () => {
    await evaluate(`(() => {
      document.getElementById('question-toggle').click();
      const f = document.getElementById('question-form');
      const select = f.elements.question_key;
      select.value = [...select.options].find((o) => o.value && o.value !== 'CUSTOM')?.value ?? select.options[1].value;
      select.dispatchEvent(new Event('change', { bubbles: true }));
      f.elements.answer.value = '확인용 답';
      f.elements.password.value = 'not-my-password-1';
      f.requestSubmit();
    })()`);
    await waitUntil("!document.querySelector('#question-form [data-error-for=password]').hidden");
    return evaluate("(() => { const n = document.querySelector('#question-form [data-error-for=password]'); return { text: n.textContent, original: !!n.querySelector('.error-original') }; })()");
  };
  await goto("/static/me.html", meReady);
  const meta = await evaluate("document.getElementById('profile-meta').textContent");
  check("en 내 정보: 가입일이 영어 날짜 형식", /· [A-Z][a-z]{2} \d{1,2}, \d{4} /.test(meta), meta);
  check("en 내 정보: 언어 칸 숨김(플래그 꺼짐)", await evaluate("document.getElementById('language').hidden"));
  let pw = await wrongPassword();
  check("en 질문 저장 + 틀린 비밀번호: 비밀번호 칸 아래에 번역 문구", pw.text === "Your current password is incorrect." && !pw.original, JSON.stringify(pw));
  await goto("/static/me.html?lang=ko", meReady);
  pw = await wrongPassword();
  check("ko 질문 저장 + 틀린 비밀번호: 예전 문구 그대로", pw.text === "현재 비밀번호가 올바르지 않습니다.", JSON.stringify(pw));
  check("ko 내 정보: 가입일 예전 형식", /· \d{4}\.\d{2}\.\d{2} 가입$/.test(await evaluate("document.getElementById('profile-meta').textContent")));

  // ---------- 기능 플래그를 켰을 때 (lang-boot.js를 바꿔 받아 확인. 저장소의 파일은 그대로) ----------
  await send("Network.enable");
  await send("Network.setBypassServiceWorker", { bypass: true });
  // 요청 단계에서 가로채 저장소의 파일을 플래그만 바꿔 돌려준다. (응답 단계는 304 재확인 때 본문이 비어 있다)
  const flaggedBoot = readFileSync(join(ROOT, "static", "js", "lang-boot.js"), "utf8").replace(
    "var LANG_SWITCH_ENABLED = false;",
    "var LANG_SWITCH_ENABLED = true;",
  );
  await send("Fetch.enable", { patterns: [{ urlPattern: "*/static/js/lang-boot.js*", requestStage: "Request" }] });
  listeners.push((msg) => {
    if (msg.method !== "Fetch.requestPaused") return;
    send("Fetch.fulfillRequest", {
      requestId: msg.params.requestId,
      responseCode: 200,
      responseHeaders: [
        { name: "Content-Type", value: "text/javascript; charset=utf-8" },
        { name: "Cache-Control", value: "no-store" },
      ],
      body: Buffer.from(flaggedBoot, "utf8").toString("base64"),
    });
  });
  // 브라우저 언어(navigator.languages)를 페이지 스크립트보다 먼저 바꿔 둔다. 다시 부르면 앞의 것을 지운다.
  let languageScript = null;
  const browserLanguage = async (languages) => {
    if (languageScript) await send("Page.removeScriptToEvaluateOnNewDocument", { identifier: languageScript });
    const list = JSON.stringify(languages);
    ({ identifier: languageScript } = await send("Page.addScriptToEvaluateOnNewDocument", {
      source: `Object.defineProperty(navigator, "languages", { get: () => ${list} }); Object.defineProperty(navigator, "language", { get: () => ${list}[0] });`,
    }));
  };

  // 처음 방문(저장된 값 없음): 브라우저 언어를 따르고, 지원하지 않으면 한국어
  await evaluate(`localStorage.removeItem("${LANG_KEY}")`);
  await browserLanguage(["en-US", "en"]);
  await goto("/static/index.html", homeReady);
  const first = await evaluate(`({ lang: document.documentElement.lang, button: !!document.querySelector('.site-lang'), languages: navigator.languages.join(','), stored: localStorage.getItem("${LANG_KEY}") })`);
  check("플래그 켬 + 브라우저 영어: 영어로 시작", first.lang === "en" && first.button, JSON.stringify(first));
  await browserLanguage(["ja-JP", "ja"]);
  await goto("/static/index.html", homeReady);
  check("플래그 켬 + 브라우저 일본어(미지원): 한국어", (await evaluate("document.documentElement.lang")) === "ko");

  // 헤더 🌐 버튼: 44px, 펼친 목록 3개 각 44px, 화면 안
  const globe = await evaluate("(() => { const r = document.querySelector('.site-lang').getBoundingClientRect(); return { w: r.width, h: r.height, label: document.querySelector('.site-lang').getAttribute('aria-label') }; })()");
  check("🌐 버튼 44px 이상, 이름 있음", globe.w >= 44 && globe.h >= 44 && globe.label.includes("Language"), JSON.stringify(globe));
  await evaluate("document.querySelector('.site-lang').click()");
  await sleep(150);
  const menu = await evaluate(`(() => {
    const items = [...document.querySelectorAll('.lang-menu__item')].map((n) => { const r = n.getBoundingClientRect(); return { text: n.textContent, h: r.height, inside: r.left >= 0 && r.right <= ${W} }; });
    return { open: !document.querySelector('.lang-menu').hidden, expanded: document.querySelector('.site-lang').getAttribute('aria-expanded'), current: document.querySelector('.lang-menu [aria-current]')?.textContent, items };
  })()`);
  check(
    "🌐 목록: 3개 언어, 각 44px, 화면 안, 지금 언어 표시",
    menu.open && menu.expanded === "true" && menu.items.map((i) => i.text).join("|") === "한국어|English|简体中文" && menu.items.every((i) => i.h >= 44 && i.inside) && menu.current === "한국어",
    JSON.stringify(menu),
  );
  l = await layout();
  check("🌐 버튼이 있어도 헤더 안 넘침", l.header && !l.wide);
  await screenshot(`i18n-${W}-lang-menu.png`);
  await evaluate("document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); document.querySelector('.site-lang').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))");
  check("Esc로 닫힘", await evaluate("document.querySelector('.lang-menu').hidden"));
  await evaluate("document.querySelector('.site-lang').click()");
  await evaluate("[...document.querySelectorAll('.lang-menu__item')].find((n) => n.textContent === '简体中文').click()");
  await sleep(300);
  await waitUntil(`document.documentElement.lang === 'zh-CN' && ${homeReady}`);
  check("简体中文 고르면 다시 불러와 중국어 + 저장", (await evaluate("document.documentElement.lang")) === "zh-CN" && (await evaluate(`localStorage.getItem("${LANG_KEY}")`)) === "zh-CN");

  // 내 정보의 언어 칸
  await goto("/static/me.html", meReady);
  const options = await evaluate(`(() => {
    const s = document.getElementById('language');
    return { shown: !s.hidden, title: s.querySelector('h2').textContent, items: [...s.querySelectorAll('.lang-options__item')].map((n) => ({ text: n.textContent, h: n.getBoundingClientRect().height, right: n.getBoundingClientRect().right })) };
  })()`);
  check(
    "내 정보 언어 칸: 보임, 제목 번역, 버튼 3개 44px·화면 안",
    options.shown && options.title === "语言" && options.items.length === 3 && options.items.every((i) => i.h >= 44 && i.right <= W),
    JSON.stringify(options),
  );
  await evaluate("document.getElementById('language').scrollIntoView()");
  await screenshot(`i18n-${W}-me-language.png`);
  await evaluate("[...document.querySelectorAll('.lang-options__item')].find((n) => n.textContent === 'English').click()");
  await sleep(300);
  await waitUntil(`document.documentElement.lang === 'en' && ${meReady}`);
  check("내 정보에서 English 고르면 영어", (await evaluate("document.documentElement.lang")) === "en" && (await evaluate("document.getElementById('language-title').textContent")) === "Language");

  // 일부러 낸 401·400 응답은 콘솔에 "Failed to load resource"로 남으므로 빼고 본다.
  const errors = exceptions.filter((text) => !/^Failed to load resource: the server responded with a status of 40[01]/.test(text ?? ""));
  check("자바스크립트 오류 없음", errors.length === 0, errors.join(" / "));
} catch (error) {
  results.push(`ERROR ${error.stack}`);
} finally {
  writeFileSync(join(OUT, "i18n-check.txt"), results.join("\n") + "\n");
  console.log(results.join("\n"));
  b.close();
}
