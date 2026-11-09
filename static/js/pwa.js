// 홈 화면 앱(PWA) 지원: 서비스 워커 등록과 아이폰 Safari용 "홈 화면에 추가" 안내.
// 모든 화면이 <script type="module" src="/static/js/pwa.js">로 불러 서비스 워커를 등록하고,
// 안내는 첫 화면(목록)만 showInstallGuide로 보여준다.
import { el, icon } from "./ui.js";

// 닫은 사용자에게 다시 보이지 않게 기록하는 키
export const INSTALL_GUIDE_KEY = "campus-books.install-guide-dismissed";

registerServiceWorker();

function registerServiceWorker() {
  // 서비스 워커는 https(또는 localhost)에서만 동작한다. 지원하지 않으면 그냥 웹 페이지로 쓴다.
  if (!("serviceWorker" in navigator)) return;
  // 화면을 그리는 요청과 겹치지 않게, 페이지를 다 불러온 뒤 등록한다.
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/static/sw.js", { scope: "/static/" }).catch(() => {
      // 등록에 실패해도 화면은 그대로 쓸 수 있으므로 알리지 않는다.
    });
  });
}

/**
 * 아이폰·아이패드 Safari에서만 "공유 → 홈 화면에 추가" 안내를 container 맨 위에 보여준다.
 * - iOS Safari에는 안드로이드 Chrome 같은 설치 버튼(beforeinstallprompt)이 없어 직접 알려줘야 한다.
 * - 이미 홈 화면 앱으로 열었거나(standalone), 한 번 닫았으면 보여주지 않는다.
 */
export function showInstallGuide(container) {
  if (!isIosSafari() || isStandalone() || readDismissed()) return;

  const close = el("button", {
    type: "button",
    className: "install-guide__close",
    text: "×",
    attrs: { "aria-label": "홈 화면 추가 안내 닫기" },
  });
  const shareIcon = el("span", { className: "install-guide__share" }, icon("share"));
  const guide = el(
    "aside",
    { className: "install-guide", attrs: { "aria-label": "홈 화면에 추가" } },
    el(
      "div",
      { className: "install-guide__body" },
      el("p", { className: "install-guide__title", text: "홈 화면에 추가하면 앱처럼 쓸 수 있어요" }),
      el(
        "p",
        { className: "install-guide__text" },
        "Safari 아래쪽의 ",
        shareIcon,
        "공유 → '홈 화면에 추가'를 누르세요.",
      ),
    ),
    close,
  );
  close.addEventListener("click", () => {
    saveDismissed();
    guide.remove();
  });
  container.prepend(guide);
}

// iPadOS Safari는 Mac처럼 알려지므로 터치 지원 여부로 구분한다.
// 아이폰의 Chrome·Firefox·Edge 등은 메뉴가 달라 안내 문구가 맞지 않으므로 뺀다.
function isIosSafari() {
  const ua = navigator.userAgent;
  const isIos = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
  return isIos && /Safari\//.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS|GSA\//.test(ua);
}

function isStandalone() {
  return window.navigator.standalone === true || window.matchMedia("(display-mode: standalone)").matches;
}

// 사생활 보호 모드 등에서 localStorage가 막혀 있으면 예외가 난다. 그때는 기록 없이 안내만 닫는다.
function readDismissed() {
  try {
    return window.localStorage.getItem(INSTALL_GUIDE_KEY) === "1";
  } catch {
    return false;
  }
}

function saveDismissed() {
  try {
    window.localStorage.setItem(INSTALL_GUIDE_KEY, "1");
  } catch {
    // 저장하지 못하면 다음에 다시 보일 수 있지만, 지금 화면에서는 닫힌다.
  }
}
