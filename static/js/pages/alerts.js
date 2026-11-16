// 알림 화면(헤더 종): 맨 위에 안 읽은 쪽지 수 줄(누르면 쪽지함), 아래에 찾는 교재 알림과 안 쓴 후기 알림을 섞은 목록. 로그인이 필요하다.
// 찾는 교재 알림은 목록을 그린 뒤 모두 읽음 처리한다. 이번에 처음 보는 알림은 강조한 채로 남고, 종 배지에서 그만큼 빠진다.
// 후기 알림은 읽음 처리가 없다. 후기를 쓰거나 기한이 지나면 서버 계산에서 저절로 빠진다.
// 찾는 교재 조건 등록·삭제는 찾는 교재 화면(book-alerts.html, 내 정보에서 진입)에서 한다.
import { listNotifications, listReviewReminders, markAllNotificationsRead } from "../api.js";
import { redirectToLogin, refreshAlertBadge, renderHeader, unreadMessageCount } from "../auth.js";
import { t, tNodes } from "../i18n.js";
import { getToken } from "../token.js";
import {
  el,
  EMPTY_ALERTS_IMAGE,
  formatDate,
  formatPrice,
  renderEmptyState,
  renderPagination,
  reviewDueText,
  safeImageUrl,
  setErrorText,
  statusBadge,
} from "../ui.js";

const PAGE_SIZE = 20;

const summary = document.getElementById("result-summary");
const listError = document.getElementById("list-error");
const emptyActions = document.getElementById("empty-actions");
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
    else showListError(t("err.network"));
    return;
  }
  window.addEventListener("popstate", loadNotifications);
  showUnreadMessages();
  loadNotifications();
}

// 맨 위 "읽지 않은 쪽지 N개" 줄. 숫자는 헤더가 이미 받은 것을 기다려 쓴다(같은 요청을 두 번 보내지 않음). 실패하면 줄을 숨긴다.
async function showUnreadMessages() {
  const count = await unreadMessageCount();
  if (count === null) return;
  document.getElementById("unread-messages-text").textContent = t("alerts.unread_messages", { count });
  document.getElementById("unread-messages").hidden = false;
}

// 401(토큰 만료)이면 로그인 화면으로 보낸다. 처리했으면 true.
function handleAuthError(error) {
  if (error.status !== 401) return false;
  redirectToLogin();
  return true;
}

// ---------- 알림 ----------

function readPage() {
  return new URLSearchParams(window.location.search).get("page") ?? "1";
}

async function loadNotifications() {
  summary.textContent = t("common.loading");
  listError.hidden = true;
  notificationList.replaceChildren();
  pagination.replaceChildren();
  emptyActions.hidden = true;

  let data;
  let reviews;
  try {
    // 후기 알림은 최근 14일 거래뿐이라 개수가 적어 한 번에 받는다.
    [data, { items: reviews }] = await Promise.all([listNotifications({ page: readPage(), size: PAGE_SIZE }), listReviewReminders()]);
  } catch (error) {
    if (handleAuthError(error)) return;
    showListError(error.fieldErrors?.page ?? error.message, error.fieldErrors?.page ? error.fieldOriginals?.page : error.original);
    return;
  }
  renderNotifications(data, reviews);

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

function renderNotifications({ items, total, page, size }, reviews) {
  const totalPages = Math.max(1, Math.ceil(total / size));
  // 후기 알림은 첫 페이지에만 시간순으로 섞는다. (찾는 교재 알림만 서버에서 페이지를 나눈다)
  const reviewItems = page === 1 ? reviews : [];
  if (total === 0 && reviewItems.length === 0) {
    renderEmptyState(summary, t("alerts.empty"), {
      image: EMPTY_ALERTS_IMAGE,
    });
    // 빈 화면 안내 아래에 "찾는 교재 등록하기"
    emptyActions.hidden = false;
    return;
  }
  // 안 쓴 후기 알림도 새 알림으로 센다.
  const unreadCount = items.filter((item) => item.read_at === null).length + reviewItems.length;
  const allCount = total + reviewItems.length;
  summary.textContent = unreadCount > 0 ? t("alerts.total_new", { total: allCount, count: unreadCount }) : t("alerts.total", { count: allCount });
  // 서버 시각은 같은 형식의 ISO 문자열이라 글자 순서가 곧 시간 순서다.
  const rows = [
    ...items.map((item) => ({ time: item.created_at, node: renderNotification(item) })),
    ...reviewItems.map((item) => ({ time: item.created_at, node: renderReviewReminder(item) })),
  ].sort((a, b) => (a.time < b.time ? 1 : a.time > b.time ? -1 : 0));
  notificationList.replaceChildren(...rows.map((row) => row.node));
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
        el("p", { className: "notification-card__keyword", text: t(unread ? "alerts.card_new" : "alerts.card", { keyword: notification.keyword }) }),
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

// 안 쓴 후기 알림: 누르면 그 대화(쪽지 화면)로 가서 "후기 남기기"로 이어진다. 기한이 3일 이하면 "D-3" 배지.
function renderReviewReminder(reminder) {
  const due = reviewDueText(reminder.days_left);
  return el(
    "li",
    {},
    el(
      "a",
      {
        className: "card notification-card notification-card--unread",
        href: `/static/chat.html?id=${encodeURIComponent(reminder.conversation_id)}`,
      },
      el(
        "div",
        { className: "notification-card__body" },
        el(
          "p",
          { className: "notification-card__keyword" },
          t("term.review"),
          due ? el("span", { className: "due-badge", text: due }) : null,
        ),
        // 닉네임·글 제목은 사용자가 쓴 글이라 번역하지 않는다. 문장 안에서 따로 감싸 두어 구분할 수 있게 한다.
        el(
          "p",
          { className: "notification-card__title" },
          ...tNodes("bell.review_item", { nickname: el("span", { className: "notification-card__user", text: reminder.partner_nickname }) }),
        ),
        el(
          "p",
          { className: "notification-card__meta" },
          el("span", { className: "notification-card__user", text: reminder.post_title ?? reminder.book_title }),
          ` · ${formatDate(reminder.created_at)}`,
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

function showListError(message, original = null) {
  summary.textContent = "";
  setErrorText(listError, message, original);
  listError.hidden = false;
}
