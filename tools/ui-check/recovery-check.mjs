// 복구 코드 화면(가입 직후 코드, 비밀번호 재설정, 내 정보에서 재발급)을 헤드리스 Chrome으로 확인한다.
// 사용: WIDTH=375 tools/ui-check/run.sh recovery-check
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { api, loginApi, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);

const email = "recover@uicheck.ac.kr";
const pw = "recoverpass123";
const newPw = "recoverpass456";
const CODE = /^[23456789A-HJKMNP-Z]{4}(-[23456789A-HJKMNP-Z]{4}){3}$/;

const b = await startBrowser(OUT, { width: W });
const dialogs = [];
b.listeners.push((msg) => {
  if (msg.method === "Page.javascriptDialogOpening") {
    dialogs.push(msg.params.type);
    b.send("Page.handleJavaScriptDialog", { accept: true });
  }
});
const noScroll = () => b.evaluate(`document.documentElement.scrollWidth <= ${W}`);
// 눌러야 하는 것들이 44px 이상인지
const smallTargets = (selector) =>
  b.evaluate(`[...document.querySelectorAll(${JSON.stringify(selector)})].filter((e) => e.getClientRects().length).map((e) => e.getBoundingClientRect()).filter((r) => r.height < 43.5).length`);

try {
  // ---------- 가입 직후: 코드 한 번 보여주기 ----------
  await b.goto("/static/signup.html", "document.getElementById('signup-form')");
  await b.evaluate(`(() => { const f = document.getElementById('signup-form');
    f.email.value = ${JSON.stringify(email)}; f.password.value = ${JSON.stringify(pw)}; f.password_confirm.value = ${JSON.stringify(pw)}; f.nickname.value = '복구확인';
    f.requestSubmit(); })()`);
  check("가입: 폼 대신 복구 코드", await b.waitUntil(`!document.getElementById('signup-code').hidden && document.getElementById('signup-form').hidden`));
  const code = await b.evaluate(`document.querySelector('.recovery-code__value').textContent`);
  check("가입: 코드 모양 4-4-4-4", CODE.test(code), code);
  check("가입: 잃어버리면 재설정 불가 안내", await b.evaluate(`document.querySelector('.recovery-code__warning').textContent.includes('잃어버리면 비밀번호를 재설정할 수 없어요')`));
  const continueBtn = "[...document.querySelectorAll('.recovery-code button')].find((x) => x.textContent === '로그인하러 가기')";
  check("가입: 저장 확인 전에는 다음 버튼 잠김", await b.evaluate(`${continueBtn}.disabled`));
  await b.evaluate(`[...document.querySelectorAll('.recovery-code button')].find((x) => x.textContent === '코드 복사').click()`);
  check("가입: 복사 버튼 누르면 결과 안내", await b.waitUntil(`document.querySelector('.recovery-code__status').textContent.length > 0`));
  check(`가입: 버튼·체크 44px 이상`, (await smallTargets(".recovery-code button, .recovery-code__check")) === 0);
  check(`${W}px: 가입 코드 화면 가로 스크롤 없음`, await noScroll());
  await b.screenshot(`recovery-signup-${W}.png`);
  await b.evaluate(`document.querySelector('.recovery-code__check input').click()`);
  check("가입: 저장했어요 체크하면 다음 버튼 풀림", await b.evaluate(`!${continueBtn}.disabled`));
  await b.evaluate(`${continueBtn}.click()`);
  check("가입: 로그인 화면으로 (가입 완료 안내)", await b.waitUntil(`location.pathname === '/static/login.html' && !document.getElementById('login-notice').hidden`));
  check("가입: 이동할 때 떠나기 확인 창 없음", dialogs.length === 0, dialogs.join(","));

  // ---------- 로그인 → 비밀번호 재설정 ----------
  check("로그인: '비밀번호를 잊으셨나요?' 링크", await b.evaluate(`document.getElementById('reset-link').getAttribute('href').startsWith('/static/reset-password.html')`));
  check("로그인: 재설정 링크 44px", (await smallTargets("#reset-link")) === 0);
  await b.evaluate(`document.getElementById('reset-link').click()`);
  await b.waitUntil(`location.pathname === '/static/reset-password.html' && document.getElementById('reset-form')`);
  check("재설정: 탭 바 없음", await b.evaluate(`!document.querySelector('.tab-bar')`));
  check("재설정: 코드 없으면 재설정 불가 안내", await b.evaluate(`document.querySelector('.form-notice').textContent.includes('잃어버렸다면 재설정할 수 없습니다')`));
  check(`${W}px: 재설정 화면 가로 스크롤 없음`, await noScroll());
  await b.screenshot(`recovery-reset-form-${W}.png`);

  // 틀린 코드 → 같은 실패 문구
  await b.evaluate(`(() => { const f = document.getElementById('reset-form');
    f.email.value = ${JSON.stringify(email)}; f.recovery_code.value = 'AAAA-BBBB-CCCC-DDDD'; f.new_password.value = ${JSON.stringify(newPw)}; f.new_password_confirm.value = ${JSON.stringify(newPw)};
    f.requestSubmit(); })()`);
  check("재설정: 틀린 코드는 '이메일 또는 복구 코드가 맞지 않습니다.'", await b.waitUntil(`document.getElementById('reset-error').textContent === '이메일 또는 복구 코드가 맞지 않습니다.'`));
  // 맞는 코드(소문자·하이픈 없이 적어도 됨) → 새 코드
  await b.evaluate(`(() => { const f = document.getElementById('reset-form'); f.recovery_code.value = ${JSON.stringify(code.replaceAll("-", "").toLowerCase())}; f.requestSubmit(); })()`);
  check("재설정: 성공하면 새 코드", await b.waitUntil(`!document.getElementById('reset-code').hidden && document.getElementById('reset-form').hidden`));
  const newCode = await b.evaluate(`document.querySelector('.recovery-code__value').textContent`);
  check("재설정: 새 코드는 이전 코드와 다름", CODE.test(newCode) && newCode !== code, newCode);
  check(`${W}px: 새 코드 화면 가로 스크롤 없음`, await noScroll());
  await b.screenshot(`recovery-reset-done-${W}.png`);
  await b.evaluate(`document.querySelector('.recovery-code__check input').click()`);
  await b.evaluate(`${continueBtn}.click()`);
  check("재설정: 로그인 화면에 '비밀번호를 바꿨습니다' 안내", await b.waitUntil(`location.pathname === '/static/login.html' && document.getElementById('login-notice').textContent.includes('비밀번호를 바꿨습니다')`));
  check("재설정: 옛 비밀번호 로그인 실패, 새 비밀번호 성공", (await loginApi(email, pw)) === undefined && typeof (await loginApi(email, newPw)) === "string");

  // ---------- 내 정보: 재발급 ----------
  const token = await loginApi(email, newPw);
  await b.evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(token)})`);
  await b.goto("/static/me.html", "!document.getElementById('account').hidden");
  check("내 정보: 복구 코드 발급일 안내", await b.evaluate(`document.getElementById('recovery-status').textContent.startsWith('복구 코드:')`));
  await b.evaluate(`document.getElementById('recovery-toggle').click()`);
  await b.evaluate(`(() => { const f = document.getElementById('recovery-form'); f.password.value = 'wrong-password'; f.requestSubmit(); })()`);
  check("내 정보: 틀린 비밀번호는 칸 아래 안내", await b.waitUntil(`document.querySelector('#recovery-form [data-error-for=password]').textContent.includes('올바르지')`));
  await b.evaluate(`(() => { const f = document.getElementById('recovery-form'); f.password.value = ${JSON.stringify(newPw)}; f.requestSubmit(); })()`);
  check("내 정보: 재발급하면 새 코드", await b.waitUntil(`!document.getElementById('recovery-code').hidden && document.querySelector('#recovery-code .recovery-code__value')`));
  const third = await b.evaluate(`document.querySelector('#recovery-code .recovery-code__value').textContent`);
  check("내 정보: 재발급 코드는 앞의 코드와 다름", CODE.test(third) && third !== newCode);
  check(`${W}px: 내 정보 재발급 화면 가로 스크롤 없음`, await noScroll());
  await b.screenshot(`recovery-me-${W}.png`);
  const reused = await api("POST", "/auth/password-reset", null, { email, recovery_code: newCode, new_password: "whatever1234" });
  check("내 정보: 재발급하면 이전 코드는 400", reused.status === 400);
  await b.evaluate(`document.querySelector('#recovery-code .recovery-code__check input').click()`);
  await b.evaluate(`[...document.querySelectorAll('#recovery-code button')].find((x) => x.textContent === '확인').click()`);
  check("내 정보: 확인을 누르면 코드가 닫힘", await b.waitUntil(`document.getElementById('recovery-code').hidden`));

  const jsErrors = b.exceptions.filter((e) => !String(e).startsWith("Failed to load resource"));
  check("JS 에러 없음", jsErrors.length === 0, jsErrors.join(" | "));
} catch (error) {
  results.push(`ERROR  ${error.message}`);
} finally {
  b.close();
  writeFileSync(join(OUT, "recovery-check.txt"), results.join("\n") + "\n");
  console.log(results.join("\n"));
}
