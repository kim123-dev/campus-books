// 후기 관리 화면 (관리자 전용): 숨긴 후기를 보고 숨김을 풀 수 있다. (숨기기는 신고 처리에서 한다)
// 보기(숨긴 후기·전체)·사용자·페이지는 주소창(?status=ALL&reviewee_id=3&page=2)에 저장한다.
import { adminUserHref, adminUserLink, handleAuthError, reasonForm, startAdminPage } from "../admin-common.js";
import { listAdminReviews, unhideReview } from "../api.js";
import { el, formatDate, renderPagination } from "../ui.js";

const PAGE_SIZE = 20;
const STATUSES = ["HIDDEN", "ALL"];
const RATING_TEXT = { GOOD: "좋아요", BAD: "아쉬워요" };

const main = document.getElementById("admin-main");
const notice = document.getElementById("admin-notice");
const filterUser = document.getElementById("filter-user");
const summary = document.getElementById("result-summary");
const listError = document.getElementById("list-error");
const list = document.getElementById("review-list");
const pagination = document.getElementById("pagination");

// 응답이 늦게 도착한 이전 요청이 최신 결과를 덮어쓰지 않도록 요청마다 번호를 붙인다.
let latestRequestId = 0;

init();

async function init() {
  if ((await startAdminPage(main)) === null) return;
  window.addEventListener("popstate", load);
  load();
}

function readQuery() {
  const params = new URLSearchParams(window.location.search);
  const number = (key) => (/^\d+$/.test(params.get(key) ?? "") ? params.get(key) : "");
  return {
    status: STATUSES.includes(params.get("status")) ? params.get("status") : "HIDDEN",
    revieweeId: number("reviewee_id"),
    reviewerId: number("reviewer_id"),
    page: params.get("page") ?? "1",
  };
}

async function load() {
  const requestId = ++latestRequestId;
  const query = readQuery();
  markTabs(query);
  renderUserFilter(query);
  summary.textContent = "불러오는 중…";
  listError.hidden = true;
  list.replaceChildren();
  pagination.replaceChildren();

  let data;
  try {
    data = await listAdminReviews({
      hidden: query.status === "HIDDEN" ? "true" : undefined,
      reviewee_id: query.revieweeId,
      reviewer_id: query.reviewerId,
      page: query.page,
      size: PAGE_SIZE,
    });
  } catch (error) {
    if (requestId !== latestRequestId) return;
    if (handleAuthError(error)) return;
    showError(error.fieldErrors?.page ?? error.message);
    return;
  }
  if (requestId !== latestRequestId) return;
  render(data);
}

// 사용자 필터가 걸려 있으면 탭을 바꿔도 유지한다.
function markTabs({ status, revieweeId, reviewerId }) {
  for (const tab of document.querySelectorAll(".tabs__item")) {
    if (tab.dataset.status === status) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
    const params = new URLSearchParams({ status: tab.dataset.status });
    if (revieweeId) params.set("reviewee_id", revieweeId);
    if (reviewerId) params.set("reviewer_id", reviewerId);
    tab.setAttribute("href", `?${params}`);
  }
}

function renderUserFilter({ revieweeId, reviewerId }) {
  const userId = revieweeId || reviewerId;
  filterUser.hidden = !userId;
  if (!userId) return;
  const params = new URLSearchParams(window.location.search);
  for (const key of ["reviewee_id", "reviewer_id", "page"]) params.delete(key);
  filterUser.replaceChildren(
    el("a", { href: adminUserHref(userId), text: `사용자 #${userId}` }),
    revieweeId ? "가 받은 후기만 보는 중 · " : "가 쓴 후기만 보는 중 · ",
    el("a", { href: `?${params}`, text: "전체 보기" }),
  );
}

function render({ items, total, page, size }) {
  if (total === 0) {
    summary.textContent = readQuery().status === "HIDDEN" ? "숨긴 후기가 없습니다." : "후기가 없습니다.";
    return;
  }
  summary.textContent = items.length === 0 ? `이 페이지에는 후기가 없습니다. (전체 ${total}건)` : `총 ${total}건`;
  list.replaceChildren(...items.map(renderReview));
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

function renderReview(review) {
  const hidden = review.hidden_at !== null;
  return el(
    "li",
    { className: "card admin-card", attrs: { "data-review-id": String(review.id) } },
    el(
      "div",
      { className: "admin-card__head" },
      el("span", {
        className: `admin-badge${review.rating === "BAD" ? " admin-badge--suspend" : ""}`,
        text: RATING_TEXT[review.rating] ?? review.rating,
      }),
      hidden ? el("span", { className: "admin-badge admin-badge--hide-review", text: `숨김 · ${formatDate(review.hidden_at)}` }) : null,
      el("span", { className: "admin-card__meta", text: `#${review.id} · ${formatDate(review.created_at)}` }),
    ),
    el("p", { className: "admin-card__line" }, adminUserLink(review.reviewer), " → ", adminUserLink(review.reviewee)),
    el("p", { className: "admin-card__meta", text: `교재: ${review.book_title}` }),
    el("p", { className: "admin-card__reason", text: review.content || "(내용 없음)" }),
    hidden ? unhideForm(review) : null,
  );
}

function unhideForm(review) {
  return reasonForm({
    id: `unhide-${review.id}`,
    submitText: "숨김 해제",
    confirm: (reason) =>
      `후기 #${review.id}의 숨김을 풀까요?\n받은 사람의 프로필과 매너 학점에 바로 다시 들어갑니다.\n\n사유: ${reason}`,
    onSubmit: async (reason) => {
      await unhideReview(review.id, { reason });
      notice.textContent = `후기 #${review.id}의 숨김을 해제했습니다.`;
      notice.hidden = false;
      load();
    },
  });
}

function showError(message) {
  summary.textContent = "";
  listError.textContent = message;
  listError.hidden = false;
}
