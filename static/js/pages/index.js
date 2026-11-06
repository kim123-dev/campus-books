// 목록 화면: 필터 → API 호출 → 카드 그리기 → 페이지 이동.
// 필터와 페이지는 주소창(?q=...&page=2)에 저장한다. 새로고침, 뒤로 가기, 링크 공유에도 같은 결과가 나오게 하기 위해서다.
import { listPosts } from "../api.js";
import { renderHeader } from "../auth.js";
import {
  CONDITION_LABELS,
  clearFormErrors,
  el,
  formatDate,
  formatPrice,
  showFormErrors,
  statusBadge,
} from "../ui.js";

const PAGE_SIZE = 10;
const FILTER_KEYS = ["q", "status", "course_name", "min_price", "max_price"];

const form = document.getElementById("filter-form");
const filterError = document.getElementById("filter-error");
const summary = document.getElementById("result-summary");
const list = document.getElementById("post-list");
const pagination = document.getElementById("pagination");

// 응답이 늦게 도착한 이전 요청이 최신 결과를 덮어쓰지 않도록 요청마다 번호를 붙인다.
let latestRequestId = 0;

renderHeader(document.getElementById("site-header"));

form.addEventListener("submit", (event) => {
  event.preventDefault();
  navigate(readForm(), 1); // 조건이 바뀌면 첫 페이지부터 본다.
});

document.getElementById("filter-reset").addEventListener("click", () => {
  form.reset();
  navigate({}, 1);
});

// 뒤로 가기/앞으로 가기로 주소가 바뀌면 그 주소의 조건으로 다시 불러온다.
window.addEventListener("popstate", load);

load();

// ---------- 주소창 ↔ 조건 ----------

function readUrl() {
  const params = new URLSearchParams(window.location.search);
  const filters = {};
  for (const key of FILTER_KEYS) {
    const value = params.get(key);
    if (value) filters[key] = value;
  }
  // page는 서버가 검증한다. (0이나 문자이면 422 메시지를 보여준다)
  return { filters, page: params.get("page") ?? "1" };
}

function readForm() {
  const filters = {};
  for (const key of FILTER_KEYS) {
    const value = String(form.elements.namedItem(key).value).trim();
    if (value) filters[key] = value;
  }
  return filters;
}

function fillForm(filters) {
  for (const key of FILTER_KEYS) form.elements.namedItem(key).value = filters[key] ?? "";
}

function navigate(filters, page) {
  const params = new URLSearchParams(filters);
  if (Number(page) > 1) params.set("page", page);
  const query = params.toString();
  history.pushState(null, "", query ? `?${query}` : window.location.pathname);
  load();
}

// ---------- 불러오기와 그리기 ----------

async function load() {
  const { filters, page } = readUrl();
  const requestId = ++latestRequestId;

  fillForm(filters);
  clearFormErrors(form, filterError);
  summary.textContent = "불러오는 중…";
  list.replaceChildren();
  pagination.replaceChildren();

  try {
    const data = await listPosts({ ...filters, page, size: PAGE_SIZE });
    if (requestId !== latestRequestId) return;
    render(data, filters);
  } catch (error) {
    if (requestId !== latestRequestId) return;
    summary.textContent = "";
    showFormErrors(form, filterError, error);
  }
}

function render(data, filters) {
  const { items, total, page, size } = data;
  const totalPages = Math.max(1, Math.ceil(total / size));
  const hasFilters = Object.keys(filters).length > 0;

  if (total === 0) {
    summary.textContent = hasFilters ? "조건에 맞는 글이 없습니다." : "아직 등록된 글이 없습니다.";
    return;
  }

  summary.textContent =
    items.length === 0
      ? `이 페이지에는 글이 없습니다. (전체 ${total}개, ${totalPages}페이지까지)`
      : `총 ${total}개`;
  list.replaceChildren(...items.map(renderCard));
  renderPagination(filters, page, totalPages);
}

function renderCard(post) {
  const courseText = post.course_name ? ` · ${post.course_name}` : "";
  return el(
    "li",
    {},
    el(
      "a",
      { className: "card post-card", href: `/static/post.html?id=${encodeURIComponent(post.id)}` },
      el(
        "div",
        { className: "post-card__top" },
        statusBadge(post.status),
        el("span", { className: "post-card__condition", text: `책 상태 ${CONDITION_LABELS[post.condition] ?? post.condition}` }),
      ),
      el("h2", { className: "post-card__title", text: post.title }),
      el("p", { className: "post-card__book", text: `${post.book_title}${courseText}` }),
      el("p", { className: "post-card__price", text: formatPrice(post.price) }),
      el("p", { className: "post-card__meta", text: `${post.seller.nickname} · ${formatDate(post.created_at)}` }),
    ),
  );
}

function renderPagination(filters, page, totalPages) {
  if (totalPages <= 1 && page === 1) return;

  const prev = el("button", { type: "button", className: "button", text: "이전", disabled: page <= 1 });
  const next = el("button", { type: "button", className: "button", text: "다음", disabled: page >= totalPages });
  prev.addEventListener("click", () => goToPage(filters, Math.min(page - 1, totalPages)));
  next.addEventListener("click", () => goToPage(filters, page + 1));

  pagination.replaceChildren(
    prev,
    el("span", { className: "pagination__info", text: `${page} / ${totalPages} 페이지` }),
    next,
  );
}

function goToPage(filters, page) {
  navigate(filters, page);
  window.scrollTo({ top: 0 });
}
