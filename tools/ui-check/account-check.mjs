// 비밀번호 변경·회원 탈퇴 화면(내 글)을 헤드리스 Chrome으로 확인한다.
// 사용: WIDTH=375 tools/ui-check/run.sh account-check
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { api, loginApi, readSeed, sleep, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const seed = readSeed(OUT);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);

// 확인 전용 사용자를 새로 만들고, 판매자 글에 문의해 대화방을 하나 만든다.
const email = "leaver@uicheck.ac.kr";
const pw = "leaverpass123";
const newPw = "leaverpass456";
await api("POST", "/auth/signup", null, { email, password: pw, nickname: "탈퇴예정" });
const token = await loginApi(email, pw);
const conv = await api("POST", `/posts/${seed.p1}/conversations`, token);
await api("POST", `/conversations/${conv.body.id}/messages`, token, { content: "아직 판매 중인가요?" });

const b = await startBrowser(OUT, { width: W });
const dialogs = [];
b.listeners.push((msg) => {
  if (msg.method === "Page.javascriptDialogOpening") {
    dialogs.push(msg.params.message);
    b.send("Page.handleJavaScriptDialog", { accept: true });
  }
});

try {
  await b.goto("/static/index.html");
  await b.evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(token)})`);
  await b.goto("/static/my-posts.html", "!document.getElementById('account').hidden");

  check("계정 관리 버튼 2개 보임", await b.evaluate(`!document.getElementById('password-toggle').hidden && !document.getElementById('withdraw-toggle').hidden`));
  check("가로 스크롤 없음", await b.evaluate(`document.documentElement.scrollWidth <= ${W}`));

  // 비밀번호 변경: 틀린 현재 비밀번호 → 칸 아래 에러
  await b.evaluate(`document.getElementById('password-toggle').click()`);
  await b.screenshot(`account-password-${W}.png`);
  await b.evaluate(`(() => { const f = document.getElementById('password-form');
    f.current_password.value = 'wrong-pass'; f.new_password.value = ${JSON.stringify(newPw)}; f.new_password_confirm.value = ${JSON.stringify(newPw)};
    f.requestSubmit(); })()`);
  check("틀린 비밀번호 에러 표시", await b.waitUntil(`document.querySelector('[data-error-for=current_password]').textContent.includes('올바르지')`));

  await b.evaluate(`(() => { const f = document.getElementById('password-form'); f.current_password.value = ${JSON.stringify(pw)}; f.requestSubmit(); })()`);
  check("변경 완료 안내", await b.waitUntil(`document.getElementById('account-notice').textContent.includes('변경했습니다')`));
  const stored = await b.evaluate(`localStorage.getItem("campus-books.token")`);
  check("새 토큰 저장", stored && stored !== token);
  check("새 토큰으로 내 정보 조회", (await api("GET", "/users/me", stored)).status === 200);
  check("옛 토큰 401", (await api("GET", "/users/me", token)).status === 401);

  // 회원 탈퇴: 확인 창 두 번 → 목록 화면으로 이동
  await b.evaluate(`document.getElementById('withdraw-toggle').click()`);
  await b.screenshot(`account-withdraw-${W}.png`);
  await b.evaluate(`(() => { const f = document.getElementById('withdraw-form'); f.password.value = ${JSON.stringify(newPw)}; f.requestSubmit(); })()`);
  check("탈퇴 후 목록으로 이동", await b.waitUntil(`location.pathname.endsWith('/index.html')`));
  check("확인 창 2번 + 완료 알림", dialogs.length === 3, dialogs.join(" / "));
  check("토큰 삭제", (await b.evaluate(`localStorage.getItem("campus-books.token")`)) === null);
  check("탈퇴 후 로그인 실패", (await loginApi(email, newPw)) === undefined);

  // 판매자 화면에서 상대가 "탈퇴한 사용자"로 보인다.
  await b.evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(seed.seller_token)})`);
  await b.goto(`/static/chat.html?id=${conv.body.id}`, "document.getElementById('chat-partner')?.textContent");
  await sleep(300);
  check("상대 이름 '탈퇴한 사용자'", (await b.evaluate(`document.getElementById('chat-partner').textContent`)) === "탈퇴한 사용자");
  check("입력창 잠김", await b.evaluate(`document.querySelector('textarea').disabled`));
  await b.screenshot(`account-chat-${W}.png`);
  // 틀린 비밀번호 요청(400)은 일부러 보낸 것이라 네트워크 로그는 빼고 본다.
  const jsErrors = b.exceptions.filter((e) => !String(e).startsWith("Failed to load resource"));
  check("JS 에러 없음", jsErrors.length === 0, jsErrors.join(" | "));
} catch (error) {
  results.push(`ERROR  ${error.message}`);
} finally {
  b.close();
  writeFileSync(join(OUT, "account-check.txt"), results.join("\n") + "\n");
  console.log(results.join("\n"));
}
