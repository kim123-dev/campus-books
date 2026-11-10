// 헤드리스 Chrome 공통 도구 (DevTools 프로토콜 직접 사용, 추가 설치 없음)
import { spawn } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// 경로·포트는 모두 이 파일 위치 기준 상대 경로나 환경 변수로 정한다. (특정 PC 경로를 박아 두지 않기 위해)
const HERE = dirname(fileURLToPath(import.meta.url));
export const ROOT = resolve(HERE, "..", ".."); // campus-books 저장소 루트
export const FIXTURES = join(HERE, "fixtures"); // 업로드 확인용 사진
export const BASE = process.env.UI_CHECK_BASE ?? `http://127.0.0.1:${process.env.UI_CHECK_PORT ?? 8001}`;
export const CDP_PORT = Number(process.env.CDP_PORT ?? 9333);
export const CHROME_PATH = process.env.CHROME_PATH ?? findChrome();
export const PYTHON =
  process.env.PYTHON ?? join(ROOT, "venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");

function findChrome() {
  const candidates = {
    win32: ["C:/Program Files/Google/Chrome/Application/chrome.exe", "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"],
    darwin: ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
    linux: ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"],
  }[process.platform] ?? [];
  return candidates.find((path) => existsSync(path)) ?? candidates[0] ?? "chrome";
}

// run.sh가 띄운 확인용 서버와 같은 DB·키로 CLI를 실행하기 위한 환경 변수
export function cliEnv(OUT) {
  return {
    ...process.env,
    DATABASE_URL: process.env.DATABASE_URL ?? `sqlite:///${OUT.replaceAll("\\", "/")}/ui-check.db`,
    PYTHONIOENCODING: "utf-8",
  };
}
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function startBrowser(OUT, { width, height = 812, mobile = true, port = CDP_PORT }) {
  const chrome = spawn(CHROME_PATH, [
    "--headless=new",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${join(OUT, "chrome-profile")}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--hide-scrollbars",
    "about:blank",
  ]);
  let wsUrl;
  for (let i = 0; i < 50 && !wsUrl; i++) {
    try {
      const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      wsUrl = targets.find((t) => t.type === "page")?.webSocketDebuggerUrl;
    } catch {}
    if (!wsUrl) await sleep(200);
  }
  if (!wsUrl) throw new Error("Chrome에 연결하지 못했습니다.");
  const ws = new WebSocket(wsUrl);
  await new Promise((r) => ws.addEventListener("open", r));
  let nextId = 1;
  const pending = new Map();
  const exceptions = [];
  const listeners = [];
  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    }
    if (msg.method === "Runtime.exceptionThrown") exceptions.push(msg.params.exceptionDetails.exception?.description);
    if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") exceptions.push(msg.params.entry.text);
    for (const fn of listeners) fn(msg);
  });
  const send = (method, params = {}) => {
    const id = nextId++;
    ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
  };
  const evaluate = async (expression) => {
    const { result, exceptionDetails } = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
    return result.value;
  };
  const waitUntil = async (expression, timeout = 8000) => {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      try {
        if (await evaluate(`Boolean(${expression})`)) return true;
      } catch {}
      await sleep(120);
    }
    return false;
  };
  const goto = async (path, waitFor) => {
    await send("Page.navigate", { url: BASE + path });
    await sleep(150);
    await waitUntil(waitFor ?? "document.readyState === 'complete'");
  };
  const screenshot = async (name) => {
    const { data } = await send("Page.captureScreenshot", { format: "png" });
    writeFileSync(join(OUT, name), Buffer.from(data, "base64"));
  };
  const setMetrics = (w, h) =>
    send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: mobile ? 2 : 1, mobile });
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Log.enable");
  await setMetrics(width, height);
  if (mobile) await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
  const close = () => {
    ws.close();
    chrome.kill();
  };
  return { send, evaluate, waitUntil, goto, screenshot, setMetrics, exceptions, listeners, close };
}

export function readSeed(OUT) {
  return JSON.parse(readFileSync(join(OUT, "seed.json"), "utf8"));
}

export async function api(method, path, token, body) {
  const isForm = body instanceof FormData;
  const response = await fetch(BASE + path, {
    method,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body && !isForm ? { "Content-Type": "application/json" } : {}) },
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  });
  return { status: response.status, body: await response.json().catch(() => null) };
}

export async function loginApi(email, password) {
  const response = await fetch(BASE + "/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: email, password }),
  });
  return (await response.json()).access_token;
}

export async function uploadPhoto(OUT, postId, token, name, type) {
  const form = new FormData();
  form.append("file", new Blob([readFileSync(join(FIXTURES, name))], { type }), name);
  return api("POST", `/posts/${postId}/images`, token, form);
}

export function makeAdmin(OUT, email) {
  return import("node:child_process").then(({ execFileSync }) =>
    execFileSync(PYTHON, ["-m", "app.cli", "make-admin", email], {
      cwd: ROOT,
      env: cliEnv(OUT),
      encoding: "utf8",
    }),
  );
}

// 추가 데이터: 관리자, 사진 2장, 찜, 신고 (PC 비교·모바일 확인 공통)
export async function seedExtra(OUT, seed) {
  const PASSWORD = "check-password-123";
  await api("POST", "/auth/signup", null, { email: "admin@uicheck.ac.kr", password: PASSWORD, nickname: "관리자" });
  await makeAdmin(OUT, "admin@uicheck.ac.kr");
  const admin = await loginApi("admin@uicheck.ac.kr", PASSWORD);
  await uploadPhoto(OUT, seed.p1, seed.seller_token, "a.jpg", "image/jpeg");
  await uploadPhoto(OUT, seed.p1, seed.seller_token, "b.png", "image/png");
  await uploadPhoto(OUT, seed.p1, seed.seller_token, "c.webp", "image/webp");
  await api("POST", `/posts/${seed.p1}/wishlist`, seed.buyer_token);
  await api("POST", `/posts/${seed.p2}/reports`, seed.buyer_token, { reason: "SPAM", description: "같은 글을 계속 올려요" });
  return { admin, password: PASSWORD };
}
