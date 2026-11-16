// 헤더 종을 누르면 종 바로 아래에 뜨는 작은 알림 판(팝오버).
// 안 읽은 쪽지가 있는 대화, 안 읽은 찾는 교재 알림, 안 쓴 후기 알림을 구분 제목 없이 한 목록에 최신순으로 섞어 보여준다.
// 데이터는 세 API(대화방 목록, 찾는 교재 알림 목록, 후기 알림)를 화면에서 합친 것이고, 판을 열 때마다 새로 받는다.
// 그래서 대화에서 후기를 쓰고 돌아와 판을 열면 그 항목은 이미 빠져 있다.
// 판은 다시 누르기·바깥 누르기·Esc·다른 화면으로 이동하면 닫힌다. 맨 아래 "전체 보기"는 알림 화면(alerts.html)으로.

import { listConversations, listNotifications, listReviewReminders, markNotificationRead } from "./api.js";
import { t } from "./i18n.js";
import { el, formatAgo, formatDate, reviewDueText } from "./ui.js";

const ALERTS_PAGE = "/static/alerts.html";
const BOOK_ALERTS_PAGE = "/static/book-alerts.html";
const CHAT_PAGE = "/static/chat.html";
const POST_PAGE = "/static/post.html";
// 판에 담을 만큼만 받는다. (안 읽은 것만 보여주므로 이보다 많으면 "전체 보기"로)
const FETCH_SIZE = 30;

/**
 * 종 버튼과 판을 묶어 돌려준다.
 * onAlertRead: 찾는 교재 알림 하나를 읽음 처리한 뒤 부른다. (auth.js가 종 배지 숫자를 줄인다)
 */
export function notificationBell({ button, onAlertRead }) {
  const panelId = "notification-panel";
  const list = el("ul", { className: "notification-panel__list" });
  const status = el("p", { className: "notification-panel__status", hidden: true });
  const emptyLink = el("a", { className: "notification-panel__register", href: BOOK_ALERTS_PAGE, text: t("alerts.register_link") });
  const empty = el("div", { className: "notification-panel__empty", hidden: true }, el("p", { text: t("bell.empty") }), emptyLink);
  const panel = el(
    "div",
    { className: "notification-panel", attrs: { id: panelId, role: "dialog", "aria-label": t("term.notifications") }, hidden: true },
    list,
    status,
    empty,
    el("a", { className: "notification-panel__all", href: ALERTS_PAGE, text: t("bell.view_all") }),
  );
  const wrap = el("div", { className: "site-bell-wrap" }, button, panel);
  button.setAttribute("aria-haspopup", "dialog");
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("aria-controls", panelId);

  // 가장 최근에 연 요청만 그린다. (빠르게 닫았다 다시 열면 앞 요청 결과는 버린다)
  let loadToken = 0;

  const close = () => {
    if (panel.hidden) return;
    panel.hidden = true;
    button.setAttribute("aria-expanded", "false");
    loadToken += 1;
  };

  const open = () => {
    placePanel(button, panel);
    panel.hidden = false;
    button.setAttribute("aria-expanded", "true");
    load(++loadToken);
  };

  async function load(token) {
    list.replaceChildren();
    empty.hidden = true;
    status.hidden = false;
    status.textContent = t("common.loading");
    let items;
    try {
      items = await fetchItems();
    } catch {
      if (token !== loadToken) return;
      status.textContent = t("bell.load_error");
      return;
    }
    if (token !== loadToken) return;
    status.hidden = true;
    empty.hidden = items.length > 0;
    list.replaceChildren(...items.map((item) => itemRow(item, onAlertRead)));
  }

  button.addEventListener("click", (event) => {
    // 링크가 아니라 판을 여닫는 버튼이다.
    event.preventDefault();
    if (panel.hidden) open();
    else close();
  });
  // 판 밖(종 포함 묶음 밖)을 누르면 닫는다. 종 자체는 위의 버튼 처리가 여닫는다.
  document.addEventListener("click", (event) => {
    if (!panel.hidden && !wrap.contains(event.target)) close();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) {
      close();
      button.focus();
    }
  });
  // 다른 화면으로 갔다가 뒤로 가기로 돌아오면(페이지 캐시) 열린 채로 보이지 않게 닫는다.
  window.addEventListener("pagehide", close);
  window.addEventListener("resize", () => {
    if (!panel.hidden) placePanel(button, panel);
  });
  return wrap;
}

/** 세 API를 함께 불러 안 읽은(안 쓴) 것만 골라 최신순으로 섞는다. */
async function fetchItems() {
  const [conversations, notifications, reviews] = await Promise.all([
    listConversations({ size: FETCH_SIZE }),
    listNotifications({ size: FETCH_SIZE }),
    listReviewReminders(),
  ]);
  const messageItems = conversations.items
    .filter((c) => c.unread_count > 0)
    .map((c) => ({
      kind: "message",
      time: c.last_message_at,
      text: t("bell.message_item", { nickname: c.partner.nickname }),
      href: `${CHAT_PAGE}?id=${encodeURIComponent(c.id)}`,
    }));
  const alertItems = notifications.items
    .filter((n) => n.read_at === null)
    .map((n) => ({
      kind: "alert",
      id: n.id,
      time: n.created_at,
      text: t("bell.alert_item", { keyword: n.keyword }),
      href: `${POST_PAGE}?id=${encodeURIComponent(n.post.id)}`,
    }));
  // 후기 알림은 판매 완료 시각으로 섞는다. 누르면 그 대화로 가서 "후기 남기기"로 이어진다(읽음 처리 없음).
  const reviewItems = reviews.items.map((r) => ({
    kind: "review",
    time: r.created_at,
    text: t("bell.review_item", { nickname: r.partner_nickname }),
    due: reviewDueText(r.days_left),
    href: `${CHAT_PAGE}?id=${encodeURIComponent(r.conversation_id)}`,
  }));
  // 서버 시각은 같은 형식의 ISO 문자열이라 글자 순서가 곧 시간 순서다.
  return [...messageItems, ...alertItems, ...reviewItems].sort((a, b) => (a.time < b.time ? 1 : a.time > b.time ? -1 : 0));
}

/** 한 줄 요약 + 작은 회색 시간. 판에는 안 읽은 것만 오므로 모두 왼쪽에 점이 있다. */
function itemRow(item, onAlertRead) {
  const link = el(
    "a",
    { className: "notification-panel__item notification-panel__item--unread", href: item.href },
    el("span", { className: "notification-panel__dot", attrs: { "aria-hidden": "true" } }),
    el(
      "span",
      { className: "notification-panel__body" },
      el("span", { className: "notification-panel__text", text: item.text }),
      el(
        "span",
        { className: "notification-panel__meta" },
        // 후기 기한이 3일 이하로 남았으면 "D-3" 작은 배지를 시간 앞에 둔다. (요약 문장은 두 줄 안에 남게 따로 둔다)
        item.due ? el("span", { className: "due-badge", text: item.due }) : null,
        el("time", { className: "notification-panel__time", text: formatAgo(item.time), attrs: { datetime: item.time, title: formatDate(item.time) } }),
      ),
    ),
  );
  if (item.kind === "alert") {
    // 찾는 교재 알림: 그 알림만 읽음 처리하고 배지를 줄인 뒤 글로 간다. 읽음 처리가 실패해도 글은 연다.
    link.addEventListener("click", async (event) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
      event.preventDefault();
      try {
        await markNotificationRead(item.id);
        onAlertRead?.();
      } catch {
        // 다음에 알림 화면을 열면 모두 읽음 처리된다.
      }
      window.location.href = item.href;
    });
  }
  // 쪽지 항목은 그냥 대화로 간다. 대화 화면이 메시지를 읽음 처리하고 배지를 다시 받는다.
  return el("li", {}, link);
}

/**
 * 판의 위치와 최대 높이. 모바일(좁은 화면)은 화면 좌우 8px 여백 폭으로 종 바로 아래,
 * 하단 탭 바를 가리지 않도록 그 위까지만. PC는 CSS가 종 아래 오른쪽 정렬로 둔다.
 */
function placePanel(button, panel) {
  const top = Math.round(button.getBoundingClientRect().bottom + 4);
  const tabBar = document.querySelector(".tab-bar");
  const tabBarTop = tabBar && tabBar.getClientRects().length ? tabBar.getBoundingClientRect().top : window.innerHeight;
  panel.style.setProperty("--notification-panel-top", `${top}px`);
  panel.style.setProperty("--notification-panel-room", `${Math.max(160, Math.floor(tabBarTop - top - 8))}px`);
}
