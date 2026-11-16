// 화면 언어 확인 (375px): 한국어 기본, ?lang=·저장된 값으로 바꾸기, 영어·중국어 탭 이름과 헤더가 넘치지 않는지,
// 서버 오류의 번역 문장 + 한국어 원문, 내 정보의 비밀번호 틀림 표시,
// 언어 선택 공개 후: 로그인 전·후·로그인 화면의 🌐 버튼, 브라우저 언어 따르기, 언어를 바꾸면 저장·다시 불러오기.
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { api, readSeed, sleep, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const seed = readSeed(OUT);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  [${W}] ${name}${detail ? `  (${detail})` : ""}`);

const b = await startBrowser(OUT, { width: W, height: 812, mobile: true });
const { evaluate, waitUntil, goto, screenshot, send, exceptions } = b;
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
const globeSize = () =>
  evaluate("(() => { const n = document.querySelector('.site-lang'); if (!n) return null; const r = n.getBoundingClientRect(); return { w: r.width, h: r.height, inside: r.left >= 0 && r.right <= innerWidth }; })()");
const globeOk = (g) => !!g && g.w >= 44 && g.h >= 44 && g.inside;
const texts = (selector) => evaluate(`[...document.querySelectorAll(${JSON.stringify(selector)})].map((n) => n.textContent.trim())`);

try {
  // ---------- 한국어 기본 ----------
  await goto("/static/index.html");
  await evaluate("localStorage.clear()");
  await goto("/static/index.html", homeReady);
  let l = await layout();
  check("기본: <html lang=ko>, 탭 4칸 한국어", l.lang === "ko" && l.tabs.map((t) => t.text).join("|") === "홈|글쓰기|쪽지|내 정보", l.tabs.map((t) => t.text).join("|"));
  // 확인용 브라우저 언어는 ko-KR(lib.mjs)이라 저장된 값이 없으면 한국어로 시작한다.
  let g = await globeSize();
  check("로그인 전: 🌐 버튼 보임, 44px 이상, 화면 안", globeOk(g), JSON.stringify(g));
  check("로그인 전: 🌐 버튼이 있어도 하단 탭 4칸·한 줄·헤더 안 넘침", l.tabs.length === 4 && l.tabs.every((t) => t.fits) && l.header && !l.wide, JSON.stringify(l.tabs));
  await goto("/static/login.html", "!document.documentElement.hasAttribute('data-i18n-pending') && !!document.querySelector('.site-lang')");
  g = await globeSize();
  l = await layout();
  check("로그인 화면: 🌐 버튼 보임, 44px 이상, 헤더 안 넘침", globeOk(g) && l.header && !l.wide, JSON.stringify(g));
  await goto("/static/index.html", homeReady);
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
    "en 로그인 실패: 로그인 화면용 번역 문장 + 한국어 원문(lang=ko, 작은 회색)",
    loginError.main === "Incorrect email or password." && /[가-힣]/.test(loginError.original ?? "") && loginError.lang === "ko" && loginError.size < 15 && loginError.color === "rgb(92, 99, 112)",
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

  // ---------- 2단계: 로그인 전 화면 (목록·로그인·가입·재설정·설치 안내) ----------
  // 로그인·가입·재설정 화면은 하단 탭 바가 없으므로 탭 바를 기다리지 않는다.
  const pageReady = "!document.documentElement.hasAttribute('data-i18n-pending') && document.fonts.status === 'loaded' && !!document.querySelector('.site-nav a')";
  // 화면 밖(375px 오른쪽)으로 나간 요소와 가로 스크롤. 숨긴 요소는 크기가 0이라 빠진다.
  const overflow = () =>
    evaluate(`(() => {
      const bad = [...document.querySelectorAll('main *, .site-header *')].filter((n) => {
        const r = n.getBoundingClientRect();
        return r.width > 0 && (r.right > ${W} + 0.5 || r.left < -0.5);
      }).map((n) => n.tagName + '.' + n.className + ' ' + (n.textContent || '').trim().slice(0, 24));
      const sw = document.documentElement.scrollWidth;
      return { ok: bad.length === 0 && sw <= ${W}, bad: bad.slice(0, 4).join(' / ') + (sw > ${W} ? ' scrollWidth=' + sw : '') };
    })()`);
  const text = (selector) => evaluate(`document.querySelector(${JSON.stringify(selector)})?.textContent.trim()`);
  const attr = (selector, name) => evaluate(`document.querySelector(${JSON.stringify(selector)})?.getAttribute(${JSON.stringify(name)})`);
  const submitForm = (id, values) =>
    evaluate(`(() => {
      const f = document.getElementById(${JSON.stringify(id)});
      for (const [k, v] of Object.entries(${JSON.stringify(values)})) f.elements.namedItem(k).value = v;
      f.requestSubmit();
    })()`);

  for (const lang of ["en", "zh-CN"]) {
    const en = lang === "en";
    // 목록 (비로그인): 제목, 검색 한 줄, 필터 펼침, 결과 수, 빈 결과
    await goto(`/static/index.html?lang=${lang}`, homeReady);
    const home = await evaluate(`({
      title: document.title,
      h1: document.querySelector('h1').textContent,
      toggle: document.querySelector('#filter-toggle span:not(.count-badge)').textContent,
      placeholder: document.getElementById('q').placeholder,
      search: document.getElementById('search-button').getAttribute('aria-label'),
      summary: document.getElementById('result-summary').textContent,
      // 검색창 안내 문구가 잘리지 않고 칸 안에 다 보이는지 (글자 폭을 직접 잰다)
      placeholderFits: (() => {
        const i = document.getElementById('q'), cs = getComputedStyle(i), c = document.createElement('canvas').getContext('2d');
        c.font = cs.font;
        return c.measureText(i.placeholder).width <= i.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
      })(),
      oneRow: (() => { const rs = [...document.querySelector('.filter-form__search-row').children].map((c) => c.getBoundingClientRect().top); return Math.max(...rs) - Math.min(...rs) < 2; })(),
    })`);
    const homeOk = en
      ? home.title === "Textbooks | Campus Books" && home.h1 === "Used textbooks" &&
        home.toggle === "Filter" && home.placeholder === "Find books" && home.search === "Search" && home.summary === "3 posts"
      : home.title === "教材列表 | Campus Books" && home.toggle === "筛选" && home.summary === "共 3 条";
    check(`${lang} 목록: 제목·검색·결과 수, 검색 안내 문구가 칸 안에 다 보임`, homeOk && home.oneRow && home.placeholderFits, JSON.stringify(home));
    await evaluate("document.getElementById('filter-toggle').click()");
    await sleep(200);
    const filters = await evaluate(`({
      status: document.querySelector('label[for=status]').textContent,
      options: [...document.getElementById('status').options].map((o) => o.textContent).join('|'),
      course: document.querySelector('label[for=course_name]').textContent,
      buttons: [...document.querySelectorAll('#filter-more .form-actions button')].map((b) => b.textContent).join('|'),
    })`);
    const filtersOk = en
      ? filters.status === "Status" && filters.options === "All|For sale|Reserved|Sold" && filters.course === "Course (exact match)" && filters.buttons === "Search|Reset"
      : filters.options === "全部|在售|已预订|已售出" && filters.buttons === "搜索|重置";
    let o = await overflow();
    check(`${lang} 목록: 필터 펼침 문구, 화면 안 넘침`, filtersOk && o.ok, `${JSON.stringify(filters)} ${o.bad}`);
    await screenshot(`i18n-${W}-${lang}-home-filter.png`);
    await submitForm("filter-form", { status: "ON_SALE" });
    await waitUntil("document.querySelectorAll('.post-card').length > 0");
    check(`${lang} 목록: 필터 개수 aria`, (await attr("#filter-toggle", "aria-label")) === (en ? "Filter, 1 applied" : "筛选，已应用 1 项"));
    await submitForm("filter-form", { status: "", q: "없는책-zzz" });
    await waitUntil("!!document.querySelector('.empty-state__image')");
    check(`${lang} 목록: 빈 검색 결과`, (await text("#result-summary")) === (en ? "No posts match your search." : "没有符合条件的帖子。"));

    // 로그인: 문구, 가입 직후 안내
    await goto(`/static/login.html?joined=1&lang=${lang}`, pageReady);
    const login = await evaluate(`({
      title: document.title,
      labels: [...document.querySelectorAll('#login-form label')].map((n) => n.textContent).join('|'),
      submit: document.querySelector('#login-form [type=submit]').textContent,
      forgot: document.getElementById('reset-link').textContent,
      switchText: document.querySelector('.auth-switch:not(.auth-switch--forgot)').textContent.replace(/\\s+/g, ' ').trim(),
      notice: document.getElementById('login-notice').textContent,
    })`);
    const loginOk = en
      ? login.title === "Log in | Campus Books" && login.labels === "Email|Password" && login.submit === "Log in" && login.forgot === "Forgot your password?" &&
        login.switchText === "Don't have an account? Sign up" && login.notice === "You're signed up. Please log in."
      : login.labels === "电子邮箱|密码" && login.submit === "登录" && login.notice === "注册成功，请登录。";
    o = await overflow();
    check(`${lang} 로그인: 문구·안내, 화면 안 넘침`, loginOk && o.ok, `${JSON.stringify(login)} ${o.bad}`);

    // 가입: 질문 목록(영문 키로 번역), 질문 안 고르면 안내, 긴 질문이 들어간 선택 칸이 넘치지 않는지
    await goto(`/static/signup.html?lang=${lang}`, `${pageReady} && !!document.getElementById('signup-question')`);
    await submitForm("signup-form", { email: "new@uicheck.ac.kr", password: "check-password-1", password_confirm: "check-password-1", nickname: "새사람" });
    await waitUntil("!document.querySelector('[data-error-for=question_key]').hidden");
    const signup = await evaluate(`({
      legend: document.querySelector('legend').textContent,
      first: document.getElementById('signup-question').options[1].textContent,
      value: document.getElementById('signup-question').options[1].value,
      error: document.querySelector('[data-error-for=question_key]').textContent,
      hint: document.getElementById('password-hint').textContent,
    })`);
    const signupOk = en
      ? signup.legend === "If you forget your password" && signup.first.startsWith("What was the name of a shop") && signup.error === "Please choose a question." && signup.hint === "8–64 characters"
      : signup.legend === "忘记密码时" && signup.first.startsWith("小时候") && signup.error === "请选择一个问题。";
    o = await overflow();
    check(`${lang} 가입: 질문 목록·안내 번역, 값은 영문 키, 화면 안 넘침`, signupOk && signup.value === "CHILDHOOD_SHOP" && o.ok, `${JSON.stringify(signup)} ${o.bad}`);
    await screenshot(`i18n-${W}-${lang}-signup.png`);

    // 재설정: 질문 문장은 서버 원문 그대로, 틀린 답은 번역 문장 + 원문(남은 횟수)
    await goto(`/static/reset-password.html?lang=${lang}`, pageReady);
    await submitForm("question-form", { email: "seller@uicheck.ac.kr" });
    await waitUntil("!document.getElementById('verify-form').hidden");
    await submitForm("verify-form", { answer: "틀린 답입니다" });
    await waitUntil("!document.querySelector('#verify-form [data-error-for=answer]').hidden");
    const reset = await evaluate(`(() => {
      const slot = document.querySelector('#verify-form [data-error-for=answer]');
      return {
        title: document.title,
        question: document.getElementById('reset-question').textContent,
        label: document.querySelector('.reset-question__label').textContent,
        main: slot.firstChild.textContent,
        original: slot.querySelector('.error-original')?.textContent,
        button: document.getElementById('verify-button').textContent,
      };
    })()`);
    const resetOk = en
      ? reset.title === "Reset password | Campus Books" && reset.label === "Security question" && reset.main === "The email or answer is incorrect." && reset.button === "Verify"
      : reset.label === "安全问题" && reset.main === "电子邮箱或答案不正确。" && reset.button === "验证";
    o = await overflow();
    check(
      `${lang} 재설정: 서버 질문은 한국어 원문, 틀린 답은 번역 + 원문(남은 횟수), 화면 안 넘침`,
      resetOk && /[가-힣]/.test(reset.question) && /남은 시도/.test(reset.original ?? "") && o.ok,
      `${JSON.stringify(reset)} ${o.bad}`,
    );
    await screenshot(`i18n-${W}-${lang}-reset.png`);
  }

  // 설치 안내(아이폰 Safari에서만 보임): 문장 가운데 공유 아이콘이 그대로 들어가는지
  const { userAgent: defaultUa } = await send("Browser.getVersion");
  await send("Emulation.setUserAgentOverride", {
    userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    platform: "",
  });
  await evaluate("localStorage.removeItem('campus-books.install-guide-dismissed')");
  await goto("/static/index.html?lang=en", `${homeReady} && !!document.querySelector('.install-guide')`);
  const guide = await evaluate(`(() => {
    const g = document.querySelector('.install-guide'), p = g.querySelector('.install-guide__text');
    return { title: g.querySelector('.install-guide__title').textContent, text: p.textContent, iconInside: !!p.querySelector('svg.icon--share'), close: g.querySelector('.install-guide__close').getAttribute('aria-label'), aria: g.getAttribute('aria-label') };
  })()`);
  const o = await overflow();
  check(
    "en 설치 안내: 문장 가운데 공유 아이콘, 닫기 이름, 화면 안",
    guide.text === "Tap Share at the bottom of Safari, then 'Add to Home Screen'." && guide.iconInside && guide.close === "Close the Add to Home Screen tip" && guide.aria === "Add to Home Screen" && o.ok,
    `${JSON.stringify(guide)} ${o.bad}`,
  );
  await screenshot(`i18n-${W}-en-install-guide.png`);
  await send("Emulation.setUserAgentOverride", { userAgent: defaultUa, platform: "" });

  // ---------- 로그인한 화면 (영어) ----------
  await evaluate(`localStorage.setItem("${TOKEN_KEY}", ${JSON.stringify(seed.seller_token)})`);
  await goto("/static/index.html?lang=en", `${homeReady} && !!document.getElementById('nav-alerts')`);
  await waitUntil("document.getElementById('tab-messages').getAttribute('aria-label')");
  const aria = await evaluate("({ bell: document.getElementById('nav-alerts').getAttribute('aria-label'), tab: document.getElementById('tab-messages').getAttribute('aria-label') })");
  check("en 로그인: 알림 종(Notifications)·쪽지 탭 이름(복수형)", aria.bell.startsWith("Notifications") && /^Messages(, \d+ unread messages?)?$/.test(aria.tab), JSON.stringify(aria));
  l = await layout();
  check("en 로그인: 헤더 안 넘침, 가로 스크롤 없음", l.header && !l.wide);
  g = await globeSize();
  check("en 로그인: 🌐 버튼 보임, 44px 이상, 하단 탭 4칸", globeOk(g) && l.tabs.length === 4 && l.tabs.every((t) => t.fits), `${JSON.stringify(g)} ${l.tabs.map((t) => t.text).join("|")}`);

  // 내 정보: 가입일 형식, 언어 칸 보임, 본인 확인 질문 저장 때 비밀번호 틀림은 칸 아래에 번역 문구
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
  check("en 내 정보: 가입일이 영어 날짜 형식", /· Joined [A-Z][a-z]{2} \d{1,2}, \d{4}$/.test(meta), meta);
  check("en 내 정보: 언어 칸 보임", !(await evaluate("document.getElementById('language').hidden")));
  let pw = await wrongPassword();
  check("en 질문 저장 + 틀린 비밀번호: 비밀번호 칸 아래에 번역 문구", pw.text === "Your current password is incorrect." && !pw.original, JSON.stringify(pw));
  await goto("/static/me.html?lang=ko", meReady);
  pw = await wrongPassword();
  check("ko 질문 저장 + 틀린 비밀번호: 예전 문구 그대로", pw.text === "현재 비밀번호가 올바르지 않습니다.", JSON.stringify(pw));
  check("ko 내 정보: 가입일 예전 형식", /· \d{4}\.\d{2}\.\d{2} 가입$/.test(await evaluate("document.getElementById('profile-meta').textContent")));

  // ---------- 3단계: 거래 화면 (상세·작성·프로필·신고 창·구매자 고르기) ----------
  // 한국어 검색창 안내 문구도 375px에서 칸 안에 다 보여야 한다.
  await goto("/static/index.html?lang=ko", homeReady);
  const koSearch = await evaluate(`(() => {
    const i = document.getElementById('q'), cs = getComputedStyle(i), c = document.createElement('canvas').getContext('2d');
    c.font = cs.font;
    return { placeholder: i.placeholder, text: c.measureText(i.placeholder).width, room: i.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) };
  })()`);
  check("ko 목록: 검색 안내 문구가 칸 안에 다 보임", koSearch.text <= koSearch.room, JSON.stringify(koSearch));

  // 남은 한국어: 사용자가 쓴 글·교재 제목·닉네임·후기·서버 원문 자리를 빼고 한글이 보이면 번역이 빠진 것이다.
  const USER_TEXT = ".post-detail__title, .post-detail__description, .post-detail__info dd, .report-dialog__target, .profile__name, .post-card, .review, .error-original, .site-header, .tab-bar";
  const leftoverKorean = () =>
    evaluate(`(() => {
      const out = [];
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        const p = n.parentElement;
        // 가격 단위 "원"은 모든 언어에서 그대로 쓴다. 구매자 고르기 창의 닉네임(값이 숫자인 칸)도 사용자 글이다.
        const nickname = p.closest('label')?.querySelector('input[name=buyer]:not([value=none])');
        if (!/[가-힣]/.test(n.textContent.replace(/원/g, '')) || !p || nickname || p.closest(${JSON.stringify(USER_TEXT)}) || p.closest('[hidden]') || p.closest('script')) continue;
        out.push(n.textContent.trim().slice(0, 30));
      }
      return out;
    })()`);
  const detailReady = `${settled} && !document.getElementById('post-detail').hidden`;
  for (const lang of ["en", "zh-CN"]) {
    const en = lang === "en";
    // 남의 글 (판매자로 로그인해 구매자의 글을 본다): 정보 칸 이름, 연락·신고·차단 버튼
    await goto(`/static/post.html?id=${seed.p3}&lang=${lang}`, detailReady);
    let left = await leftoverKorean();
    let o = await overflow();
    const dts = await texts(".post-detail__info dt");
    check(`${lang} 상세(남의 글): 정보 칸·버튼 번역, 한국어 안 남음, 화면 안 넘침`, left.length === 0 && o.ok && dts[0] === (en ? "Textbook title" : "教材名称"), `${dts.join("|")} ${left.join(" / ")} ${o.bad}`);
    await screenshot(`i18n-${W}-${lang}-post.png`);
    // 신고 창: 사유는 영문 값, 이름은 번역
    await evaluate("[...document.querySelectorAll('.post-detail__safety .link-button')][0].click()");
    await waitUntil("!!document.querySelector('.report-dialog[open]')");
    const report = await evaluate(`({
      legend: document.querySelector('.report-dialog legend').textContent,
      values: [...document.querySelectorAll('.report-dialog input[name=reason]')].map((n) => n.value).join(','),
      first: document.querySelector('.report-dialog__reason span').textContent,
    })`);
    left = await leftoverKorean();
    o = await overflow();
    check(
      `${lang} 신고 창: 사유 번역(값은 영문), 한국어 안 남음`,
      report.legend === (en ? "Reason" : "举报原因") && report.values === "SPAM,FRAUD,ABUSE,INAPPROPRIATE,OTHER" && report.first === (en ? "Spam or flooding" : "广告·刷屏") && left.length === 0,
      `${JSON.stringify(report)} ${left.join(" / ")}`,
    );
    await screenshot(`i18n-${W}-${lang}-report.png`);
    await evaluate("document.querySelector('.report-dialog[open]').close()");

    // 내 글: 관리 버튼, 판매 완료 창(구매자 고르기)
    await goto(`/static/post.html?id=${seed.p1}&lang=${lang}`, `${detailReady} && !document.getElementById('owner-panel').hidden`);
    left = await leftoverKorean();
    o = await overflow();
    const owner = await texts("#owner-actions button, #owner-actions a");
    check(`${lang} 상세(내 글): 관리 버튼 번역, 한국어 안 남음, 화면 안 넘침`, left.length === 0 && o.ok && owner.includes(en ? "Mark as sold" : "改为已售出"), `${owner.join("|")} ${left.join(" / ")} ${o.bad}`);
    await evaluate(`[...document.querySelectorAll('#owner-actions button')].find((n) => n.textContent === ${JSON.stringify(en ? "Mark as sold" : "改为已售出")}).click()`);
    await waitUntil("!!document.querySelector('.report-dialog[open]')");
    left = await leftoverKorean();
    const buyer = await text(".report-dialog legend");
    check(`${lang} 판매 완료 창: 구매자 고르기 번역`, buyer === (en ? "Trade partner" : "交易对象") && left.length === 0, `${buyer} ${left.join(" / ")}`);
    await evaluate("document.querySelector('.report-dialog[open]').close()");

    // 없는 글: 상태 코드별 번역 문장 + 한국어 원문
    await goto(`/static/post.html?id=999999&lang=${lang}`, `${settled} && !document.getElementById('page-error').hidden`);
    const missing = await evaluate("(() => { const n = document.getElementById('page-error-text'); return { text: n.firstChild?.textContent, original: n.querySelector('.error-original')?.textContent }; })()");
    check(`${lang} 없는 글: 번역 문장 + 한국어 원문`, !!missing.original && !/[가-힣]/.test(missing.text ?? "가"), JSON.stringify(missing));

    // 수정 화면 (내 글)
    await goto(`/static/post-form.html?id=${seed.p1}&lang=${lang}`, `${settled} && !document.getElementById('form-card').hidden`);
    left = await leftoverKorean();
    o = await overflow();
    const formTitle = await text("#form-title");
    check(`${lang} 수정 화면: 칸 이름·안내 번역, 한국어 안 남음, 화면 안 넘침`, formTitle === (en ? "Edit listing" : "编辑帖子") && left.length === 0 && o.ok, `${formTitle} ${left.join(" / ")} ${o.bad}`);
    await screenshot(`i18n-${W}-${lang}-post-form.png`);

    // 프로필: 매너 학점(중국어 礼仪绩点), 판매 중인 글·후기 수
    await goto(`/static/user.html?id=1&lang=${lang}`, `${settled} && !document.getElementById('profile').hidden && document.getElementById('posts-summary').textContent !== ''`);
    left = await leftoverKorean();
    o = await overflow();
    const manner = await text(".manner-gpa__label");
    check(`${lang} 프로필: 매너 학점·목록 번역, 한국어 안 남음, 화면 안 넘침`, manner === (en ? "Manner GPA" : "礼仪绩点") && left.length === 0 && o.ok, `${manner} ${left.join(" / ")} ${o.bad}`);
    await screenshot(`i18n-${W}-${lang}-user.png`);
  }
  await goto(`/static/post.html?id=${seed.p3}&lang=ko`, detailReady);
  const koDts = await texts(".post-detail__info dt");
  check("ko 상세: 정보 칸 예전 문구", koDts[0] === "교재명" && koDts.includes("판매자"), koDts.join("|"));

  // ---------- 4단계: 쪽지·알림·내 정보 (판매자로 로그인한 상태) ----------
  // 사용자가 쓴 값(닉네임·쪽지·글 제목·키워드·이메일)과 서버가 준 문장(본인 확인 질문)은 원문 그대로라 빼고 본다.
  const USER_TEXT_4 = `${USER_TEXT}, .message__bubble, #chat-partner, .chat__post a, .conversation-card__partner, .conversation-card__post, .conversation-card__preview, .action-menu__title, .alert-list__keyword, .block-item__name, #profile-nickname, #question-status, #language, .lang-menu`;
  const leftover4 = () =>
    evaluate(`(() => {
      const out = [];
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        const p = n.parentElement;
        if (!/[가-힣]/.test(n.textContent.replace(/원/g, '')) || !p || p.closest(${JSON.stringify(USER_TEXT_4)}) || p.closest('[hidden]') || p.closest('script')) continue;
        out.push(n.textContent.trim().slice(0, 30));
      }
      return out;
    })()`);
  // 종 알림 판: 판매자에게 긴 키워드의 찾는 교재 알림 하나를 만들어 둔다. (항목이 두 줄을 넘지 않는지 보기 위해)
  await api("POST", "/users/me/alerts", seed.seller_token, { keyword: "Operating System Concepts" });
  for (const lang of ["en", "zh-CN"]) {
    const en = lang === "en";
    // 알림 화면이 모두 읽음 처리하므로 언어마다 새 알림을 하나씩 만든다. (글 제목은 영어: 사용자 입력이 한국어로 남았다고 보지 않게)
    await api("POST", "/posts", seed.buyer_token, { title: `OS textbook ${lang}`, book_title: "Operating System Concepts 10th Edition", condition: "GOOD", price: 9000 });
    // 종 알림 판: 라벨·전체 보기 번역, 한 항목 두 줄 이내, 판이 화면 안
    await goto(`/static/index.html?lang=${lang}`, `${settled} && !!document.getElementById('nav-alerts')`);
    await evaluate("document.getElementById('nav-alerts').click()");
    await waitUntil("!document.getElementById('notification-panel').hidden && document.querySelector('.notification-panel__status').hidden");
    const bell = await evaluate(`(() => {
      const p = document.getElementById('notification-panel'), r = p.getBoundingClientRect();
      const items = [...p.querySelectorAll('.notification-panel__text')];
      return {
        label: p.getAttribute('aria-label'), all: p.querySelector('.notification-panel__all').textContent, inside: r.left >= 0 && r.right <= ${W},
        lines: items.map((s) => Math.round(s.scrollHeight / parseFloat(getComputedStyle(s).lineHeight))), texts: items.map((s) => s.textContent),
        wide: [...p.querySelectorAll('*')].filter((n) => n.getBoundingClientRect().right > r.right + 0.5).length,
      };
    })()`);
    const alertText = en ? "New listing for your book alert “Operating System Concepts”" : "求书提醒“Operating System Concepts”有新的匹配帖子";
    check(
      `${lang} 종 알림 판: 라벨·전체 보기·항목 번역, 한 항목 두 줄 이내, 넘침 없음`,
      bell.label === (en ? "Notifications" : "通知") && bell.all === (en ? "See all" : "查看全部") && bell.texts.includes(alertText) &&
        bell.lines.length > 0 && Math.max(...bell.lines) <= 2 && bell.inside && bell.wide === 0,
      JSON.stringify(bell),
    );
    await screenshot(`i18n-${W}-${lang}-bell.png`);
    await evaluate("document.getElementById('nav-alerts').click()");
    // 쪽지함: 개수(복수형), 역할, 안 읽은 수 낭독 문장, 카드 메뉴
    await goto(`/static/conversations.html?lang=${lang}`, `${settled} && document.querySelectorAll('.conversation-card').length > 0`);
    let left = await leftover4();
    let o = await overflow();
    const inbox = await evaluate(`({
      title: document.title,
      summary: document.getElementById('result-summary').textContent,
      unread: document.querySelector('.count-badge .visually-hidden')?.textContent ?? '',
    })`);
    check(
      `${lang} 쪽지함: 제목·개수·안 읽은 수 번역, 한국어 안 남음, 화면 안 넘침`,
      inbox.title === (en ? "Inbox | Campus Books" : "私信箱 | Campus Books") && inbox.summary === (en ? "3 conversations" : "3 个对话") && left.length === 0 && o.ok,
      `${JSON.stringify(inbox)} ${left.join(" / ")} ${o.bad}`,
    );
    await screenshot(`i18n-${W}-${lang}-conversations.png`);
    await evaluate("document.querySelector('.conversation-menu-button').click()");
    await waitUntil("!!document.querySelector('.action-menu[open]')");
    const menu = await texts(".action-menu[open] .action-menu__item");
    left = await leftover4();
    check(`${lang} 쪽지함 메뉴: 신고·차단·나가기 번역`, menu.includes(en ? "Leave conversation" : "退出对话") && left.length === 0, `${menu.join("|")} ${left.join(" / ")}`);
    await evaluate("document.querySelector('.action-menu[open]').close()");

    // 대화: 역할·안내·입력창·보내기, 문서 제목에 상대 닉네임
    await goto(`/static/chat.html?id=${seed.c1}&lang=${lang}`, `${settled} && !document.getElementById('chat').hidden`);
    left = await leftover4();
    o = await overflow();
    const chatInfo = await evaluate(`({
      title: document.title,
      role: document.querySelector('.chat__role')?.textContent,
      placeholder: document.getElementById('content').placeholder,
      send: document.querySelector('#message-form [type=submit]').textContent,
      photo: document.getElementById('photo-button').getAttribute('aria-label'),
      more: document.querySelector('#chat-actions .chat__more').getAttribute('aria-label'),
    })`);
    await evaluate("document.querySelector('#chat-actions .chat__more').click()");
    await waitUntil("document.querySelector('dialog.action-menu')?.open");
    chatInfo.menu = await evaluate("[...document.querySelectorAll('dialog.action-menu .action-menu__item')].map((b) => b.textContent).join('|')");
    await evaluate("document.querySelector('.action-menu[open]').close()");
    check(
      `${lang} 대화: 역할·입력창·버튼·사진 추가·더보기·⋯ 메뉴 번역, 한국어 안 남음, 화면 안 넘침`,
      chatInfo.title.includes("구매자지은") && chatInfo.role === (en ? "Inquiry about your listing" : "对我帖子的咨询") && chatInfo.send === (en ? "Send" : "发送") &&
        chatInfo.photo === (en ? "Add photo" : "添加照片") && chatInfo.more === (en ? "More" : "更多") && chatInfo.menu === (en ? "Report|Block|Cancel" : "举报|屏蔽|取消") && left.length === 0 && o.ok,
      `${JSON.stringify(chatInfo)} ${left.join(" / ")} ${o.bad}`,
    );
    await screenshot(`i18n-${W}-${lang}-chat.png`);

    // 없는 대화방: 번역 문장 + 한국어 원문
    await goto(`/static/chat.html?id=999999&lang=${lang}`, `${settled} && !document.getElementById('page-error').hidden`);
    const noRoom = await evaluate("(() => { const n = document.getElementById('page-error-text'); return { text: n.firstChild?.textContent, original: n.querySelector('.error-original')?.textContent }; })()");
    check(`${lang} 없는 대화방: 번역 문장 + 한국어 원문`, !!noRoom.original && !/[가-힣]/.test(noRoom.text ?? "가"), JSON.stringify(noRoom));

    // 알림 화면: 제목·안 읽은 쪽지 줄·빈 화면 버튼 번역, 넘침 없음
    await goto(`/static/alerts.html?lang=${lang}`, `${settled} && !document.getElementById('unread-messages').hidden && document.getElementById('result-summary').textContent !== ${JSON.stringify(en ? "Loading…" : "加载中…")}`);
    left = await leftover4();
    o = await overflow();
    const notif = await evaluate("({ h1: document.querySelector('h1').textContent, h2: document.querySelector('main h2').textContent, row: document.querySelector('#unread-messages a').textContent })");
    check(
      `${lang} 알림 화면: 제목·쪽지 줄·찾는 교재 알림 제목 번역, 한국어 안 남음, 화면 안 넘침`,
      notif.h1 === (en ? "Notifications" : "通知") && notif.h2 === (en ? "Book alerts" : "求书提醒") && (en ? /^\d+ unread messages?$/ : /^\d+ 条未读私信$/).test(notif.row) && left.length === 0 && o.ok,
      `${JSON.stringify(notif)} ${left.join(" / ")} ${o.bad}`,
    );
    await screenshot(`i18n-${W}-${lang}-notifications.png`);

    // 찾는 교재 화면: 조건 등록 → 목록 문구, 같은 키워드 다시 등록 → 칸 아래 맞춤 문장 + 원문
    await goto(`/static/book-alerts.html?lang=${lang}`, `${settled} && document.getElementById('alert-count').textContent !== ''`);
    const keyword = `알림확인${lang}`;
    const addAlert = async () => {
      await evaluate(`(() => { const f = document.getElementById('alert-form'); f.elements.keyword.value = ${JSON.stringify(keyword)}; f.requestSubmit(); })()`);
    };
    await addAlert();
    await waitUntil(`[...document.querySelectorAll('.alert-list__keyword')].some((n) => n.textContent === ${JSON.stringify(keyword)})`);
    await addAlert();
    await waitUntil("!document.querySelector('#alert-form [data-error-for=keyword]').hidden");
    const dup = await evaluate("(() => { const n = document.querySelector('#alert-form [data-error-for=keyword]'); return { text: n.firstChild?.textContent, original: n.querySelector('.error-original')?.textContent }; })()");
    left = await leftover4();
    o = await overflow();
    const alertTexts = await texts(".alert-list__price, .alert-list__actions a");
    check(
      `${lang} 찾는 교재 알림: 조건 줄·빈 알림 번역, 중복은 맞춤 문장 + 원문, 한국어 안 남음`,
      dup.text === (en ? "You've already added this keyword." : "该关键词已添加。") && !!dup.original && alertTexts.includes(en ? "Any price" : "价格不限") && left.length === 0 && o.ok,
      `${JSON.stringify(dup)} ${alertTexts.join("|")} ${left.join(" / ")} ${o.bad}`,
    );
    await screenshot(`i18n-${W}-${lang}-alerts.png`);
    await evaluate(`[...document.querySelectorAll('.alert-list__item')].find((n) => n.textContent.includes(${JSON.stringify(keyword)})).querySelector('.link-button--danger').click()`);
    await waitUntil(`![...document.querySelectorAll('.alert-list__keyword')].some((n) => n.textContent === ${JSON.stringify(keyword)})`);

    // 차단 목록 (비어 있음)
    await goto(`/static/blocks.html?lang=${lang}`, `${settled} && document.getElementById('result-summary').textContent !== ${JSON.stringify(en ? "Loading…" : "加载中…")}`);
    left = await leftover4();
    o = await overflow();
    const blocks = await evaluate("({ h1: document.querySelector('h1').textContent, summary: document.getElementById('result-summary').textContent })");
    check(
      `${lang} 차단 목록: 제목·빈 목록 번역, 한국어 안 남음, 화면 안 넘침`,
      blocks.h1 === (en ? "Blocked users" : "屏蔽列表") && blocks.summary === (en ? "You haven't blocked anyone." : "没有屏蔽的用户。") && left.length === 0 && o.ok,
      `${JSON.stringify(blocks)} ${left.join(" / ")} ${o.bad}`,
    );

    // 내 정보: 계정 버튼·탭·내 글 개수, 펼친 폼(닉네임·비밀번호·탈퇴) 문구
    await goto(`/static/me.html?lang=${lang}`, `${meReady} && document.getElementById('result-summary').textContent !== ${JSON.stringify(en ? "Loading…" : "加载中…")}`);
    left = await leftover4();
    o = await overflow();
    const me4 = await evaluate(`({
      buttons: [...document.querySelectorAll('.settings-row')].filter((n) => n.getClientRects().length).map((n) => n.textContent.trim()).join('|'),
      tabs: [...document.querySelectorAll('#me-tabs a')].map((n) => n.textContent).join('|'),
      summary: document.getElementById('result-summary').textContent,
      manner: document.getElementById('profile-manner').textContent,
    })`);
    check(
      `${lang} 내 정보: 계정 버튼·탭·개수·매너 학점 번역, 한국어 안 남음, 화면 안 넘침`,
      me4.summary === (en ? "2 posts" : "共 2 条") && me4.manner.startsWith(en ? "Manner GPA: " : "礼仪绩点：") && left.length === 0 && o.ok,
      `${JSON.stringify(me4)} ${left.join(" / ")} ${o.bad}`,
    );
    await screenshot(`i18n-${W}-${lang}-me.png`);
    for (const id of ["nickname-toggle", "password-toggle", "language-toggle", "withdraw-toggle"]) {
      await evaluate(`document.getElementById('${id}').click()`);
      left = await leftover4();
      o = await overflow();
      check(`${lang} 내 정보 ${id.replace("-toggle", "")} 폼: 한국어 안 남음, 화면 안 넘침`, left.length === 0 && o.ok, `${left.join(" / ")} ${o.bad}`);
    }
  }
  await goto("/static/conversations.html?lang=ko", `${settled} && document.querySelectorAll('.conversation-card').length > 0`);
  const koInbox = await evaluate("({ summary: document.getElementById('result-summary').textContent, unread: document.querySelector('.count-badge')?.textContent ?? '' })");
  check("ko 쪽지함: 예전 문구", koInbox.summary === "대화방 3개" && (koInbox.unread === "" || /^안 읽은 메시지 \d+개\d+$/.test(koInbox.unread)), JSON.stringify(koInbox));

  // ---------- 브라우저 언어 따르기와 🌐 목록 (언어 선택 공개) ----------
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
  check("저장된 값 없음 + 브라우저 영어: 영어로 시작", first.lang === "en" && first.button, JSON.stringify(first));
  await browserLanguage(["ja-JP", "ja"]);
  await goto("/static/index.html", homeReady);
  check("저장된 값 없음 + 브라우저 일본어(미지원): 한국어", (await evaluate("document.documentElement.lang")) === "ko");

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

  // 내 정보의 언어 행: 오른쪽에 지금 언어, 누르면 언어 버튼 3개가 펼쳐짐
  await goto("/static/me.html", meReady);
  await evaluate("document.getElementById('language-toggle').click()");
  const options = await evaluate(`(() => {
    const s = document.getElementById('language');
    return { shown: !s.hidden, title: document.getElementById('language-title').textContent, current: document.getElementById('language-current').textContent, items: [...s.querySelectorAll('.lang-options__item')].map((n) => ({ text: n.textContent, h: n.getBoundingClientRect().height, right: n.getBoundingClientRect().right })) };
  })()`);
  check(
    "내 정보 언어 행: 보임, 이름 번역, 지금 언어 표시, 펼친 버튼 3개 44px·화면 안",
    options.shown && options.title === "语言" && options.current === "简体中文" && options.items.length === 3 && options.items.every((i) => i.h >= 44 && i.right <= W),
    JSON.stringify(options),
  );
  await evaluate("document.getElementById('language').scrollIntoView()");
  await screenshot(`i18n-${W}-me-language.png`);
  await evaluate("[...document.querySelectorAll('.lang-options__item')].find((n) => n.textContent === 'English').click()");
  await sleep(300);
  await waitUntil(`document.documentElement.lang === 'en' && ${meReady}`);
  check("내 정보에서 English 고르면 영어", (await evaluate("document.documentElement.lang")) === "en" && (await evaluate("document.getElementById('language-title').textContent")) === "Language");

  // 일부러 낸 401·400·404(없는 글·대화방)·409(같은 키워드) 응답은 콘솔에 "Failed to load resource"로 남으므로 빼고 본다.
  const errors = exceptions.filter((text) => !/^Failed to load resource: the server responded with a status of 40[0149]/.test(text ?? ""));
  check("자바스크립트 오류 없음", errors.length === 0, errors.join(" / "));
} catch (error) {
  results.push(`ERROR ${error.stack}`);
} finally {
  writeFileSync(join(OUT, "i18n-check.txt"), results.join("\n") + "\n");
  console.log(results.join("\n"));
  b.close();
}
