// 관리 기록 화면 (관리자 전용): 누가·언제·누구에게·무엇을·왜.
// 조치 종류·대상 사용자·페이지는 주소창(?action=SUSPEND&target_user_id=3&page=2)에 저장한다.
import {
  ADMIN_ACTION_LABELS,
  adminUserLink,
  describeDetail,
  handleAuthError,
  startAdminPage,
  userLabel,
} from "../admin-common.js";
import { listAdminActions } from "../api.js";
import { el, formatDate, renderPagination } from "../ui.js";

const PAGE_SIZE = 20;

const main = document.getElementById("admin-main");
const filterForm = document.getElementById("log-filter");
const actionSelect = document.getElementById("filter-action");
const filterUser = document.getElementById("filter-user");
const summary = document.getElementById("result-summary");
const listError = document.getElementById("list-error");
const list = document.getElementById("log-list");
const pagination = document.getElementById("pagination");

// 응답이 늦게 도착한 이전 요청이 최신 결과를 덮어쓰지 않도록 요청마다 번호를 붙인다.
let latestRequestId = 0;

init();

async function init() {
  if ((await startAdminPage(main)) === null) return;
  actionSelect.append(
    ...Object.entries(ADMIN_ACTION_LABELS).map(([value, label]) => el("option", { value, text: label })),
  );
  // 조치를 바꾸면 바로 첫 페이지부터 다시 불러온다.
  actionSelect.addEventListener("change", () => {
    const params = new URLSearchParams(window.location.search);
    if (actionSelect.value) params.set("action", actionSelect.value);
    else params.delete("action");
    params.delete("page");
    history.pushState(null, "", `?${params}`);
    load();
  });
  filterForm.addEventListener("submit", (event) => event.preventDefault());
  window.addEventListener("popstate", load);
  load();
}

function readQuery() {
  const params = new URLSearchParams(window.location.search);
  const action = Object.hasOwn(ADMIN_ACTION_LABELS, params.get("action")) ? params.get("action") : "";
  return {
    action,
    target_user_id: params.get("target_user_id") ?? "",
    admin_id: params.get("admin_id") ?? "",
    page: params.get("page") ?? "1",
  };
}

async function load() {
  const requestId = ++latestRequestId;
  const query = readQuery();
  actionSelect.value = query.action;
  renderUserFilter(query);
  summary.textContent = "불러오는 중…";
  listError.hidden = true;
  list.replaceChildren();
  pagination.replaceChildren();

  let data;
  try {
    data = await listAdminActions({ ...query, size: PAGE_SIZE });
  } catch (error) {
    if (requestId !== latestRequestId) return;
    if (handleAuthError(error)) return;
    showError(error.fieldErrors?.page ?? error.fieldErrors?.target_user_id ?? error.message);
    return;
  }
  if (requestId !== latestRequestId) return;
  render(data);
}

// 사용자 상세에서 "이 사용자에 대한 기록"으로 들어온 경우, 걸린 조건과 풀기 링크를 보여준다.
function renderUserFilter({ target_user_id: targetUserId, admin_id: adminId }) {
  const parts = [];
  if (targetUserId) parts.push(`사용자 #${targetUserId}에 대한 기록`);
  if (adminId) parts.push(`관리자 #${adminId}가 한 조치`);
  filterUser.hidden = parts.length === 0;
  if (parts.length === 0) return;
  const params = new URLSearchParams(window.location.search);
  params.delete("target_user_id");
  params.delete("admin_id");
  params.delete("page");
  filterUser.replaceChildren(`${parts.join(" · ")}만 보는 중 · `, el("a", { href: `?${params}`, text: "전체 보기" }));
}

function render({ items, total, page, size }) {
  if (total === 0) {
    summary.textContent = "관리 기록이 없습니다.";
    return;
  }
  summary.textContent = items.length === 0 ? `이 페이지에는 기록이 없습니다. (전체 ${total}건)` : `총 ${total}건`;
  list.replaceChildren(...items.map(renderEntry));
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

function renderEntry(entry) {
  const details = describeDetail(entry.detail);
  return el(
    "li",
    { className: "card admin-card" },
    el(
      "div",
      { className: "admin-card__head" },
      el("span", {
        className: `admin-badge admin-badge--${entry.action.toLowerCase().replaceAll("_", "-")}`,
        text: ADMIN_ACTION_LABELS[entry.action] ?? entry.action,
      }),
      el("span", { className: "admin-card__meta", text: formatDate(entry.created_at) }),
    ),
    el(
      "p",
      { className: "admin-card__line" },
      `${userLabel(entry.admin)} → `,
      entry.target_user ? adminUserLink(entry.target_user) : el("span", { text: targetText(entry) }),
    ),
    el("p", { className: "admin-card__reason", text: entry.reason ? `사유: ${entry.reason}` : "사유 없음" }),
    details.length ? el("p", { className: "admin-card__meta", text: details.join(" · ") }) : null,
  );
}

// 사용자와 관계없는 조치(재가입 차단 해제 등)의 대상 표시
function targetText(entry) {
  if (entry.target_type === "EMAIL_BAN") return `재가입 차단 #${entry.target_id}`;
  return `${entry.target_type} #${entry.target_id}`;
}

function showError(message) {
  summary.textContent = "";
  listError.textContent = message;
  listError.hidden = false;
}
