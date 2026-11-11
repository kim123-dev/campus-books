// 사용자 관리 화면 (관리자 전용): 닉네임·이메일·번호로 찾고, 상태(정지 중·관리자·탈퇴)로 거른다.
// 검색어·상태·페이지는 주소창(?q=kim&status=SUSPENDED&page=2)에 저장한다.
import { adminUserHref, handleAuthError, startAdminPage, userBadges, userLabel } from "../admin-common.js";
import { listAdminUsers } from "../api.js";
import { el, formatDate, renderPagination } from "../ui.js";

const PAGE_SIZE = 20;
const STATUSES = ["SUSPENDED", "ADMIN", "WITHDRAWN"];

const main = document.getElementById("admin-main");
const form = document.getElementById("user-search");
const qInput = document.getElementById("search-q");
const statusSelect = document.getElementById("filter-status");
const summary = document.getElementById("result-summary");
const listError = document.getElementById("list-error");
const list = document.getElementById("user-list");
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

function applyFilter() {
  const params = new URLSearchParams();
  const q = qInput.value.trim();
  if (q) params.set("q", q);
  if (statusSelect.value) params.set("status", statusSelect.value);
  history.pushState(null, "", `?${params}`);
  load();
}

function readQuery() {
  const params = new URLSearchParams(window.location.search);
  return {
    q: params.get("q") ?? "",
    status: STATUSES.includes(params.get("status")) ? params.get("status") : "",
    page: params.get("page") ?? "1",
  };
}

async function load() {
  const requestId = ++latestRequestId;
  const query = readQuery();
  qInput.value = query.q;
  statusSelect.value = query.status;
  summary.textContent = "불러오는 중…";
  listError.hidden = true;
  list.replaceChildren();
  pagination.replaceChildren();

  let data;
  try {
    data = await listAdminUsers({ ...query, size: PAGE_SIZE });
  } catch (error) {
    if (requestId !== latestRequestId) return;
    if (handleAuthError(error)) return;
    showError(error.fieldErrors?.q ?? error.fieldErrors?.page ?? error.message);
    return;
  }
  if (requestId !== latestRequestId) return;
  render(data);
}

function render({ items, total, page, size }) {
  if (total === 0) {
    summary.textContent = "조건에 맞는 사용자가 없습니다.";
    return;
  }
  summary.textContent = items.length === 0 ? `이 페이지에는 사용자가 없습니다. (전체 ${total}명)` : `총 ${total}명`;
  list.replaceChildren(...items.map(renderUser));
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

function renderUser(user) {
  const counts = [`글 ${user.post_count}개`];
  if (user.pending_report_count > 0) counts.push(`미처리 신고 ${user.pending_report_count}건`);
  return el(
    "li",
    { className: "card admin-card" },
    el(
      "div",
      { className: "admin-card__head" },
      el("a", { className: "admin-card__title", href: adminUserHref(user.id), text: userLabel(user) }),
      ...userBadges(user),
    ),
    user.email ? el("p", { className: "admin-card__email", text: user.email }) : null,
    el("p", { className: "admin-card__meta", text: `#${user.id} · ${formatDate(user.created_at)} 가입 · ${counts.join(" · ")}` }),
  );
}

function showError(message) {
  summary.textContent = "";
  listError.textContent = message;
  listError.hidden = false;
}
