// 본인 확인 질문(가입·비밀번호 재설정·내 정보 등록/변경·재설정 안내)을 헤드리스 Chrome으로 확인한다.
// 사용: WIDTH=375 tools/ui-check/run.sh reset-check
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { api, loginApi, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);

const email = "question@uicheck.ac.kr";
const pw = "questionpass123";
const newPw = "questionpass456";
const answer = "해피 마트";

const b = await startBrowser(OUT, { width: W });
const noScroll = () => b.evaluate(`document.documentElement.scrollWidth <= ${W}`);
const text = (sel) => b.evaluate(`document.querySelector(${JSON.stringify(sel)})?.textContent ?? ""`);
const visible = (sel) => b.evaluate(`(() => { const n = document.querySelector(${JSON.stringify(sel)}); return !!n && n.offsetParent !== null; })()`);

try {
  // ---------- 가입: 질문 고르기 ----------
  await b.goto("/static/signup.html", "document.querySelector('#signup-question select')");
  check("가입: 질문 목록 9개 + 직접 만들기", (await b.evaluate("document.querySelectorAll('#signup-question select option').length")) === 11);
  check("가입: 답 안내 문구", (await text("#signup-answer-hint")).includes("남이 쉽게 알 수 없는 답으로 정해 주세요"));
  check("가입: 직접 만들기 칸은 처음에 숨김", !(await visible("#signup-custom-question")));
  check(`${W}px: 가입 가로 스크롤 없음`, await noScroll());
  await b.screenshot(`reset-signup-${W}.png`);

  const fill = `(() => { const f = document.getElementById('signup-form');
    f.email.value = ${JSON.stringify(email)}; f.password.value = ${JSON.stringify(pw)}; f.password_confirm.value = ${JSON.stringify(pw)};
    f.nickname.value = '질문확인'; })()`;
  await b.evaluate(fill);
  // 질문을 고르지 않으면 보내지 않고 칸 아래에 알려준다.
  await b.evaluate("document.getElementById('signup-form').requestSubmit()");
  check("가입: 질문을 안 고르면 칸 아래 안내", (await text("[data-error-for=question_key]")).includes("질문을 골라"));

  // 직접 만들기 → 답이 질문에 들어 있으면 서버(422)가 거절한다.
  await b.evaluate(`(() => { const s = document.querySelector('#signup-question select'); s.value = '__custom'; s.dispatchEvent(new Event('change')); })()`);
  check("가입: 직접 만들기 고르면 질문 칸이 보임", await visible("#signup-custom-question"));
  check("가입: 질문을 고르면 지난 안내가 사라짐", !(await visible("[data-error-for=question_key]")));
  check(`${W}px: 직접 만들기 칸 펼친 뒤 가로 스크롤 없음`, await noScroll());
  await b.screenshot(`reset-signup-custom-${W}.png`);
  await b.evaluate(`(() => { document.getElementById('signup-custom-question').value = '초록이의 이름은 무엇일까?'; document.getElementById('signup-answer').value = '초록이'; document.getElementById('signup-form').requestSubmit(); })()`);
  check("가입: 답이 질문에 들어 있으면 거절 안내", await b.waitUntil(`(document.querySelector('[data-error-for=security_question]').textContent + document.getElementById('signup-error').textContent).includes('질문 안에')`));

  // 준비된 질문으로 가입 → 로그인 화면(joined=1)
  await b.evaluate(`(() => { const s = document.querySelector('#signup-question select'); s.value = 'CHILDHOOD_SHOP'; s.dispatchEvent(new Event('change'));
    document.getElementById('signup-answer').value = ${JSON.stringify(answer)}; document.getElementById('signup-form').requestSubmit(); })()`);
  check("가입: 성공하면 로그인 화면으로", await b.waitUntil("location.pathname === '/static/login.html' && location.search.includes('joined=1')", 8000));

  // ---------- 재설정: 1단계 이메일 → 2단계 질문·답 확인 → 3단계 새 비밀번호 ----------
  await b.goto("/static/reset-password.html", "document.getElementById('question-form')");
  check("재설정: 처음에는 이메일 칸만", (await visible("#question-form")) && !(await visible("#verify-form")) && !(await visible("#reset-form")));
  check(`${W}px: 재설정 1단계 가로 스크롤 없음`, await noScroll());
  await b.screenshot(`reset-step1-${W}.png`);
  await b.evaluate(`(() => { const f = document.getElementById('question-form'); f.email.value = ${JSON.stringify(email.toUpperCase())}; f.requestSubmit(); })()`);
  check("재설정: 가입한 질문이 보임", await b.waitUntil(`document.getElementById('reset-question').textContent === '어릴 때 살던 동네에서 자주 가던 가게 이름은?'`));
  check("재설정: 답 칸과 인증 확인 버튼, 새 비밀번호 칸은 아직 없음", (await visible("#verify-form")) && (await visible("#verify-button")) && !(await visible("#reset-form")));
  check(`${W}px: 재설정 2단계 가로 스크롤 없음`, await noScroll());
  await b.screenshot(`reset-step2-${W}.png`);

  // 틀린 답 → 답 칸 바로 아래에 남은 시도 횟수, 새 비밀번호 칸은 계속 숨김
  await b.evaluate(`(() => { document.getElementById('answer').value = '틀린답'; document.getElementById('verify-form').requestSubmit(); })()`);
  check("재설정: 틀린 답이면 답 칸 아래 안내와 남은 시도", await b.waitUntil(`document.querySelector('#verify-form [data-error-for=answer]').textContent.includes('남은 시도 4번')`));
  check("재설정: 틀린 동안 새 비밀번호 칸 안 보임", !(await visible("#reset-form")));
  check(`${W}px: 오답 안내 뒤 가로 스크롤 없음`, await noScroll());
  await b.screenshot(`reset-wrong-${W}.png`);

  // 맞는 답(띄어쓰기 다르게) → 확인됐어요, 답 칸 잠김, 새 비밀번호 칸 나타남
  await b.evaluate(`(() => { document.getElementById('answer').value = '해피마트'; document.getElementById('verify-form').requestSubmit(); })()`);
  check("재설정: 맞으면 '확인됐어요'", await b.waitUntil("!document.getElementById('verify-ok').hidden"));
  check("재설정: 지난 오답 안내는 사라짐", !(await visible("#verify-form [data-error-for=answer]")));
  check("재설정: 답 칸 잠김·인증 버튼 숨김", await b.evaluate("document.getElementById('answer').readOnly && document.getElementById('verify-button').hidden"));
  check("재설정: 새 비밀번호 칸과 바꾸기 버튼이 나타남", await visible("#reset-form"));
  check(`${W}px: 재설정 3단계 가로 스크롤 없음`, await noScroll());
  await b.screenshot(`reset-step3-${W}.png`);

  // 새 비밀번호 확인이 다르면 칸 아래 안내, 맞으면 로그인 화면(reset=1)
  await b.evaluate(`(() => { const f = document.getElementById('reset-form'); f.new_password.value = ${JSON.stringify(newPw)}; f.new_password_confirm.value = 'different-pass'; f.requestSubmit(); })()`);
  check("재설정: 새 비밀번호 확인 불일치 안내", (await text("#reset-form [data-error-for=new_password_confirm]")).includes("일치하지"));
  await b.evaluate(`(() => { const f = document.getElementById('reset-form'); f.new_password_confirm.value = ${JSON.stringify(newPw)}; f.requestSubmit(); })()`);
  check("재설정: 성공하면 로그인 화면으로", await b.waitUntil("location.pathname === '/static/login.html' && location.search.includes('reset=1')", 8000));
  check("재설정: 새 비밀번호로 로그인", (await loginApi(email, newPw)) !== undefined);

  // 가입하지 않은 이메일에도 질문과 같은 모양의 오답 안내가 나온다. (가입 여부를 알려주지 않음)
  await b.goto("/static/reset-password.html", "document.getElementById('question-form')");
  await b.evaluate(`(() => { const f = document.getElementById('question-form'); f.email.value = 'nobody@uicheck.ac.kr'; f.requestSubmit(); })()`);
  check("재설정: 없는 이메일에도 질문이 보임", await b.waitUntil(`document.getElementById('reset-question').textContent.length > 5`));
  await b.evaluate(`(() => { document.getElementById('answer').value = '아무거나'; document.getElementById('verify-form').requestSubmit(); })()`);
  check("재설정: 없는 이메일도 같은 오답 안내", await b.waitUntil(`document.querySelector('#verify-form [data-error-for=answer]').textContent.includes('남은 시도 4번')`));
  await b.evaluate("document.getElementById('change-email').click()");
  check("재설정: 이메일 바꾸기로 1단계로 돌아감", (await visible("#question-form")) && !(await visible("#verify-form")) && !(await visible("#reset-form")));

  // ---------- 다음 로그인: 재설정 안내 ----------
  const token = await loginApi(email, newPw);
  await b.goto("/static/index.html");
  await b.evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(token)})`);
  await b.goto("/static/me.html", "!document.getElementById('account').hidden");
  check("안내: 재설정 알림이 위쪽에 보임", await b.waitUntil(`document.querySelector('.site-notice--action')?.textContent.includes('비밀번호가 재설정됐어요')`));
  check(`${W}px: 안내가 있어도 가로 스크롤 없음`, await noScroll());
  await b.screenshot(`reset-notice-${W}.png`);
  await b.evaluate("document.querySelector('.site-notice--action button').click()");
  check("안내: 확인을 누르면 사라짐", await b.waitUntil("!document.querySelector('.site-notice--action')"));
  check("안내: 서버에도 확인으로 기록", (await api("GET", "/users/me", token)).body.password_reset_notice === null);

  // ---------- 내 정보: 지금 질문, 7일 제한 ----------
  check("내 정보: 지금 질문을 보여줌", (await text("#question-status")).includes("어릴 때 살던 동네"));
  check("내 정보: 7일 제한 안내", (await text("#question-status")).includes("부터 바꿀 수 있어요"));
  await b.evaluate("document.getElementById('question-toggle').click()");
  check("내 정보: 질문 폼이 펼쳐짐", await visible("#question-form"));
  check(`${W}px: 질문 폼 가로 스크롤 없음`, await noScroll());
  await b.screenshot(`reset-me-form-${W}.png`);
  await b.evaluate(`(() => { const s = document.querySelector('#question-fields select'); s.value = 'SCHOOL_CLUB'; s.dispatchEvent(new Event('change'));
    document.getElementById('me-answer').value = '천체관측반'; document.getElementById('question-password').value = ${JSON.stringify(newPw)};
    document.getElementById('question-form').requestSubmit(); })()`);
  check("내 정보: 7일 안에 바꾸면 공통 영역에 안내", await b.waitUntil(`document.querySelector('#question-form .form-error').textContent.includes('7일')`));

  // ---------- 다른 회원: 직접 만든 질문으로 변경 ----------
  const old = "oldmember@uicheck.ac.kr";
  await api("POST", "/auth/signup", null, { email: old, password: pw, nickname: "예전회원" });
  const oldToken = await loginApi(old, pw);
  await b.evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(oldToken)})`);
  await b.goto("/static/me.html", "!document.getElementById('account').hidden");
  await b.evaluate("document.getElementById('question-toggle').click()");
  await b.evaluate(`(() => { const s = document.querySelector('#question-fields select'); s.value = '__custom'; s.dispatchEvent(new Event('change'));
    document.getElementById('me-custom-question').value = '내가 처음 키운 화분의 이름은?'; document.getElementById('me-answer').value = '초록이';
    document.getElementById('question-password').value = 'wrong-pass'; document.getElementById('question-form').requestSubmit(); })()`);
  check("내 정보: 비밀번호가 틀리면 비밀번호 칸 아래", await b.waitUntil(`document.querySelector('#question-form [data-error-for=password]').textContent.includes('현재 비밀번호')`));
  await b.evaluate(`(() => { document.getElementById('question-password').value = ${JSON.stringify(pw)}; document.getElementById('question-form').requestSubmit(); })()`);
  check("내 정보: 저장하면 완료 안내와 새 질문", await b.waitUntil(`document.getElementById('account-notice').textContent.includes('저장했어요') && document.getElementById('question-status').textContent.includes('화분')`));

  // ---------- 관리자: 질문 버튼·안내 없음 ----------
  await import("./lib.mjs").then(({ makeAdmin }) => makeAdmin(OUT, old));
  await b.goto("/static/me.html", "!document.getElementById('account').hidden");
  check("관리자: 질문 버튼 숨김", await b.evaluate("document.getElementById('question-toggle').hidden"));
  check("관리자: 질문 안내 숨김", await b.evaluate("document.getElementById('question-status').hidden"));

  const jsErrors = b.exceptions.filter((e) => !String(e).startsWith("Failed to load resource"));
  check("JS 에러 없음", jsErrors.length === 0, jsErrors.join(" | "));
} catch (error) {
  results.push(`ERROR  ${error.message}`);
} finally {
  b.close();
  writeFileSync(join(OUT, "reset-check.txt"), results.join("\n") + "\n");
  console.log(results.join("\n"));
}
