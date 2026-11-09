// 목록 화면: 필터 → API 호출 → 카드 그리기 → 페이지 이동.
// 필터와 페이지는 주소창(?q=...&page=2)에 저장한다. 새로고침, 뒤로 가기, 링크 공유에도 같은 결과가 나오게 하기 위해서다.
import { listPosts } from "../api.js";
import { renderHeader } from "../auth.js";
import { clearFormErrors, el, icon, renderPagination, renderPostCard, showFormErrors } from "../ui.js";
import { createWishlistButton } from "../wishlist-button.js";

const PAGE_SIZE = 10;
const FILTER_KEYS = ["q", "status", "course_name", "min_price", "max_price"];
// 모바일에서 "필터" 버튼 안에 접어 두는 조건. 검색어(q)는 항상 보이는 한 줄 검색창에 있다.
const FOLDED_KEYS = FILTER_KEYS.filter((key) => key !== "q");

const form = document.getElementById("filter-form");
const filterError = document.getElementById("filter-error");
const summary = document.getElementById("result-summary");
const list = document.getElementById("post-list");
const pagination = document.getElementById("pagination");
const filterToggle = document.getElementById("filter-toggle");
const filterCount = el("span", { className: "count-badge filter-form__count", attrs: { "aria-hidden": "true" }, hidden: true });

// 응답이 늦게 도착한 이전 요청이 최신 결과를 덮어쓰지 않도록 요청마다 번호를 붙인다.
let latestRequestId = 0;

// 로그인한 사용자(없으면 null). 내 글에는 하트를 그리지 않으려고 쓴다.
const mePromise = renderHeader(document.getElementById("site-header"));

form.addEventListener("submit", (event) => {
  event.preventDefault();
  // 모바일에서는 검색하면 필터를 접어 결과가 바로 보이게 한다. (오류가 나면 load가 다시 펼친다)
  setFilterOpen(false);
  navigate(readForm(), 1); // 조건이 바뀌면 첫 페이지부터 본다.
});

document.getElementById("filter-reset").addEventListener("click", () => {
  form.reset();
  navigate({}, 1);
});

// ---------- 모바일 필터 접기 ----------
// PC에서는 CSS가 버튼을 숨기고 모든 칸을 보여주므로 이 상태와 상관없다.

document.getElementById("search-button").append(icon("search"));
filterToggle.append(icon("filter"), el("span", { text: "필터" }), filterCount);
filterToggle.addEventListener("click", () => setFilterOpen(!form.classList.contains("is-open")));

function setFilterOpen(open) {
  form.classList.toggle("is-open", open);
  filterToggle.setAttribute("aria-expanded", String(open));
}

// 접힌 상태에서도 어떤 조건이 걸려 있는지 알 수 있게 버튼에 개수를 보여준다. ("필터 2")
function showFilterCount(filters) {
  const count = FOLDED_KEYS.filter((key) => filters[key]).length;
  filterCount.textContent = String(count);
  filterCount.hidden = count === 0;
  filterToggle.setAttribute("aria-label", count > 0 ? `필터, ${count}개 적용됨` : "필터");
}

// 접힌 칸에 오류가 있으면(예: 최소 가격 > 최대 가격 422) 펼쳐서 보여준다.
function openIfFoldedError() {
  const more = document.getElementById("filter-more");
  if (more.querySelector('[aria-invalid="true"]') || !filterError.hidden) setFilterOpen(true);
}

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
  showFilterCount(filters);
  clearFormErrors(form, filterError);
  summary.textContent = "불러오는 중…";
  list.replaceChildren();
  pagination.replaceChildren();

  try {
    // 헤더의 로그인 확인은 실패해도 null을 돌려주므로 함께 기다려도 목록이 막히지 않는다.
    const [data, me] = await Promise.all([listPosts({ ...filters, page, size: PAGE_SIZE }), mePromise]);
    if (requestId !== latestRequestId) return;
    render(data, filters, me);
  } catch (error) {
    if (requestId !== latestRequestId) return;
    summary.textContent = "";
    showFormErrors(form, filterError, error);
    openIfFoldedError();
  }
}

function render(data, filters, me) {
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
  list.replaceChildren(...items.map((post) => renderPostCard(post, { action: wishlistAction(post, me) })));
  renderPagination(pagination, page, totalPages, (nextPage) => goToPage(filters, nextPage));
}

/**
 * 카드 위 하트. 내 글에는 없고, 판매 완료된 글은 찜해 둔 경우에만(해제할 수 있게) 보여준다.
 * 로그인하지 않았으면 하트를 보여주고, 누르면 로그인 화면으로 보낸다.
 */
function wishlistAction(post, me) {
  if (me !== null && me.id === post.seller.id) return null;
  if (post.status === "SOLD" && post.is_wishlisted !== true) return null;
  return createWishlistButton(post, { className: "wish-button--card" });
}

function goToPage(filters, page) {
  navigate(filters, page);
  window.scrollTo({ top: 0 });
}
