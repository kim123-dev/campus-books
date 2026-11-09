// 찜(하트) 버튼. 목록 카드, 상세, 찜 목록 화면이 함께 쓴다.
// ui.js는 auth.js가 불러오는 공통 부품이라, 로그인 이동(auth.js)을 쓰는 이 버튼은 순환 참조를 피하려고 따로 둔다.
import { addWishlist, removeWishlist } from "./api.js";
import { redirectToLogin } from "./auth.js";
import { getToken } from "./token.js";
import { el } from "./ui.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const HEART_PATH =
  "M12 20.5s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.6a4.3 4.3 0 0 1 7.5 2.7c0 5.6-7.5 10.2-7.5 10.2z";
const ERROR_SHOW_MS = 4000;

/**
 * 하트 버튼을 만든다. 내 글에는 만들지 말 것 (서버도 400으로 막는다).
 * - 로그인하지 않았으면 누를 때 로그인 화면으로 보내고, 로그인 후 이 화면으로 돌아온다.
 * - 누르면 응답이 올 때까지 잠그고, 성공한 뒤에 하트를 바꾼다. (미리 바꿨다 되돌리지 않는다)
 * @param {{id: number, title: string, is_wishlisted: boolean|null}} post
 * @param {{className?: string}} options className: 놓이는 곳별 모양 (카드 위 / 상세)
 */
export function createWishlistButton(post, { className = "" } = {}) {
  let wished = post.is_wishlisted === true;
  const button = el("button", { type: "button", className: `wish-button ${className}`.trim() }, heartIcon());

  const paint = () => {
    button.setAttribute("aria-pressed", String(wished));
    // 카드 안에는 제목이 여러 개라 어떤 글의 버튼인지 이름에 글 제목을 넣는다.
    button.setAttribute("aria-label", `${post.title} ${wished ? "찜 해제" : "찜하기"}`);
  };
  paint();

  button.addEventListener("click", async () => {
    if (!getToken()) {
      redirectToLogin();
      return;
    }
    button.disabled = true;
    try {
      if (wished) {
        await removeWishlist(post.id);
        wished = false;
      } else {
        wished = (await addWishlist(post.id)).is_wishlisted;
      }
      paint();
    } catch (error) {
      if (error.status === 401) {
        // 토큰이 만료되었다. (api.js가 토큰을 이미 지웠다)
        redirectToLogin();
        return;
      }
      // 400(내 글, 그사이 판매 완료됨), 404(그사이 삭제됨)는 서버 메시지를 그대로 보여준다.
      showWishlistError(error.message);
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

// HTML 문자열 없이 createElementNS로 SVG를 만든다. 색은 CSS가 aria-pressed에 따라 채운다.
function heartIcon() {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", HEART_PATH);
  svg.append(path);
  return svg;
}

// 카드에는 에러를 넣을 자리가 없으므로, 화면 아래에 잠깐 보이는 알림 하나를 함께 쓴다.
let errorToast = null;
let hideTimer = 0;

function showWishlistError(message) {
  if (errorToast === null) {
    errorToast = el("p", { className: "toast", attrs: { role: "alert" }, hidden: true });
    document.body.append(errorToast);
  }
  errorToast.textContent = message;
  errorToast.hidden = false;
  clearTimeout(hideTimer);
  hideTimer = setTimeout(() => {
    errorToast.hidden = true;
  }, ERROR_SHOW_MS);
}
