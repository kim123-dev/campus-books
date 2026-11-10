// 찾는 교재 알림 화면: 위에서 조건(키워드·최대 가격)을 등록·삭제하고, 아래에서 받은 알림을 본다. 로그인이 필요하다.
// 알림 목록을 그린 뒤 모두 읽음 처리한다. 이번에 처음 보는 알림은 강조한 채로 남고, 헤더 배지는 사라진다.
import {
  createAlert,
  deleteAlert,
  listAlerts,
  listNotifications,
  markAllNotificationsRead,
} from "../api.js";
import { redirectToLogin, refreshAlertBadge, renderHeader } from "../auth.js";
import { getToken } from "../token.js";
import {
  clearFormErrors,
  el,
  formatDate,
  formatPrice,
  renderPagination,
  safeImageUrl,
  showFormErrors,
  statusBadge,
} from "../ui.js";

const PAGE_SIZE = 20;

const alertForm = document.getElementById("alert-form");
const alertFormError = document.getElementById("alert-form-error");
const alertList = document.getElementById("alert-list");
const alertCount = document.getElementById("alert-count");
const summary = document.getElementById("result-summary");
const listError = document.getElementById("list-error");
const notificationList = document.getElementById("notification-list");
const pagination = document.getElementById("pagination");

init();

async function init() {
  if (!getToken()) {
    redirectToLogin();
    return;
  }
  const me = await renderHeader(document.getElementById("site-header"));
  if (me === null) {
    if (!getToken()) redirectToLogin();
    else showListError("서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
    return;
  }
  alertForm.addEventListener("submit", onSubmitAlert);
  window.addEventListener("popstate", loadNotifications);
  loadAlerts();
  loadNotifications();
}

// 401(토큰 만료)이면 로그인 화면으로 보낸다. 처리했으면 true.
function handleAuthError(error) {
  if (error.status !== 401) return false;
  redirectToLogin();
  return true;
}

// ---------- 찾는 교재 조건 ----------

async function loadAlerts() {
  let data;
  try {
    data = await listAlerts();
  } catch (error) {
    if (handleAuthError(error)) return;
    showFormErrors(alertForm, alertFormError, error);
    return;
  }
  renderAlerts(data);
}

function renderAlerts({ items, max_count: maxCount }) {
  alertCount.textContent = `${items.length}/${maxCount}`;
  alertList.replaceChildren(...items.map(renderAlertItem));
}

function renderAlertItem(alert) {
  const priceText = alert.max_price === null ? "가격 상관없음" : `${formatPrice(alert.max_price)} 이하`;
  // 등록하기 전에 이미 올라온 글은 알림이 오지 않으므로, 같은 조건의 검색 결과로 바로 볼 수 있게 한다.
  const query = new URLSearchParams({ q: alert.keyword });
  if (alert.max_price !== null) query.set("max_price", String(alert.max_price));

  const removeButton = el("button", { type: "button", className: "link-button link-button--danger", text: "삭제" });
  removeButton.addEventListener("click", () => onDeleteAlert(alert, removeButton));
  return el(
    "li",
    { className: "alert-list__item" },
    el(
      "div",
      { className: "alert-list__text" },
      el("span", { className: "alert-list__keyword", text: alert.keyword }),
      " ",
      el("span", { className: "alert-list__price", text: priceText }),
    ),
    el(
      "div",
      { className: "alert-list__actions" },
      el("a", { className: "link-button", href: `/static/index.html?${query}`, text: "지금 있는 글 검색" }),
      removeButton,
    ),
  );
}

async function onSubmitAlert(event) {
  event.preventDefault();
  clearFormErrors(alertForm, alertFormError);
  const { keyword, max_price: maxPrice } = alertForm.elements;
  const data = { keyword: keyword.value };
  if (maxPrice.value !== "") {
    const price = Number(maxPrice.value);
    if (!Number.isInteger(price) || price < 0) {
      showFormErrors(alertForm, alertFormError, { fieldErrors: { max_price: "0 이상의 정수로 입력해 주세요." } });
      return;
    }
    data.max_price = price;
  }

  const submit = alertForm.querySelector("[type=submit]");
  submit.disabled = true;
  try {
    await createAlert(data);
    alertForm.reset();
    keyword.focus();
  } catch (error) {
    if (handleAuthError(error)) return;
    // 409(같은 키워드)는 키워드 칸 아래에, 400(개수 초과)·403(정지)은 공통 영역에 보여준다.
    if (error.status === 409) showFormErrors(alertForm, alertFormError, { fieldErrors: { keyword: error.message } });
    else showFormErrors(alertForm, alertFormError, error);
    return;
  } finally {
    submit.disabled = false;
  }
  loadAlerts();
}

async function onDeleteAlert(alert, button) {
  button.disabled = true;
  try {
    await deleteAlert(alert.id);
  } catch (error) {
    if (handleAuthError(error)) return;
    // 이미 지워진 조건(404)이면 목록만 새로 맞춘다.
    if (error.status !== 404) {
      button.disabled = false;
      showFormErrors(alertForm, alertFormError, error);
      return;
    }
  }
  loadAlerts();
}

// ---------- 알림 ----------

function readPage() {
  return new URLSearchParams(window.location.search).get("page") ?? "1";
}

async function loadNotifications() {
  summary.textContent = "불러오는 중…";
  listError.hidden = true;
  notificationList.replaceChildren();
  pagination.replaceChildren();

  let data;
  try {
    data = await listNotifications({ page: readPage(), size: PAGE_SIZE });
  } catch (error) {
    if (handleAuthError(error)) return;
    showListError(error.fieldErrors?.page ?? error.message);
    return;
  }
  renderNotifications(data);

  // 목록을 보여준 뒤 읽음 처리한다. 실패해도 다음에 다시 열면 되므로 화면에 에러를 띄우지 않는다.
  if (data.items.some((item) => item.read_at === null)) {
    try {
      await markAllNotificationsRead();
    } catch {
      // 배지가 그대로 남을 뿐이다.
    }
    refreshAlertBadge();
  }
}

function renderNotifications({ items, total, page, size }) {
  const totalPages = Math.max(1, Math.ceil(total / size));
  if (total === 0) {
    summary.textContent = "아직 받은 알림이 없습니다. 찾는 교재를 등록해 두면 새 글이 올라올 때 알려 드려요.";
    return;
  }
  const unreadCount = items.filter((item) => item.read_at === null).length;
  summary.textContent = unreadCount > 0 ? `총 ${total}개 · 새 알림 ${unreadCount}개` : `총 ${total}개`;
  notificationList.replaceChildren(...items.map(renderNotification));
  renderPagination(pagination, page, totalPages, goToPage);
}

function renderNotification(notification) {
  const { post } = notification;
  const unread = notification.read_at === null;
  const courseText = post.course_name ? ` · ${post.course_name}` : "";
  return el(
    "li",
    {},
    el(
      "a",
      {
        className: `card notification-card${unread ? " notification-card--unread" : ""}`,
        href: `/static/post.html?id=${encodeURIComponent(post.id)}`,
      },
      el("img", { className: "notification-card__thumb", src: safeImageUrl(post.thumbnail_url), alt: "", loading: "lazy", width: 64, height: 64 }),
      el(
        "div",
        { className: "notification-card__body" },
        el("p", { className: "notification-card__keyword", text: `"${notification.keyword}" ${unread ? "새 알림" : "알림"}` }),
        el("p", { className: "notification-card__title", text: post.title }),
        el("p", { className: "notification-card__meta", text: `${post.book_title}${courseText}` }),
        el(
          "p",
          { className: "notification-card__meta" },
          statusBadge(post.status),
          ` ${formatPrice(post.price)} · ${formatDate(notification.created_at)}`,
        ),
      ),
    ),
  );
}

function goToPage(page) {
  history.pushState(null, "", page > 1 ? `?page=${page}` : window.location.pathname);
  loadNotifications();
  window.scrollTo({ top: 0 });
}

function showListError(message) {
  summary.textContent = "";
  listError.textContent = message;
  listError.hidden = false;
}
