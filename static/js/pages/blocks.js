// 차단 목록 화면: 내가 차단한 사용자를 차단한 순서(최신순)로 보여주고 해제할 수 있게 한다. 로그인이 필요하다.
// 페이지 번호는 주소창(?page=2)에 저장한다. 새로고침과 뒤로 가기에도 같은 페이지가 나오게 하기 위해서다.
import { listBlocks, unblockUser } from "../api.js";
import { redirectToLogin, renderHeader } from "../auth.js";
import { confirmUnblock } from "../safety.js";
import { getToken } from "../token.js";
import { el, formatDate, renderPagination } from "../ui.js";

const PAGE_SIZE = 20;

const summary = document.getElementById("result-summary");
const listError = document.getElementById("list-error");
const list = document.getElementById("block-list");
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
  list.replaceChildren();
  pagination.replaceChildren();

  let data;
  try {
    data = await listBlocks({ page: readPage(), size: PAGE_SIZE });
  } catch (error) {
    if (requestId !== latestRequestId) return;
    if (error.status === 401) {
      redirectToLogin();
      return;
    }
    showError(error.fieldErrors?.page ?? error.message);
    return;
  }
  if (requestId !== latestRequestId) return;
  render(data);
}

function render({ items, total, page, size }) {
  const totalPages = Math.max(1, Math.ceil(total / size));
  if (total === 0) {
    summary.textContent = "차단한 사용자가 없습니다.";
    return;
  }
  summary.textContent =
    items.length === 0
      ? `이 페이지에는 차단한 사용자가 없습니다. (전체 ${total}명, ${totalPages}페이지까지)`
      : `총 ${total}명`;
  list.replaceChildren(...items.map(renderBlockItem));
  renderPagination(pagination, page, totalPages, goToPage);
}

function renderBlockItem({ user, created_at: createdAt }) {
  const status = el("p", { className: "form-error", attrs: { role: "alert" }, hidden: true });
  const button = el("button", {
    type: "button",
    className: "button",
    text: "차단 해제",
    attrs: { "aria-label": `${user.nickname}님 차단 해제` },
  });
  button.addEventListener("click", async () => {
    if (!confirmUnblock(user.nickname)) return;
    status.hidden = true;
    button.disabled = true;
    try {
      await unblockUser(user.id);
      // 줄을 바로 지우지 않고 "해제됨"으로 남겨, 목록이 갑자기 밀리지 않게 한다.
      button.replaceWith(el("span", { className: "block-item__done", text: "해제됨" }));
    } catch (error) {
      if (error.status === 401) {
        redirectToLogin();
        return;
      }
      status.textContent = error.message;
      status.hidden = false;
      button.disabled = false;
    }
  });

  return el(
    "li",
    { className: "card block-item" },
    el(
      "div",
      { className: "block-item__info" },
      el("p", { className: "block-item__name", text: user.nickname }),
      el("p", { className: "block-item__meta", text: `${formatDate(createdAt).slice(0, 10)} 차단` }),
    ),
    button,
    status,
  );
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
