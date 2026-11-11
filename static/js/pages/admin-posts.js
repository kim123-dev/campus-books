// 글 관리 화면 (관리자 전용): 글을 찾아 신고 없이도 지울 수 있다. 삭제는 사유 창 → 확인 창을 거친다.
// 검색어·판매 상태·판매자·페이지는 주소창(?q=회로&status=SOLD&seller_id=3&page=2)에 저장한다.
import { adminUserHref, adminUserLink, handleAuthError, openReasonDialog, startAdminPage } from "../admin-common.js";
import { adminDeletePost, listAdminPosts } from "../api.js";
import { el, formatDate, formatPrice, renderPagination, statusBadge } from "../ui.js";

const PAGE_SIZE = 20;
const STATUSES = ["ON_SALE", "RESERVED", "SOLD"];

const main = document.getElementById("admin-main");
const form = document.getElementById("post-search");
const qInput = document.getElementById("search-q");
const statusSelect = document.getElementById("filter-status");
const filterUser = document.getElementById("filter-user");
const notice = document.getElementById("admin-notice");
const summary = document.getElementById("result-summary");
const listError = document.getElementById("list-error");
const list = document.getElementById("post-list");
const pagination = document.getElementById("pagination");

// 응답이 늦게 도착한 이전 요청이 최신 결과를 덮어쓰지 않도록 요청마다 번호를 붙인다.
let latestRequestId = 0;

init();

async function init() {
  if ((await startAdminPage(main)) === null) return;
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    applyFilter();
  });
  // 상태는 고르는 즉시 적용한다. 검색어는 "검색"을 눌러야 적용한다.
  statusSelect.addEventListener("change", applyFilter);
  window.addEventListener("popstate", load);
  load();
}

// 판매자 필터(사용자 상세에서 온 경우)는 검색을 바꿔도 유지한다.
function applyFilter() {
  const params = new URLSearchParams();
  const q = qInput.value.trim();
  if (q) params.set("q", q);
  if (statusSelect.value) params.set("status", statusSelect.value);
  const { sellerId } = readQuery();
  if (sellerId) params.set("seller_id", sellerId);
  history.pushState(null, "", `?${params}`);
  load();
}

function readQuery() {
  const params = new URLSearchParams(window.location.search);
  return {
    q: params.get("q") ?? "",
    status: STATUSES.includes(params.get("status")) ? params.get("status") : "",
    sellerId: /^\d+$/.test(params.get("seller_id") ?? "") ? params.get("seller_id") : "",
    page: params.get("page") ?? "1",
  };
}

async function load() {
  const requestId = ++latestRequestId;
  const query = readQuery();
  qInput.value = query.q;
  statusSelect.value = query.status;
  renderUserFilter(query.sellerId);
  summary.textContent = "불러오는 중…";
  listError.hidden = true;
  list.replaceChildren();
  pagination.replaceChildren();

  let data;
  try {
    data = await listAdminPosts({ q: query.q, status: query.status, seller_id: query.sellerId, page: query.page, size: PAGE_SIZE });
  } catch (error) {
    if (requestId !== latestRequestId) return;
    if (handleAuthError(error)) return;
    showError(error.fieldErrors?.q ?? error.fieldErrors?.page ?? error.message);
    return;
  }
  if (requestId !== latestRequestId) return;
  render(data);
}

function renderUserFilter(sellerId) {
  filterUser.hidden = !sellerId;
  if (!sellerId) return;
  const params = new URLSearchParams(window.location.search);
  params.delete("seller_id");
  params.delete("page");
  filterUser.replaceChildren(
    el("a", { href: adminUserHref(sellerId), text: `사용자 #${sellerId}` }),
    "의 글만 보는 중 · ",
    el("a", { href: `?${params}`, text: "전체 보기" }),
  );
}

function render({ items, total, page, size }) {
  if (total === 0) {
    summary.textContent = "조건에 맞는 글이 없습니다.";
    return;
  }
  summary.textContent = items.length === 0 ? `이 페이지에는 글이 없습니다. (전체 ${total}건)` : `총 ${total}건`;
  list.replaceChildren(...items.map(renderPost));
  renderPagination(pagination, page, Math.max(1, Math.ceil(total / size)), goToPage);
}

function goToPage(page) {
  const params = new URLSearchParams(window.location.search);
  if (page > 1) params.set("page", String(page));
  else params.delete("page");
  history.pushState(null, "", `?${params}`);
  load();
  window.scrollTo({ top: 0 });
}

function renderPost(post) {
  const deleteButton = el("button", { type: "button", className: "button button--danger", text: "삭제" });
  deleteButton.addEventListener("click", () => openDeleteDialog(post));
  return el(
    "li",
    { className: "card admin-card", attrs: { "data-post-id": String(post.id) } },
    el(
      "div",
      { className: "admin-card__head" },
      statusBadge(post.status),
      post.pending_report_count > 0
        ? el("span", { className: "admin-badge admin-badge--suspend", text: `미처리 신고 ${post.pending_report_count}건` })
        : null,
      el("span", { className: "admin-card__meta", text: `#${post.id} · ${formatDate(post.created_at)}` }),
    ),
    el("a", { className: "admin-card__title", href: `/static/post.html?id=${encodeURIComponent(post.id)}`, text: post.title }),
    el("p", { className: "admin-card__meta", text: `${post.book_title} · ${formatPrice(post.price)}` }),
    el("p", { className: "admin-card__line" }, "판매자 ", adminUserLink(post.seller)),
    el("div", { className: "admin-card__actions" }, deleteButton),
  );
}

async function openDeleteDialog(post) {
  let resolved = [];
  const deleted = await openReasonDialog({
    title: "글 삭제",
    targetText: `#${post.id} ${post.title} (${post.book_title})`,
    submitText: "삭제하기",
    confirm: (reason) =>
      `"${post.title}" 글을 지울까요? 되돌릴 수 없어요.\n사진·찜도 함께 지워지고, 쪽지 대화는 남습니다.` +
      (post.pending_report_count > 0 ? `\n이 글의 미처리 신고 ${post.pending_report_count}건도 함께 처리됩니다.` : "") +
      `\n\n사유: ${reason}`,
    onSubmit: async (reason) => {
      resolved = (await adminDeletePost(post.id, { reason })).resolved_report_ids;
    },
  });
  if (!deleted) return;
  notice.textContent =
    `글 #${post.id}을(를) 삭제했습니다.` + (resolved.length > 0 ? ` 미처리 신고 ${resolved.length}건을 함께 처리했어요.` : "");
  notice.hidden = false;
  load();
}

function showError(message) {
  summary.textContent = "";
  listError.textContent = message;
  listError.hidden = false;
}
