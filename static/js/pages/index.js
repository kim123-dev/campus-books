// 목록 화면: 필터 → API 호출 → 카드 그리기 → 페이지 이동.
// 필터와 페이지는 주소창(?q=...&page=2)에 저장한다. 새로고침, 뒤로 가기, 링크 공유에도 같은 결과가 나오게 하기 위해서다.
import { getMySchool, listPosts, listSchools } from "../api.js";
import { renderHeader } from "../auth.js";
import { t } from "../i18n.js";
import { showInstallGuide } from "../pwa.js";
import {
  clearFormErrors,
  el,
  EMPTY_POSTS_IMAGE,
  EMPTY_SEARCH_IMAGE,
  icon,
  renderEmptyState,
  renderPagination,
  renderPostCard,
  showFormErrors,
} from "../ui.js";
import { createWishlistButton } from "../wishlist-button.js";

const PAGE_SIZE = 10;
const FILTER_KEYS = ["q", "school_id", "status", "course_name", "min_price", "max_price"];
// 홈의 학교 안내를 닫았는지(이 브라우저에만 기록).
const SCHOOL_HINT_KEY = "campus-books.school-hint-dismissed";
// "필터" 버튼 안에 접어 두는 조건. 검색어(q)는 항상 보이는 한 줄 검색창에 있다.
const FOLDED_KEYS = FILTER_KEYS.filter((key) => key !== "q");
// "판매 완료 글도 보기" 체크(주소에는 켰을 때만 show_sold=1). 기본은 꺼짐이라 필터 개수에는 세지 않는다.
const SHOW_SOLD_KEY = "show_sold";

const form = document.getElementById("filter-form");
const filterError = document.getElementById("filter-error");
const summary = document.getElementById("result-summary");
const emptyActions = document.getElementById("empty-actions");
const list = document.getElementById("post-list");
const pagination = document.getElementById("pagination");
const filterToggle = document.getElementById("filter-toggle");
const filterCount = el("span", { className: "count-badge filter-form__count", attrs: { "aria-hidden": "true" }, hidden: true });

// 응답이 늦게 도착한 이전 요청이 최신 결과를 덮어쓰지 않도록 요청마다 번호를 붙인다.
let latestRequestId = 0;

/**
 * 초기화 단계 하나를 실행한다. 한 단계가 예외를 내도(예: 휴대폰 브라우저에서만 없는 기능)
 * 나머지 단계와 목록 불러오기는 그대로 진행되게 단계마다 따로 감싼다.
 */
function safely(label, step, fallback = undefined) {
  try {
    return step();
  } catch (error) {
    console.error(`[home] ${label} 실패`, error);
    return fallback;
  }
}

// 로그인한 사용자(없으면 null). 내 글에는 하트를 그리지 않으려고 쓴다.
// 헤더를 그리다 실패해도 목록은 "로그인 안 함"으로 그린다.
const mePromise = Promise.resolve(
  safely("헤더", () => renderHeader(document.getElementById("site-header")), null),
).catch(() => null);

// 검색 폼은 스크립트가 붙기 전 기본 제출(새로고침)로도 동작하지만, 붙은 뒤에는 화면 안에서 처리한다.
// 목록 불러오기보다 먼저 붙여서, 다른 단계가 실패해도 검색 버튼이 새로고침 없이 동작하게 한다.
form.addEventListener("submit", (event) => {
  event.preventDefault();
  // 검색하면 필터를 접어 결과가 바로 보이게 한다. (오류가 나면 load가 다시 펼친다)
  setFilterOpen(false);
  navigate(readForm(), 1); // 조건이 바뀌면 첫 페이지부터 본다.
});

document.getElementById("filter-reset").addEventListener("click", () => {
  form.reset();
  navigate({}, 1);
});

// ---------- 필터 접기 ----------
// PC·모바일 모두 검색창 한 줄만 보이고, 필터 버튼을 누르면 판매 상태·과목명·가격 칸이 펼쳐진다.

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
  filterToggle.setAttribute("aria-label", count > 0 ? t("home.filter_aria", { count }) : t("term.filter"));
}

// 접힌 칸에 오류가 있으면(예: 최소 가격 > 최대 가격 422) 펼쳐서 보여준다.
function openIfFoldedError() {
  const more = document.getElementById("filter-more");
  if (more.querySelector('[aria-invalid="true"]') || !filterError.hidden) setFilterOpen(true);
}

// 뒤로 가기/앞으로 가기로 주소가 바뀌면 그 주소의 조건으로 다시 불러온다.
window.addEventListener("popstate", load);

// 목록은 이벤트(DOMContentLoaded 등)를 기다리지 않고 모듈이 실행될 때 바로 1회 불러온다.
// (모듈은 문서를 다 읽은 뒤 실행되므로 이 시점에 HTML 요소가 모두 있다)
load();

// ---------- 목록과 따로 도는 초기화 ----------

// 아이콘은 HTML에 적어 둔 글자("검색", "필터")를 바꾼다. 실패하면 글자가 그대로 남는다.
safely("검색 아이콘", () => document.getElementById("search-button").replaceChildren(icon("search")));
safely("필터 아이콘", () => filterToggle.replaceChildren(icon("filter"), el("span", { text: t("term.filter") }), filterCount));

// 아이폰 Safari에서 처음 열었을 때만 "홈 화면에 추가" 안내를 목록 위에 보여준다.
safely("홈 화면 추가 안내", () => showInstallGuide(document.querySelector("main")));

// 학교 선택 목록. 학교 이름은 번역하지 않는다. 목록을 받지 못하면 "전체"만 남는다.
// 글 목록은 이것을 기다리지 않는다. 받은 뒤 주소의 school_id를 칸에 다시 채운다.
// 학교 개수를 돌려준다(고를 학교가 없으면 학교 안내를 띄우지 않으려고 쓴다).
const schoolsReady = safely(
  "학교 목록",
  () =>
    listSchools()
      .then(({ items }) => {
        form.elements.school_id.append(...items.map((school) => el("option", { value: String(school.id), text: school.name })));
        form.elements.school_id.value = readUrl().filters.school_id ?? "";
        return items.length;
      })
      .catch(() => 0),
  Promise.resolve(0),
);

// 내 학교가 비어 있으면 제목 아래 학교 안내. 보조 안내라 실패해도 조용히 넘어간다.
safely("학교 안내", () => showSchoolHint().catch((error) => console.error("[home] 학교 안내 실패", error)));

// ---------- 주소창 ↔ 조건 ----------

function readUrl() {
  const params = new URLSearchParams(window.location.search);
  const filters = {};
  for (const key of FILTER_KEYS) {
    const value = params.get(key);
    if (value) filters[key] = value;
  }
  if (params.get(SHOW_SOLD_KEY) === "1") filters[SHOW_SOLD_KEY] = "1";
  // page는 서버가 검증한다. (0이나 문자이면 422 메시지를 보여준다)
  return { filters, page: params.get("page") ?? "1" };
}

function readForm() {
  const filters = {};
  for (const key of FILTER_KEYS) {
    const value = String(form.elements.namedItem(key).value).trim();
    if (value) filters[key] = value;
  }
  if (form.elements.namedItem(SHOW_SOLD_KEY).checked) filters[SHOW_SOLD_KEY] = "1";
  return filters;
}

function fillForm(filters) {
  for (const key of FILTER_KEYS) form.elements.namedItem(key).value = filters[key] ?? "";
  form.elements.namedItem(SHOW_SOLD_KEY).checked = filters[SHOW_SOLD_KEY] === "1";
}

// 화면 조건 → API 조건. 서버 기본은 판매 완료 포함이므로, 홈은 체크가 꺼져 있으면 include_sold=false를 보낸다.
function toApiParams(filters) {
  const { [SHOW_SOLD_KEY]: showSold, ...rest } = filters;
  return { ...rest, include_sold: showSold === "1" ? "true" : "false" };
}

function navigate(filters, page) {
  const params = new URLSearchParams(filters);
  if (Number(page) > 1) params.set("page", page);
  const query = params.toString();
  history.pushState(null, "", query ? `?${query}` : window.location.pathname);
  load();
}

// ---------- 학교 안내 ----------

// 로그인했는데 내 학교가 비어 있으면 제목 아래에 작은 안내 한 줄(+ 선택하기, 닫기). 닫으면 다시 보이지 않는다.
// 고를 학교가 없거나, 내 학교를 받지 못하면 보여주지 않는다(보조 안내라 조용히 넘어간다).
async function showSchoolHint() {
  if (readSchoolHintDismissed()) return;
  const [me, schoolCount] = await Promise.all([mePromise, schoolsReady]);
  if (me === null || schoolCount === 0) return;
  try {
    if ((await getMySchool()).school !== null) return;
  } catch {
    return;
  }
  const close = el("button", { type: "button", className: "school-hint__close", text: "×", attrs: { "aria-label": t("home.school_hint_close") } });
  const hint = el(
    "aside",
    { className: "school-hint", attrs: { "aria-label": t("term.school") } },
    el(
      "p",
      { className: "school-hint__text" },
      t("home.school_hint"),
      " ",
      // 내 정보의 학교 설정 행으로 가서 학교 목록을 펼친다(me.js가 #school-row를 보고 연다).
      el("a", { className: "school-hint__link", href: "/static/me.html#school-row", text: t("home.school_hint_link") }),
    ),
    close,
  );
  close.addEventListener("click", () => {
    saveSchoolHintDismissed();
    hint.remove();
  });
  document.querySelector(".page-title").after(hint);
}

// 사생활 보호 모드 등에서 localStorage가 막혀 있으면 예외가 난다. 그때는 기록 없이 이번 화면에서만 닫힌다.
function readSchoolHintDismissed() {
  try {
    return window.localStorage.getItem(SCHOOL_HINT_KEY) === "1";
  } catch {
    return false;
  }
}

function saveSchoolHintDismissed() {
  try {
    window.localStorage.setItem(SCHOOL_HINT_KEY, "1");
  } catch {
    // 저장하지 못하면 다음에 다시 보일 수 있다.
  }
}

// ---------- 불러오기와 그리기 ----------

async function load() {
  const { filters, page } = readUrl();
  const requestId = ++latestRequestId;

  // 학교 목록이 아직 없으면 학교 칸은 "전체"로 보이고, 목록이 도착하면 다시 채워진다(위 학교 목록 단계).
  fillForm(filters);
  showFilterCount(filters);
  clearFormErrors(form, filterError);
  summary.textContent = t("common.loading");
  emptyActions.hidden = true;
  list.replaceChildren();
  pagination.replaceChildren();

  try {
    // 헤더의 로그인 확인은 실패해도 null을 돌려주므로 함께 기다려도 목록이 막히지 않는다.
    const [data, me] = await Promise.all([listPosts({ ...toApiParams(filters), page, size: PAGE_SIZE }), mePromise]);
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
    // 검색·필터 결과가 없을 때와 글이 하나도 없을 때는 상황이 달라 그림도 다르게 둔다.
    if (hasFilters) renderEmptyState(summary, t("home.empty_search"), { image: EMPTY_SEARCH_IMAGE });
    else {
      renderEmptyState(summary, t("home.empty"), { image: EMPTY_POSTS_IMAGE });
      emptyActions.hidden = false; // "첫 교재 올리기"
    }
    return;
  }

  summary.textContent =
    items.length === 0
      ? t("home.page_empty", { total, pages: totalPages })
      : t("home.total", { count: total });
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
