// 10단계 사진 업로드 화면을 375px 헤드리스 Chrome으로 확인한다. (DevTools 프로토콜 직접 사용, 추가 설치 없음)
// 사진은 고르는 즉시 임시 사진(POST /pending-images)으로 올라가고, 저장할 때 글과 함께 붙는다.
// 휴대폰 사진(큰 JPEG·EXIF 회전·MPO·HEIC)은 photo_fixtures.py가 실행할 때 만든다.
import { spawn, spawnSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { BASE, CDP_PORT, CHROME_PATH, FIXTURES, PYTHON } from "./lib.mjs";

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
// 화면이 보낸 API 요청("POST /pending-images" 형태). 사진을 언제 올리고 지우는지 확인하는 데 쓴다.
const requests = [];

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
    if (msg.method === "Network.requestWillBeSent") {
      const { method, url } = msg.params.request;
      if (url.startsWith(BASE) && !url.includes("/static/")) requests.push(`${method} ${new URL(url).pathname}`);
    }
    if (msg.method === "Runtime.exceptionThrown") exceptions.push(msg.params.exceptionDetails.exception?.description);
    if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") exceptions.push(msg.params.entry.text);
  });
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Log.enable");
  await send("Network.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: 812, deviceScaleFactor: 2, mobile: true });

  // ---------- 10단계: 사진 업로드 (375px) ----------
  const PHONE = join(OUT, "phone-photos");
  const made = spawnSync(PYTHON, [join(FIXTURES, "..", "photo_fixtures.py"), PHONE], { encoding: "utf8" });
  if (made.status !== 0) throw new Error(`휴대폰 사진을 만들지 못했습니다: ${made.stderr}`);
  const PHONE_NAMES = ["large.jpg", "rotated.jpg", "motion.jpg", "photo.heic"];
  const files = (...names) => names.map((n) => join(PHONE_NAMES.includes(n) ? PHONE : FIXTURES, n));
  // waitUpload가 false면 줄이기만 기다리고, 올라가는 중인 상태로 돌아온다. (진행률 확인용)
  async function pickFiles(names, { waitUpload = true } = {}) {
    const { root } = await send("DOM.getDocument", { depth: 0 });
    const { nodeId } = await send("DOM.querySelector", { nodeId: root.nodeId, selector: "#photos" });
    await send("DOM.setFileInputFiles", { nodeId, files: files(...names) });
    // 고른 사진은 브라우저에서 줄인 뒤에 목록에 들어간다. "줄이는 중" 안내가 사라질 때까지 기다린다.
    await sleep(300);
    await waitUntil("document.getElementById('photo-status').hidden", 15000);
    // 줄인 사진은 바로 임시 사진으로 올라간다. 올리기가 끝날(성공·실패) 때까지 기다린다.
    if (waitUpload) await waitUntil("!document.querySelector('.photo-tile--uploading')", 15000);
  }
  const submitButtonText = () => evaluate("document.querySelector('#post-form button[type=submit]').textContent");
  const sent = (pattern) => requests.filter((r) => pattern.test(r)).length;
  // 미리보기 그림(= 실제로 올릴 파일)의 크기와 용량
  const previewInfo = (index) => evaluate(`(async () => { const i = document.querySelectorAll('.photo-tile__image')[${index}];
    await i.decode().catch(() => {}); const size = i.src.startsWith('blob:') ? (await (await fetch(i.src)).blob()).size : null;
    return { w: i.naturalWidth, h: i.naturalHeight, size, blob: i.src.startsWith('blob:'), src: new URL(i.src).pathname }; })()`);
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
  check("작성: 고르는 즉시 임시 사진으로 올라가고, 끝나면 칸에 표시가 남지 않음", sent(/^POST \/pending-images$/) === 2 && !(await evaluate("Boolean(document.querySelector('.photo-tile__state'))")), requests.join(", "));

  await pickFiles(["c.webp", "d.gif", "large.jpg"]);
  const pickError = await text("photos-error");
  check("작성: 3장 넘거나 GIF는 빼고 안내", (await tileCount()) === 3 && (await text("photo-count")) === "3/3" && pickError.includes("JPG, PNG, WebP, HEIC") && pickError.includes("3장까지"), pickError);
  const small = await previewInfo(0);
  check("작성: 작은 사진(2000px·2MB 이하)은 줄이지 않고 원본 그대로", small.blob && small.w === 1200 && small.size === readFileSync(join(FIXTURES, "a.jpg")).length, JSON.stringify(small));
  check("작성: 3장이 차면 사진 추가 막힘", await evaluate("document.getElementById('photos').disabled"));
  check(`${W}px: 사진 3장 폼 가로 스크롤 없음`, await noHorizontalScroll());
  await evaluate("document.querySelector('.photo-tile__button').scrollIntoView({block: 'center'})");
  await screenshot("10-1-form-photos.png");

  await evaluate("document.querySelectorAll('.photo-tile__button')[2].click()");
  check("작성: 새 사진 빼기 → 2/3", (await tileCount()) === 2 && (await text("photo-count")) === "2/3" && !(await evaluate("document.getElementById('photos').disabled")));
  await sleep(500); // 삭제 요청은 화면이 기다리지 않고 보내므로 잠깐 기다린다.
  check("작성: 뺀 사진은 서버의 임시 사진도 바로 지움", sent(/^DELETE \/pending-images\/\d+$/) === 1, requests.join(", "));

  await fillForm("사진 있는 컴퓨터 구조 교재");
  await evaluate("document.querySelector('#post-form button[type=submit]').click()");
  const reachedDetail = await waitUntil("location.pathname === '/static/post.html' && !document.getElementById('post-detail').hidden", 15000);
  check("작성: 글 + 사진 2장 저장 후 상세로 이동", reachedDetail, await evaluate("location.href"));
  check("작성: 사진은 글 저장 요청에 번호로 함께 감 (글마다 따로 올리지 않음)", sent(/^POST \/posts$/) === 1 && sent(/^POST \/posts\/\d+\/images$/) === 0, requests.join(", "));
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

  await goto("/static/me.html", "document.querySelectorAll('.post-card').length > 0");
  check("내 글: 썸네일 표시", await evaluate(`[...document.querySelectorAll('.post-card')].some(c => c.getAttribute('href').endsWith('id=${photoPostId}') && c.querySelector('.post-card__thumb').src.includes('_thumb.webp'))`));

  // 수정: 첫 사진을 빼고 새 사진 하나 추가
  await goto(`/static/post-form.html?id=${photoPostId}`, "!document.getElementById('form-card').hidden && document.querySelectorAll('.photo-tile').length > 0");
  check("수정: 올린 사진 2장 표시, 2/3", (await tileCount()) === 2 && (await text("photo-count")) === "2/3");
  const before = await (await fetch(`${BASE}/posts/${photoPostId}`)).json();
  await evaluate("document.querySelector('.photo-tile__button').click()");
  check("수정: 빼기 누르면 흐리게 + 되돌리기, 1/3", (await evaluate("document.querySelector('.photo-tile').classList.contains('photo-tile--removed') && document.querySelector('.photo-tile__button').textContent === '되돌리기'")) && (await text("photo-count")) === "1/3");
  await pickFiles(["c.webp"]);
  const unsaved = await (await fetch(`${BASE}/posts/${photoPostId}`)).json();
  check("수정: 저장 전에는 공개된 글의 사진이 그대로", JSON.stringify(unsaved.images) === JSON.stringify(before.images));
  await evaluate("document.querySelector('#post-form button[type=submit]').click()");
  await waitUntil("location.pathname === '/static/post.html' && !document.getElementById('post-detail').hidden", 15000);
  const after = await (await fetch(`${BASE}/posts/${photoPostId}`)).json();
  check("수정: 첫 사진 삭제 + 새 사진 추가 반영", after.images.length === 2 && !after.images.some((i) => i.id === before.images[0].id) && after.images.some((i) => i.id === before.images[1].id),
    JSON.stringify(after.images.map((i) => i.id)));
  check("수정: 지운 사진 파일은 404", (await fetch(BASE + before.images[0].url)).status === 404);

  // 올리기 실패: 화면 검사는 통과하지만(.jpg) 서버가 거절하는 파일
  const totalBefore = (await (await fetch(`${BASE}/posts`)).json()).total;
  await goto("/static/post-form.html", "!document.getElementById('form-card').hidden");
  await pickFiles(["a.jpg", "fake.jpg"]);
  const failedTile = await evaluate(`(() => { const t = document.querySelectorAll('.photo-tile'); return {
    ok: !t[0].querySelector('.photo-tile__state'), failed: t[1].classList.contains('photo-tile--failed'),
    state: t[1].querySelector('.photo-tile__state')?.textContent, buttons: [...t[1].querySelectorAll('button')].map(b => b.textContent) }; })()`);
  check("올리기 실패: 그 칸에만 '실패'와 다시 시도·빼기", failedTile.ok && failedTile.failed && failedTile.state === "실패" && failedTile.buttons.join() === "다시 시도,빼기", JSON.stringify(failedTile));
  check("올리기 실패: 서버 메시지를 사진 칸 아래에 표시", (await text("photos-error")).includes("JPG, PNG, WebP"), await text("photos-error"));
  check(`${W}px: 실패한 사진이 있는 폼 가로 스크롤 없음`, await noHorizontalScroll());
  await evaluate("document.querySelector('.photo-tile__button').scrollIntoView({block: 'center'})");
  await screenshot("10-4-upload-failed.png");
  await fillForm("사진 일부 실패 글");
  await evaluate("document.querySelector('#post-form button[type=submit]').click()");
  await waitUntil("document.getElementById('photos-error').textContent.includes('올리지 못한 사진')", 5000);
  check("올리기 실패: 실패한 사진이 있으면 저장을 막고 안내, 글은 생기지 않음",
    (await text("photos-error")).includes("다시 시도하거나 빼 주세요") && (await evaluate("location.pathname")) === "/static/post-form.html"
      && !(await evaluate("document.querySelector('#post-form button[type=submit]').disabled")) && (await (await fetch(`${BASE}/posts`)).json()).total === totalBefore);
  await evaluate("document.querySelectorAll('.photo-tile')[1].querySelector('button:last-child').click()");
  check("올리기 실패: 실패한 사진을 빼면 1/3", (await tileCount()) === 1 && (await text("photo-count")) === "1/3" && (await text("photos-error")) === "");
  await evaluate("document.querySelector('#post-form button[type=submit]').click()");
  await waitUntil("location.pathname === '/static/post.html' && !document.getElementById('post-detail').hidden", 15000);
  const savedAfterFailure = await (await fetch(`${BASE}/posts/${await evaluate("new URLSearchParams(location.search).get('id')")}`)).json();
  check("올리기 실패: 뺀 뒤 저장하면 글 하나에 성공한 사진 1장", (await (await fetch(`${BASE}/posts`)).json()).total === totalBefore + 1 && savedAfterFailure.images.length === 1);

  // ---------- 휴대폰 사진: 줄이기, EXIF 회전, MPO, 진행률, HEIC ----------
  await goto("/static/post-form.html", "!document.getElementById('form-card').hidden");
  // 올리는 속도를 느리게 해, 올라가는 중의 진행률(%)과 "올리는 중에 저장"을 확인한다.
  await send("Network.emulateNetworkConditions", { offline: false, latency: 20, downloadThroughput: -1, uploadThroughput: 150 * 1024 });
  await pickFiles(["large.jpg", "rotated.jpg", "motion.jpg"], { waitUpload: false });
  const large = await previewInfo(0);
  check("휴대폰: 2700만 화소 JPEG를 절반(3000px)으로 줄임", large.w === 3000 && large.h === 2250 && large.size < 2 * 1024 * 1024 && (await text("photos-error")) === "", JSON.stringify(large));
  const rotated = await previewInfo(1);
  check("휴대폰: EXIF 회전 사진은 세로로 세워서 줄임", rotated.w === 2000 && rotated.h === 3000 && rotated.size < 1024 * 1024, JSON.stringify(rotated));
  // 화질 비교용으로 실제로 올릴 파일을 저장해 둔다. (화질 비교 숫자를 다시 잴 때 쓴다)
  const dataUrl = await evaluate("fetch(document.querySelector('.photo-tile__image').src).then(r => r.blob()).then(b => new Promise(r => { const f = new FileReader(); f.onload = () => r(f.result); f.readAsDataURL(b); }))");
  writeFileSync(join(OUT, "prepared-large.jpg"), Buffer.from(dataUrl.split(",")[1], "base64"));
  check(`${W}px: 사진 3장 고른 폼 가로 스크롤 없음`, await noHorizontalScroll());

  await waitUntil("/^[1-9]\\d?%$/.test(document.querySelector('.photo-tile--uploading .photo-tile__state [aria-hidden=true]')?.textContent ?? '')", 15000);
  const uploadingTile = await evaluate(`(() => { const t = document.querySelector('.photo-tile--uploading'); if (!t) return null; return {
    percent: t.querySelector('.photo-tile__state [aria-hidden=true]').textContent, spoken: t.querySelector('.photo-tile__state .visually-hidden')?.textContent,
    buttons: [...t.querySelectorAll('button')].map(b => b.textContent) }; })()`);
  check("진행률: 올리는 중인 칸에 % 표시, 빼기 가능", uploadingTile !== null && /^\d+%$/.test(uploadingTile.percent) && uploadingTile.buttons.join() === "빼기", JSON.stringify(uploadingTile));
  check("진행률: 화면 낭독기에는 '올리는 중'만 읽히고 %는 읽히지 않음(aria-hidden)", uploadingTile?.spoken === "올리는 중");
  check("진행률: 올리는 중에도 저장 버튼을 누를 수 있음", !(await evaluate("document.querySelector('#post-form button[type=submit]').disabled")));
  await evaluate("document.querySelector('.photo-tile__button').scrollIntoView({block: 'center'})");
  await screenshot("10-5-upload-progress.png");

  await fillForm("휴대폰 사진 글");
  await evaluate("document.querySelector('#post-form button[type=submit]').click()");
  await sleep(200);
  check("올리는 중에 저장: 남은 업로드를 기다리는 동안 '사진 올리는 중…', 사진 추가·빼기 잠금",
    (await submitButtonText()) === "사진 올리는 중…" && (await evaluate("document.querySelector('#post-form button[type=submit]').disabled && document.getElementById('photos').disabled && [...document.querySelectorAll('.photo-tile__button')].every(b => b.disabled)")),
    await submitButtonText());
  const phoneSaved = await waitUntil("location.pathname === '/static/post.html' && !document.getElementById('post-detail').hidden", 60000);
  await send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
  check("휴대폰: 큰 JPEG·회전·MPO 3장 저장 후 상세로 이동", phoneSaved, await evaluate("location.href"));
  const phonePost = await (await fetch(`${BASE}/posts/${await evaluate("new URLSearchParams(location.search).get('id')")}`)).json();
  const sizes = await evaluate(`Promise.all(${JSON.stringify(phonePost.images.map((i) => i.url))}.map(u => fetch(u).then(r => r.blob()).then(createImageBitmap).then(b => [b.width, b.height])))`);
  check("휴대폰: 서버 사진 1600px WebP, 회전 사진은 세로", // 회전 사진의 가로는 반올림에 따라 1066~1067px이다.
    JSON.stringify([sizes[0], sizes[2]]) === "[[1600,1200],[1600,1200]]" && sizes[1][1] === 1600 && Math.abs(sizes[1][0] - 1067) <= 1, JSON.stringify(sizes));

  await goto("/static/post-form.html", "!document.getElementById('form-card').hidden");
  await pickFiles(["photo.heic"]);
  const heic = await previewInfo(0);
  check("HEIC: 브라우저가 못 열면 기본 그림으로 미리보기, 원본을 그대로 보냄", (await tileCount()) === 1 && heic.src === "/static/img/book-placeholder.svg" && (await text("photos-error")) === "", JSON.stringify(heic));
  await fillForm("아이폰 사진 글");
  await evaluate("document.querySelector('#post-form button[type=submit]').click()");
  const heicSaved = await waitUntil("location.pathname === '/static/post.html' && document.querySelector('.gallery__main')?.complete", 15000);
  check("HEIC: 서버가 WebP로 바꿔 저장", heicSaved && (await evaluate("(() => { const m = document.querySelector('.gallery__main'); return m.naturalWidth === 1200 && m.naturalHeight === 900 && m.src.endsWith('.webp'); })()")));

  check("JS 예외·콘솔 에러 없음", exceptions.filter((e) => !String(e).includes("Failed to load resource")).length === 0, exceptions.join(" / "));
} catch (error) {
  results.push(`ERROR  ${error.stack}`);
} finally {
  writeFileSync(join(OUT, "photo-check.txt"), results.join("\n"));
  console.log(results.join("\n"));
  ws?.close();
  chrome.kill();
}
