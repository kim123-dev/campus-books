// 10단계 사진 업로드 화면을 375px 헤드리스 Chrome으로 확인한다. (DevTools 프로토콜 직접 사용, 추가 설치 없음)
import { spawn } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { BASE, CDP_PORT, CHROME_PATH, FIXTURES } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const seed = JSON.parse(readFileSync(join(OUT, "seed.json"), "utf8"));
const PORT = CDP_PORT;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, detail = "") => {
  results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);
};

const chrome = spawn(CHROME_PATH, [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${join(OUT, "chrome-profile")}`,
  "--no-first-run",
  "--no-default-browser-check",
  "about:blank",
]);

let ws;
let nextId = 1;
const pending = new Map();
const exceptions = [];

async function connect() {
  for (let i = 0; i < 50; i++) {
    try {
      const targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = targets.find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(200);
  }
  throw new Error("Chrome에 연결하지 못했습니다.");
}

function send(method, params = {}) {
  const id = nextId++;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

async function evaluate(expression) {
  const { result, exceptionDetails } = await send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
  return result.value;
}

async function goto(path, waitFor) {
  await send("Page.navigate", { url: BASE + path });
  await waitUntil(waitFor ?? "document.readyState === 'complete'");
}

async function waitUntil(expression, timeout = 8000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try {
      if (await evaluate(`Boolean(${expression})`)) return true;
    } catch {}
    await sleep(150);
  }
  return false;
}

async function screenshot(name) {
  const { data } = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, name), Buffer.from(data, "base64"));
}

async function api(method, path, token, body) {
  const response = await fetch(BASE + path, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  return response.status;
}

const setToken = (token) => evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(token)})`);
// 모바일 에뮬레이션에서는 내용이 넓으면 innerWidth도 함께 넓어지므로, 375px 고정값과 모든 요소의 오른쪽 끝을 비교한다.
const noHorizontalScroll = () => evaluate(`document.documentElement.scrollWidth <= ${W} && [...document.querySelectorAll('main *')].every(e => e.getBoundingClientRect().right <= ${W + 0.5} || getComputedStyle(e).position === 'absolute' || e.closest('.visually-hidden'))`);

try {
  ws = new WebSocket(await connect());
  await new Promise((r) => ws.addEventListener("open", r));
  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    }
    if (msg.method === "Runtime.exceptionThrown") exceptions.push(msg.params.exceptionDetails.exception?.description);
    if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") exceptions.push(msg.params.entry.text);
  });
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Log.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: 812, deviceScaleFactor: 2, mobile: true });

  // ---------- 10단계: 사진 업로드 (375px) ----------
  // 5MB 넘는 사진은 저장소에 두지 않고 실행할 때 만든다. (a.jpg 뒤에 0을 덧붙여 6MB로)
  const BIG = join(OUT, "big.jpg");
  writeFileSync(BIG, Buffer.concat([readFileSync(join(FIXTURES, "a.jpg")), Buffer.alloc(6 * 1024 * 1024)]));
  const files = (...names) => names.map((n) => (n === "big.jpg" ? BIG : join(FIXTURES, n)));
  async function pickFiles(names) {
    const { root } = await send("DOM.getDocument", { depth: 0 });
    const { nodeId } = await send("DOM.querySelector", { nodeId: root.nodeId, selector: "#photos" });
    await send("DOM.setFileInputFiles", { nodeId, files: files(...names) });
    await sleep(300);
  }
  const text = (id) => evaluate(`document.getElementById(${JSON.stringify(id)}).textContent`);
  const tileCount = () => evaluate("document.querySelectorAll('#photo-list .photo-tile').length");
  const fillForm = (title) => evaluate(`(() => {
    const f = document.getElementById('post-form');
    f.elements.title.value = ${JSON.stringify(title)};
    f.elements.book_title.value = '컴퓨터 구조론';
    f.elements.condition.value = 'GOOD';
    f.elements.price.value = '12000';
  })()`);
  const imagesLoaded = (selector) => evaluate(`[...document.querySelectorAll(${JSON.stringify(selector)})].every(i => i.complete && i.naturalWidth > 0)`);

  await goto("/static/index.html");
  await setToken(seed.seller_token);
  await goto("/static/post-form.html", "!document.getElementById('form-card').hidden");
  check("작성: 처음에는 0/3, 사진 목록 숨김", (await text("photo-count")) === "0/3" && (await evaluate("document.getElementById('photo-list').hidden")));

  await pickFiles(["a.jpg", "b.png"]);
  check("작성: 2장 고르면 미리보기 2개, 2/3", (await tileCount()) === 2 && (await text("photo-count")) === "2/3");
  await waitUntil("[...document.querySelectorAll('.photo-tile__image')].every(i => i.complete && i.naturalWidth > 0)");
  check("작성: 미리보기는 blob 주소로 표시됨", await evaluate("[...document.querySelectorAll('.photo-tile__image')].every(i => i.src.startsWith('blob:') && i.naturalWidth > 0)"));

  await pickFiles(["c.webp", "d.gif", "big.jpg"]);
  const pickError = await text("photos-error");
  check("작성: 3장 넘거나 GIF·5MB 초과는 빼고 안내", (await tileCount()) === 3 && (await text("photo-count")) === "3/3" && pickError.includes("JPG, PNG, WebP") && pickError.includes("5MB"), pickError);
  check("작성: 3장이 차면 사진 추가 막힘", await evaluate("document.getElementById('photos').disabled"));
  check(`${W}px: 사진 3장 폼 가로 스크롤 없음`, await noHorizontalScroll());
  await evaluate("document.querySelector('.photo-tile__button').scrollIntoView({block: 'center'})");
  await screenshot("10-1-form-photos.png");

  await evaluate("document.querySelectorAll('.photo-tile__button')[2].click()");
  check("작성: 새 사진 빼기 → 2/3", (await tileCount()) === 2 && (await text("photo-count")) === "2/3" && !(await evaluate("document.getElementById('photos').disabled")));

  await fillForm("사진 있는 컴퓨터 구조 교재");
  await evaluate("document.querySelector('#post-form button[type=submit]').click()");
  const reachedDetail = await waitUntil("location.pathname === '/static/post.html' && !document.getElementById('post-detail').hidden", 15000);
  check("작성: 글 + 사진 2장 저장 후 상세로 이동", reachedDetail, await evaluate("location.href"));
  const photoPostId = await evaluate("new URLSearchParams(location.search).get('id')");

  await waitUntil("document.querySelector('.gallery__main')?.complete");
  check("상세: 큰 사진 + 작은 사진 2개", (await evaluate("document.querySelectorAll('.gallery__thumb').length")) === 2 && (await imagesLoaded(".gallery__main")));
  check("상세: 사진은 /images/ 경로, 대체 글", await evaluate("(() => { const m = document.querySelector('.gallery__main'); return /^\\/images\\/[0-9a-f]{32}\\.webp$/.test(new URL(m.src).pathname) && m.alt === '컴퓨터 구조론 사진 1/2'; })()"));
  // 사진은 가로 줄(track)에 이어 붙어 있고, 작은 사진을 누르면 그 사진 위치로 넘어간다.
  check("상세: 사진 2장이 가로 줄에 순서대로", await evaluate("(() => { const s = [...document.querySelectorAll('.gallery__track .gallery__main')]; return s.length === 2 && s[1].alt === '컴퓨터 구조론 사진 2/2' && s[0].src !== s[1].src; })()"));
  await evaluate("document.querySelectorAll('.gallery__thumb')[1].click()");
  await sleep(300);
  check("상세: 작은 사진 누르면 큰 사진 바뀜", await evaluate("(() => { const t = document.querySelector('.gallery__track'); const shown = Math.round(t.scrollLeft / t.clientWidth); const r = t.querySelectorAll('.gallery__main')[1].getBoundingClientRect(), f = t.getBoundingClientRect(); return shown === 1 && Math.abs(r.left - f.left) < 1 && document.querySelectorAll('.gallery__thumb')[1].getAttribute('aria-pressed') === 'true' && document.querySelectorAll('.gallery__thumb')[0].getAttribute('aria-pressed') === 'false'; })()"));
  check("상세: 사진 번호 '2 / 2' (모바일에서만 보임)", await evaluate(`(() => { const c = document.querySelector('.gallery__counter'); return c.textContent === '2 / 2' && (c.getClientRects().length > 0) === (${W} < 768); })()`));
  const imgHeaders = await evaluate("fetch(document.querySelector('.gallery__main').src).then(r => r.headers.get('content-type') + '|' + r.headers.get('x-content-type-options'))");
  check("상세: 사진 응답 image/webp + nosniff", imgHeaders === "image/webp|nosniff", imgHeaders);
  check(`${W}px: 상세 가로 스크롤 없음`, await noHorizontalScroll());
  await evaluate("scrollTo(0, 0)");
  await screenshot("10-2-detail-gallery.png");

  await goto("/static/index.html", "document.querySelectorAll('.post-card').length > 0");
  await waitUntil("document.querySelector('.post-card__thumb')?.complete");
  const cards = await evaluate(`[...document.querySelectorAll('.post-card')].map(c => ({ href: c.getAttribute('href'), src: new URL(c.querySelector('.post-card__thumb').src).pathname, lazy: c.querySelector('.post-card__thumb').loading }))`);
  const photoCard = cards.find((c) => c.href.endsWith(`id=${photoPostId}`));
  check("목록: 사진 있는 글은 썸네일", photoCard && /_thumb\.webp$/.test(photoCard.src) && photoCard.lazy === "lazy", JSON.stringify(photoCard));
  check("목록: 사진 없는 글은 기본 그림", cards.filter((c) => c !== photoCard).every((c) => c.src === "/static/img/book-placeholder.svg"));
  check("목록: 첫 카드 썸네일 표시됨", await imagesLoaded(".post-card:first-of-type .post-card__thumb, li:first-child .post-card__thumb"));
  check(`${W}px: 목록 가로 스크롤 없음`, await noHorizontalScroll());
  await screenshot("10-3-list.png");

  await goto("/static/my-posts.html", "document.querySelectorAll('.post-card').length > 0");
  check("내 글: 썸네일 표시", await evaluate(`[...document.querySelectorAll('.post-card')].some(c => c.getAttribute('href').endsWith('id=${photoPostId}') && c.querySelector('.post-card__thumb').src.includes('_thumb.webp'))`));

  // 수정: 첫 사진을 빼고 새 사진 하나 추가
  await goto(`/static/post-form.html?id=${photoPostId}`, "!document.getElementById('form-card').hidden && document.querySelectorAll('.photo-tile').length > 0");
  check("수정: 올린 사진 2장 표시, 2/3", (await tileCount()) === 2 && (await text("photo-count")) === "2/3");
  const before = await (await fetch(`${BASE}/posts/${photoPostId}`)).json();
  await evaluate("document.querySelector('.photo-tile__button').click()");
  check("수정: 빼기 누르면 흐리게 + 되돌리기, 1/3", (await evaluate("document.querySelector('.photo-tile').classList.contains('photo-tile--removed') && document.querySelector('.photo-tile__button').textContent === '되돌리기'")) && (await text("photo-count")) === "1/3");
  await pickFiles(["c.webp"]);
  await evaluate("document.querySelector('#post-form button[type=submit]').click()");
  await waitUntil("location.pathname === '/static/post.html' && !document.getElementById('post-detail').hidden", 15000);
  const after = await (await fetch(`${BASE}/posts/${photoPostId}`)).json();
  check("수정: 첫 사진 삭제 + 새 사진 추가 반영", after.images.length === 2 && !after.images.some((i) => i.id === before.images[0].id) && after.images.some((i) => i.id === before.images[1].id),
    JSON.stringify(after.images.map((i) => i.id)));
  check("수정: 지운 사진 파일은 404", (await fetch(BASE + before.images[0].url)).status === 404);

  // 부분 실패: 화면 검사는 통과하지만(.jpg) 서버가 거절하는 파일
  const totalBefore = (await (await fetch(`${BASE}/posts`)).json()).total;
  await goto("/static/post-form.html", "!document.getElementById('form-card').hidden");
  await pickFiles(["a.jpg", "fake.jpg"]);
  await fillForm("사진 일부 실패 글");
  await evaluate("document.querySelector('#post-form button[type=submit]').click()");
  await waitUntil("!document.getElementById('form-error').hidden", 15000);
  const failText = await text("form-error");
  check("부분 실패: 글은 저장됐다는 안내 + 서버 메시지", failText.includes("글은 저장됐지만 사진 1장") && failText.includes("JPG, PNG, WebP"), failText);
  check("부분 실패: 수정 모드로 전환 (?id=, 제목·버튼)", (await evaluate("/^\\?id=\\d+$/.test(location.search)")) && (await text("form-title")) === "판매글 수정" && (await evaluate("document.querySelector('#post-form button[type=submit]').textContent")) === "저장하기");
  check("부분 실패: 성공한 1장은 올린 사진으로 표시", (await tileCount()) === 1 && (await text("photo-count")) === "1/3");
  await screenshot("10-4-partial-failure.png");
  await evaluate("document.querySelector('#post-form button[type=submit]').click()");
  await waitUntil("location.pathname === '/static/post.html'", 15000);
  check("부분 실패: 다시 저장해도 글이 하나만 생김", (await (await fetch(`${BASE}/posts`)).json()).total === totalBefore + 1);

  check("JS 예외·콘솔 에러 없음", exceptions.filter((e) => !String(e).includes("Failed to load resource")).length === 0, exceptions.join(" / "));
} catch (error) {
  results.push(`ERROR  ${error.stack}`);
} finally {
  writeFileSync(join(OUT, "photo-check.txt"), results.join("\n"));
  console.log(results.join("\n"));
  ws?.close();
  chrome.kill();
}
