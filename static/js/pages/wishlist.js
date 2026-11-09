// 찜 목록 화면: 내가 찜한 글을 찜한 순서(최신순)로 보여준다. 판매 완료된 글도 배지와 함께 남는다. 로그인이 필요하다.
// 페이지 번호는 주소창(?page=2)에 저장한다. 새로고침과 뒤로 가기에도 같은 페이지가 나오게 하기 위해서다.
import { listWishlist } from "../api.js";
import { redirectToLogin, renderHeader } from "../auth.js";
import { getToken } from "../token.js";
import { renderPagination, renderPostCard } from "../ui.js";
import { createWishlistButton } from "../wishlist-button.js";

const PAGE_SIZE = 10; // 목록·내 글 화면과 같게 맞춘다.

const summary = document.getElementById("result-summary");
const listError = document.getElementById("list-error");
const emptyActions = document.getElementById("empty-actions");
const list = document.getElementById("post-list");
const pagination = document.getElementById("pagination");

// 응답이 늦게 도착한 이전 요청이 최신 결과를 덮어쓰지 않도록 요청마다 번호를 붙인다.
let latestRequestId = 0;

init();

async function init() {
  // 로그인하지 않았으면 로그인 화면으로 보낸다. 로그인 후 이 화면(보던 페이지 포함)으로 돌아온다.
  if (!getToken()) {
    redirectToLogin();
    return;
  }

  const me = await renderHeader(document.getElementById("site-header"));
  if (me === null) {
    // renderHeader는 401이면 토큰을 지우고 null을, 서버 연결 실패면 토큰을 남긴 채 null을 돌려준다.
    if (!getToken()) {
      redirectToLogin();
    } else {
      showError("서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
    }
    return;
  }

  // 뒤로 가기/앞으로 가기로 주소가 바뀌면 그 페이지를 다시 불러온다.
  window.addEventListener("popstate", load);
  load();
}

// ---------- 불러오기와 그리기 ----------

function readPage() {
  // page는 서버가 검증한다. (0이나 문자이면 422 메시지를 보여준다)
  return new URLSearchParams(window.location.search).get("page") ?? "1";
}

async function load() {
  const requestId = ++latestRequestId;
  summary.textContent = "불러오는 중…";
  listError.hidden = true;
  emptyActions.hidden = true;
  list.replaceChildren();
  pagination.replaceChildren();

  let data;
  try {
    data = await listWishlist({ page: readPage(), size: PAGE_SIZE });
  } catch (error) {
    if (requestId !== latestRequestId) return;
    if (error.status === 401) {
      // 토큰이 만료되었다. (api.js가 토큰을 이미 지웠다)
      redirectToLogin();
      return;
    }
    // 422(잘못된 page)는 필드 메시지를, 그 밖에는 서버 메시지를 보여준다.
    showError(error.fieldErrors?.page ?? error.message);
    return;
  }
  if (requestId !== latestRequestId) return;
  render(data);
}

function render({ items, total, page, size }) {
  const totalPages = Math.max(1, Math.ceil(total / size));

  if (total === 0) {
    summary.textContent = "아직 찜한 글이 없습니다. 마음에 드는 교재에서 하트를 눌러 보세요.";
    emptyActions.hidden = false;
    return;
  }

  summary.textContent =
    items.length === 0
      ? `이 페이지에는 글이 없습니다. (전체 ${total}개, ${totalPages}페이지까지)`
      : `총 ${total}개`;
  // 해제한 카드를 바로 지우지 않는다. 실수로 눌렀을 때 다시 찜할 수 있고, 목록이 갑자기 밀리지 않는다.
  list.replaceChildren(
    ...items.map((post) => renderPostCard(post, { action: createWishlistButton(post, { className: "wish-button--card" }) })),
  );
  renderPagination(pagination, page, totalPages, goToPage);
}

function goToPage(page) {
  history.pushState(null, "", page > 1 ? `?page=${page}` : window.location.pathname);
  load();
  window.scrollTo({ top: 0 });
}

function showError(message) {
  summary.textContent = "";
  listError.textContent = message;
  listError.hidden = false;
}
