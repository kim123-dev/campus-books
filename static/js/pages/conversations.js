// 쪽지함 화면: 내가 구매자나 판매자로 참여한 대화방 목록(최신 메시지순). 로그인이 필요하다.
// 카드 옆 "⋯" 메뉴에서 상대 신고·차단, 대화방 나가기를 할 수 있다.
// 페이지 번호는 주소창(?page=2)에 저장한다. 새로고침과 뒤로 가기에도 같은 페이지가 나오게 하기 위해서다.
import { blockUser, leaveConversation, listConversations, reportUser } from "../api.js";
import { redirectToLogin, refreshUnreadBadge, renderHeader } from "../auth.js";
import {
  REPORT_DONE_TEXT,
  blockDoneContent,
  confirmBlock,
  confirmLeave,
  openActionMenu,
  openReportDialog,
} from "../safety.js";
import { getToken } from "../token.js";
import { el, EMPTY_MESSAGES_IMAGE, formatShortDate, renderEmptyState, renderPagination, statusBadge } from "../ui.js";

const PAGE_SIZE = 20;
const MAX_BADGE_COUNT = 99;

const summary = document.getElementById("result-summary");
const listError = document.getElementById("list-error");
const emptyActions = document.getElementById("empty-actions");
const list = document.getElementById("conversation-list");
const pagination = document.getElementById("pagination");
const notice = document.getElementById("inbox-notice");

// 응답이 늦게 도착한 이전 요청이 최신 결과를 덮어쓰지 않도록 요청마다 번호를 붙인다.
let latestRequestId = 0;

init();

async function init() {
  // 로그인하지 않았으면 로그인 화면으로 보낸다. 로그인 후 이 화면으로 돌아온다.
  if (!getToken()) {
    redirectToLogin();
    return;
  }

  // 헤더(/users/me)를 기다리지 않고 목록을 함께 요청한다. 왕복 한 번만큼 빨리 뜬다.
  // 토큰이 만료됐으면 목록이 401을 받아 load가 로그인 화면으로 보내고, 서버 연결 실패도 load가 안내한다.
  // 뒤로 가기/앞으로 가기로 주소가 바뀌면 그 페이지를 다시 불러온다.
  window.addEventListener("popstate", load);
  const [me] = await Promise.all([renderHeader(document.getElementById("site-header")), load()]);
  // renderHeader는 401이면 토큰을 지우고 null을 돌려준다. (목록 요청보다 늦게 알게 된 경우)
  if (me === null && !getToken()) redirectToLogin();
}

// ---------- 불러오기와 그리기 ----------

function readPage() {
  // page는 서버가 검증한다. (0이나 문자이면 422 메시지를 보여준다)
  return new URLSearchParams(window.location.search).get("page") ?? "1";
}

async function load() {
  const requestId = ++latestRequestId;
  summary.textContent = "불러오는 중…";
  listError.hidden = true;
  emptyActions.hidden = true;
  list.replaceChildren();
  pagination.replaceChildren();

  let data;
  try {
    data = await listConversations({ page: readPage(), size: PAGE_SIZE });
  } catch (error) {
    if (requestId !== latestRequestId) return;
    if (error.status === 401) {
      redirectToLogin();
      return;
    }
    showError(error.fieldErrors?.page ?? error.message);
    return;
  }
  if (requestId !== latestRequestId) return;
  render(data);
}

function render({ items, total, page, size }) {
  const totalPages = Math.max(1, Math.ceil(total / size));

  if (total === 0) {
    renderEmptyState(summary, "아직 주고받은 쪽지가 없습니다. 판매글 상세 화면에서 문의를 시작해 보세요.", {
      image: EMPTY_MESSAGES_IMAGE,
    });
    emptyActions.hidden = false;
    return;
  }

  summary.textContent =
    items.length === 0
      ? `이 페이지에는 대화방이 없습니다. (전체 ${total}개, ${totalPages}페이지까지)`
      : `대화방 ${total}개`;
  list.replaceChildren(...items.map(renderConversationCard));
  renderPagination(pagination, page, totalPages, goToPage);
}

/** 대화방 카드 하나(li). 누르면 대화 화면으로 간다. */
function renderConversationCard(conversation) {
  const { post, partner, my_role: role, last_message: last, unread_count: unread } = conversation;
  const unreadText = unread > MAX_BADGE_COUNT ? `${MAX_BADGE_COUNT}+` : String(unread);

  // 글이 삭제되면 서버가 post를 null로 준다. 대화 기록은 남아 있으므로 카드는 그대로 보여준다.
  const postLine = post
    ? el("p", { className: "conversation-card__post" }, statusBadge(post.status), el("span", { text: post.title }))
    : el("p", { className: "conversation-card__post conversation-card__post--deleted", text: "삭제된 글" });

  const preview = last
    ? el("p", { className: "conversation-card__preview", text: `${last.is_mine ? "나: " : ""}${last.content}` })
    : el("p", { className: "conversation-card__preview conversation-card__preview--empty", text: "아직 메시지가 없습니다" });

  // 카드 전체가 링크라 그 안에 버튼을 넣을 수 없다(링크 안 버튼은 HTML 규칙 위반). 메뉴 버튼은 카드 옆에 둔다.
  const menuButton = el("button", {
    type: "button",
    className: "conversation-menu-button",
    text: "⋯",
    attrs: { "aria-label": `${partner.nickname}님과의 대화 메뉴`, "aria-haspopup": "dialog" },
  });
  menuButton.addEventListener("click", () => openCardMenu(conversation, menuButton));

  return el(
    "li",
    { className: "conversation-list__item" },
    el(
      "a",
      {
        className: `card conversation-card${unread > 0 ? " conversation-card--unread" : ""}`,
        href: `/static/chat.html?id=${encodeURIComponent(conversation.id)}`,
      },
      el(
        "div",
        { className: "conversation-card__top" },
        el("span", { className: "conversation-card__partner", text: partner.nickname }),
        el("span", { className: "conversation-card__role", text: role === "BUYER" ? "문의한 글" : "받은 문의" }),
        el("span", { className: "conversation-card__time", text: formatShortDate(last?.created_at ?? conversation.last_message_at) }),
      ),
      postLine,
      el(
        "div",
        { className: "conversation-card__bottom" },
        preview,
        unread > 0
          ? el(
              "span",
              { className: "count-badge" },
              // span의 aria-label은 화면 낭독기가 무시하는 경우가 많아, 보이지 않는 글자로 뜻을 붙인다.
              el("span", { className: "visually-hidden", text: "안 읽은 메시지 " }),
              unreadText,
              el("span", { className: "visually-hidden", text: "개" }),
            )
          : null,
      ),
    ),
    menuButton,
  );
}

// ---------- 카드 메뉴: 신고·차단·나가기 ----------

async function openCardMenu(conversation, menuButton) {
  const { partner } = conversation;
  // 탈퇴한 상대는 신고·차단할 사람이 없으므로 나가기만 둔다.
  const items = partner.withdrawn
    ? []
    : [
        { key: "report", label: "사용자 신고" },
        { key: "block", label: "차단" },
      ];
  items.push({ key: "leave", label: "대화방 나가기", danger: true });

  const choice = await openActionMenu({ heading: `${partner.nickname}님과의 대화`, items });
  if (choice === "report") {
    const reported = await openReportDialog({
      heading: "사용자 신고",
      targetText: `신고 대상: ${partner.nickname}`,
      send: (data) => reportUser(partner.id, data),
    });
    if (reported) showNotice(REPORT_DONE_TEXT);
  } else if (choice === "block") {
    if (!confirmBlock(partner.nickname)) return;
    await runAction(() => blockUser(partner.id), () => showNotice(...blockDoneContent()));
  } else if (choice === "leave") {
    if (!confirmLeave(partner.nickname)) return;
    await runAction(
      () => leaveConversation(conversation.id),
      () => {
        // 이 방이 빠졌으니 목록을 다시 받는다. (페이지 수·전체 개수가 바뀐다) 쪽지 배지도 함께 줄어든다.
        showNotice("대화방에서 나갔어요. 상대가 새 쪽지를 보내면 다시 나타나요.");
        load();
        refreshUnreadBadge();
      },
    );
  }
  // 메뉴가 닫히면 누른 버튼으로 초점을 돌려준다. (목록을 다시 그렸으면 그 버튼은 이미 없다)
  if (menuButton.isConnected) menuButton.focus();
}

async function runAction(action, onDone) {
  try {
    await action();
  } catch (error) {
    if (error.status === 401) {
      redirectToLogin();
      return;
    }
    showNotice(error.message);
    return;
  }
  onDone();
}

function showNotice(...content) {
  notice.replaceChildren(...content);
  notice.hidden = false;
}

function goToPage(page) {
  history.pushState(null, "", page > 1 ? `?page=${page}` : window.location.pathname);
  load();
  window.scrollTo({ top: 0 });
}

function showError(message) {
  summary.textContent = "";
  listError.textContent = message;
  listError.hidden = false;
}
