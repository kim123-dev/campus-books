// 대화 화면: 한 대화방의 메시지를 보여주고 보낸다. 로그인이 필요하다.
// - 새 메시지는 몇 초마다 after_id로 확인한다(폴링). 탭이 숨겨지면 멈춘다.
// - 맨 위로 스크롤하면 before_id로 이전 메시지를 불러온다.
// - 메시지 목록을 조회하면 서버가 상대 메시지를 읽음 처리하므로, 화면은 헤더 배지만 다시 불러온다.
// - 처음 불러오기·폴링·전송·이전 메시지가 모두 addMessages → renderMessage 한 경로로 그리고,
//   내 메시지인지는 서버 응답의 is_mine을 그대로 쓴다.
// - 사진 쪽지: 공개 주소가 없어 토큰을 붙여 fetch로 받고 blob: 주소로 보여준다. 화면에 보일 때 받는다.
// - 토큰은 탭끼리 공유된다. 다른 탭에서 계정이 바뀌면 이 화면이 새 계정 토큰으로 폴링·전송하게 되어
//   상대 메시지가 내 말풍선으로 그려지거나 다른 계정 이름으로 전송되므로, 계정이 바뀌면 멈춘다.
import {
  blockUser,
  createReview,
  fetchMessageImage,
  getConversation,
  listMessages,
  reportMessage,
  reportUser,
  sendMessage,
  sendMessageImage,
  unblockUser,
} from "../api.js";
import { redirectToLogin, refreshReviewBadge, refreshUnreadBadge, renderHeader, suspensionText } from "../auth.js";
import { t } from "../i18n.js";
import { preparePhoto } from "../photo-resize.js";
import {
  REPORT_DONE_TEXT,
  UNBLOCK_DONE_TEXT,
  blockDoneContent,
  confirmBlock,
  confirmUnblock,
  openActionMenu,
  openReportDialog,
} from "../safety.js";
import { getToken, onTokenChangedInOtherTab } from "../token.js";
import { openReviewDialog } from "../trade.js";
import {
  MOBILE_QUERY,
  clearFormErrors,
  el,
  formatMonthDayTime,
  formatShortDate,
  icon,
  readPostIdFromUrl,
  setErrorText,
  showBlobImage,
  showFormErrors,
  statusBadge,
} from "../ui.js";

const POLL_INTERVAL_MS = 5000; // 새 메시지 확인 간격
const POLL_RETRY_INTERVAL_MS = 15000; // 연결이 불안정할 때는 서버에 부담을 덜 주도록 늦춘다.
const PAGE_LIMIT = 30; // 한 번에 불러올 메시지 수 (서버 최대 100)
const NEAR_BOTTOM_PX = 80; // 이만큼 안쪽이면 "맨 아래를 보고 있다"고 본다.
const MAX_LENGTH = 1000; // 서버 규칙과 같다. (app/schemas/conversation.py)
// 글자 수는 이만큼 쓴 뒤부터 보여준다. 짧은 쪽지에서는 입력 줄을 가볍게 두기 위해서다.
const COUNTER_FROM = 800;
const DEFAULT_RETRY_SECONDS = 10; // 429에 Retry-After가 없을 때
const MAX_PHOTO_BYTES = 25 * 1024 * 1024; // 서버 규칙과 같다. (app/services/image_service.py)

const pageStatus = document.getElementById("page-status");
const pageError = document.getElementById("page-error");
const pageErrorText = document.getElementById("page-error-text");
const chat = document.getElementById("chat");
const scrollBox = document.getElementById("chat-scroll");
const list = document.getElementById("message-list");
const emptyText = document.getElementById("chat-empty");
const emptyHint = document.getElementById("chat-empty-hint");
const olderButton = document.getElementById("older-button");
const olderSentinel = document.getElementById("older-sentinel");
const newMessageButton = document.getElementById("new-message-button");
const connectionStatus = document.getElementById("connection-status");
const form = document.getElementById("message-form");
const textarea = form.elements.content;
const counter = document.getElementById("content-count");
const submitButton = form.querySelector('button[type="submit"]');
const photoInput = document.getElementById("photo-input");
const photoProgress = document.getElementById("photo-progress");
const photoButton = document.getElementById("photo-button");
const sendError = document.getElementById("send-error");
const chatActions = document.getElementById("chat-actions");
const safetyNotice = document.getElementById("chat-safety-notice");
const blockedNotice = document.getElementById("chat-blocked");
const reviewBox = document.getElementById("chat-review");
const quickReplies = document.getElementById("quick-replies");
// 빈 대화에서 구매자가 첫 쪽지를 쉽게 시작하도록 보여주는 문장(사전 키).
const QUICK_REPLY_KEYS = ["chat.quick_available", "chat.quick_price", "chat.quick_meet"];

// 차단 관계면 false. 서버도 전송을 400으로 막지만, 화면은 입력창을 미리 잠근다.
let canSend = true;
// 이 대화에서 내 역할(BUYER/SELLER). 빠른 문장은 문의한 쪽에만 보인다.
let myRole = null;

const conversationId = readPostIdFromUrl(); // ?id=를 1 이상의 정수로 읽는다. (글 번호와 같은 규칙)

// 화면에 그린 메시지 id. 전송 응답과 폴링이 같은 메시지를 줘도 한 번만 그리기 위해서다.
const shownIds = new Set();
let oldestId = null;
let newestId = null;
let hasOlder = false;
let loadingOlder = false;

let pollTimer = null;
let pollInFlight = false;
let stopped = false; // 방을 더 볼 수 없게 되면(401·403·404) 폴링을 완전히 멈춘다.

let sending = false;
// 이용 정지 중이면 안내 문구. 차단과 같이 입력창을 잠근다. (헤더의 내 정보 또는 전송 403으로 알게 된다)
let suspendedText = null;
let cooldownTimer = null;

// 이 화면을 연 계정의 토큰. 요청 전후로 비교해, 다른 탭에서 계정이 바뀌었는지 확인한다.
let sessionToken = null;
let accountChanged = false;

// 사진 썸네일은 메시지 영역에 보일 때 받는다. 오래된 대화에 사진이 많아도 처음 열 때 한꺼번에 받지 않는다.
const photoObserver = new IntersectionObserver(
  (entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      photoObserver.unobserve(entry.target);
      loadThumbnail(entry.target);
    }
  },
  { root: document.getElementById("chat-scroll"), rootMargin: "200px 0px" },
);

init();

// ---------- 화면 준비 ----------

async function init() {
  if (!getToken()) {
    redirectToLogin();
    return;
  }
  sessionToken = getToken();
  onTokenChangedInOtherTab(checkSameAccount);

  const me = await renderHeader(document.getElementById("site-header"));
  if (me === null) {
    // renderHeader는 401이면 토큰을 지우고 null을, 서버 연결 실패면 토큰을 남긴 채 null을 돌려준다.
    if (!getToken()) redirectToLogin();
    else showPageError(t("err.network"));
    return;
  }
  suspendedText = suspensionText(me);
  if (conversationId === null) {
    showPageError(t("chat.bad_url"));
    return;
  }

  let conversation;
  let first;
  try {
    // 대화방 정보와 최근 메시지를 함께 불러온다. 메시지 조회가 상대 메시지를 읽음 처리한다.
    [conversation, first] = await Promise.all([
      getConversation(conversationId),
      listMessages(conversationId, { limit: PAGE_LIMIT }),
    ]);
  } catch (error) {
    if (error.status === 401) {
      redirectToLogin();
      return;
    }
    // 404(없는 방), 403(남의 방)은 서버 메시지를 그대로 보여준다. (다른 언어는 상태 코드별 문장 + 원문)
    showPageError(error.message, error.original);
    return;
  }
  if (!checkSameAccount()) return;

  myRole = conversation.my_role;
  renderQuickReplies();
  renderChatHeader(conversation);
  applyBlockState(conversation);
  renderReviewState(conversation);
  addMessages(first.items);
  hasOlder = first.has_more;
  updateOlderButton();

  pageStatus.hidden = true;
  chat.hidden = false;
  scrollToBottom();
  // 처음 그린 메시지를 모두 읽어 주지 않도록, 그린 뒤에 새 메시지 알림 영역으로 지정한다.
  list.setAttribute("role", "log");
  list.setAttribute("aria-label", t("chat.log_aria"));

  refreshUnreadBadge(); // 방금 읽음 처리된 만큼 헤더 숫자가 줄어든다.
  bindEvents();
  bindMobileKeyboard();
  schedulePoll(POLL_INTERVAL_MS);
}

function bindEvents() {
  form.addEventListener("submit", onSubmit);
  // "+"·보내기 아이콘 버튼. 보이는 원(32px)은 안쪽 span, 누르는 영역은 버튼 전체(44px). 이름은 aria-label이 맡는다.
  photoButton.replaceChildren(el("span", { className: "chat__icon-circle" }, icon("plus")));
  submitButton.replaceChildren(el("span", { className: "chat__icon-circle" }, icon("send")));
  photoButton.addEventListener("click", () => photoInput.click());
  photoInput.addEventListener("change", onPhotoChosen);
  textarea.addEventListener("input", () => {
    updateCounter();
    fitTextarea();
    updateSendButtons();
  });
  textarea.addEventListener("keydown", onTextareaKeydown);
  updateCounter();

  olderButton.addEventListener("click", loadOlder);
  // 메시지 영역 맨 위에 닿으면 이전 메시지를 자동으로 불러온다.
  new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) loadOlder();
    },
    { root: scrollBox },
  ).observe(olderSentinel);

  // 맨 아래를 보고 있었는지 기억해 두었다가, 메시지 영역 크기가 바뀌면(429 안내가 생기거나 화면 높이가 바뀜)
  // 다시 맨 아래로 맞춘다. 그대로 두면 영역이 줄어든 만큼 마지막 메시지가 아래에서 잘린다.
  let stickToBottom = true;
  scrollBox.addEventListener("scroll", () => {
    stickToBottom = isNearBottom();
    if (stickToBottom) newMessageButton.hidden = true;
  });
  new ResizeObserver(() => {
    if (stickToBottom) scrollToBottom();
  }).observe(scrollBox);
  newMessageButton.addEventListener("click", () => {
    scrollToBottom();
    newMessageButton.hidden = true;
  });

  // 탭이 숨겨지면 폴링을 멈추고, 다시 보이면 바로 한 번 확인한다.
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) cancelPoll();
    else schedulePoll(0);
  });
}

// ---------- 모바일 키보드 ----------

/**
 * 휴대폰에서 키보드가 올라와도 입력창과 마지막 메시지가 가려지지 않게 한다.
 * - 화면 높이: iOS Safari는 키보드가 올라와도 페이지 높이(dvh)를 줄이지 않고 화면 일부를 덮는다.
 *   그래서 실제로 보이는 높이(visualViewport.height)를 CSS 변수로 넘겨 대화 화면 높이로 쓴다.
 *   메시지 영역 크기가 바뀌면 bindEvents의 ResizeObserver가 맨 아래로 다시 맞춘다.
 * - 입력 중(is-typing): 좁아진 화면을 메시지에 쓰도록 사이트 헤더·"← 쪽지함"·게시글 줄을 접는다. (CSS)
 *   상대 닉네임 줄과 ⋯(신고·차단) 메뉴는 그대로 둔다. 포커스가 빠지면 되돌린다.
 * - 보내기 버튼: 누를 때 입력창에서 포커스가 빠지면 키보드가 내려갔다 다시 올라와 화면이 흔들린다.
 *   버튼이 포커스를 가져가지 않게 해 키보드를 그대로 둔다. (클릭·전송은 그대로 일어난다)
 */
function bindMobileKeyboard() {
  const mobileQuery = window.matchMedia(MOBILE_QUERY);
  const viewport = window.visualViewport;
  const root = document.documentElement;

  const fitHeight = () => {
    if (viewport && mobileQuery.matches) {
      root.style.setProperty("--chat-viewport-height", `${Math.round(viewport.height)}px`);
      // iOS는 입력창을 보이게 하려고 페이지를 밀어 올린다. 높이를 맞췄으니 원래 위치로 되돌린다.
      if (window.scrollY !== 0) window.scrollTo(0, 0);
    } else {
      root.style.removeProperty("--chat-viewport-height");
    }
  };
  viewport?.addEventListener("resize", fitHeight);
  mobileQuery.addEventListener("change", fitHeight);
  fitHeight();

  textarea.addEventListener("focus", () => document.body.classList.toggle("is-typing", mobileQuery.matches));
  textarea.addEventListener("blur", () => document.body.classList.remove("is-typing"));

  const keepTextareaFocus = (event) => {
    if (document.activeElement === textarea) event.preventDefault();
  };
  submitButton.addEventListener("pointerdown", keepTextareaFocus);
  submitButton.addEventListener("mousedown", keepTextareaFocus);
  // 빠른 문장 칩도 같다. 입력 중에 누르면 포커스가 빠지며 칩 줄이 다시 펼쳐져(한 줄 → 여러 줄) 누른 자리가 어긋난다.
  quickReplies.addEventListener("pointerdown", keepTextareaFocus);
  quickReplies.addEventListener("mousedown", keepTextareaFocus);
}

function renderChatHeader(conversation) {
  const { partner, post, my_role: role } = conversation;
  document.title = t("title.chat_with", { nickname: partner.nickname }); // document.title은 글자로만 처리되어 안전하다.
  document.getElementById("chat-partner").textContent = partner.nickname;

  const roleText = role === "BUYER" ? t("chat.role_buyer") : t("chat.role_seller");
  const postLine = document.getElementById("chat-post");
  if (post) {
    postLine.replaceChildren(
      el("span", { className: "chat__role", text: roleText }),
      statusBadge(post.status),
      el("a", { href: `/static/post.html?id=${encodeURIComponent(post.id)}`, text: post.title }),
    );
  } else {
    // 글이 삭제되어도 대화는 이어 갈 수 있다. (서버가 대화방을 남긴다)
    postLine.replaceChildren(
      el("span", { className: "chat__role", text: roleText }),
      el("span", { className: "chat__post-deleted", text: t("common.post_deleted") }),
    );
  }
}

// ---------- 거래 후기 ----------

/**
 * 판매자가 이 대화 상대를 구매자로 골라 판매 완료했으면 후기 줄을 보여준다.
 * 후기는 차단 관계여도 남길 수 있다. 서버가 권한·기간을 다시 확인한다.
 */
function renderReviewState(conversation) {
  const { trade, partner } = conversation;
  // 거래 기록이 없거나 상대가 탈퇴했으면(쓸 수도, 볼 프로필도 없음) 줄을 숨긴다.
  if (trade === null || trade === undefined || partner.withdrawn) {
    reviewBox.hidden = true;
    return;
  }
  const profileLink = el("a", { href: `/static/user.html?id=${encodeURIComponent(partner.id)}`, text: t("chat.partner_profile") });
  if (trade.can_write) {
    const button = el("button", { type: "button", className: "button button--primary", text: t("review.submit") });
    button.addEventListener("click", () => onWriteReview(conversation));
    reviewBox.replaceChildren(
      el("span", { className: "chat__review-text", text: t("chat.review_prompt", { date: formatMonthDayTime(trade.deadline) }) }),
      button,
    );
  } else {
    const text = trade.written ? t("chat.review_written") : t("chat.review_expired");
    reviewBox.replaceChildren(el("span", { className: "chat__review-text", text }), profileLink);
  }
  reviewBox.hidden = false;
}

async function onWriteReview(conversation) {
  const written = await openReviewDialog({
    partnerNickname: conversation.partner.nickname,
    send: (data) => createReview(conversation.trade.trade_id, data),
  });
  if (!written) return;
  // 이 거래의 후기 알림이 빠지므로 종 배지를 바로 다시 받는다. (알림 판은 열 때마다 새로 받는다)
  refreshReviewBadge();
  try {
    renderReviewState(await getConversation(conversationId));
  } catch (error) {
    if (handleFatalError(error)) return;
  }
}

// ---------- 신고·차단 ----------

/**
 * 대화방의 차단 상태(can_send, blocked_by_me)에 맞춰 입력창과 버튼을 바꾼다.
 * 상대가 나를 차단한 경우에는 "차단당했다"고 알리지 않고 보낼 수 없다는 것만 보여준다.
 */
function applyBlockState(conversation) {
  canSend = conversation.can_send && suspendedText === null;
  const { partner } = conversation;

  if (canSend) {
    blockedNotice.hidden = true;
  } else if (suspendedText !== null) {
    blockedNotice.textContent = suspendedText;
    blockedNotice.hidden = false;
  } else if (partner.withdrawn) {
    blockedNotice.textContent = t("chat.withdrawn_partner");
    blockedNotice.hidden = false;
  } else {
    blockedNotice.textContent = conversation.blocked_by_me
      ? t("chat.blocked_by_me")
      : t("chat.cannot_send");
    blockedNotice.hidden = false;
  }
  textarea.disabled = !canSend;
  updateSendButtons();
  updateQuickReplies(); // 보낼 수 없게 되면 칩도 숨긴다.

  // 탈퇴한 상대는 신고·차단할 대상이 없으므로(서버도 404) 버튼을 두지 않는다.
  if (partner.withdrawn) {
    chatActions.replaceChildren();
    return;
  }

  // 닉네임 줄 오른쪽 끝의 ⋯(더보기). 메시지마다 있는 ⋯와 같은 모양·같은 메뉴 창(openActionMenu)을 쓴다.
  // 메뉴 창은 Esc나 바깥을 누르면 닫힌다. 이미 차단한 상대면 "차단" 대신 "차단 해제"가 나온다.
  const moreButton = el("button", {
    type: "button",
    className: "message__menu chat__more",
    text: "⋯",
    attrs: { "aria-label": t("chat.more_aria"), "aria-haspopup": "dialog" },
  });
  moreButton.addEventListener("click", async () => {
    const choice = await openActionMenu({
      heading: t("chat.report_target", { nickname: partner.nickname }),
      items: [
        { key: "report", label: t("term.report") },
        conversation.blocked_by_me
          ? { key: "unblock", label: t("term.unblock") }
          : { key: "block", label: t("term.block"), danger: true },
      ],
    });
    if (choice === "report") {
      const reported = await openReportDialog({
        heading: t("safety.report_user"),
        targetText: t("chat.report_target", { nickname: partner.nickname }),
        send: (data) => reportUser(partner.id, data),
      });
      if (reported) showSafetyNotice(REPORT_DONE_TEXT);
    } else if (choice === "block" || choice === "unblock") {
      await onToggleBlock(conversation);
    }
    // 메뉴를 그사이 다시 그렸으면(차단 상태 변경) 새 버튼으로 돌아간다.
    (moreButton.isConnected ? moreButton : chatActions.querySelector("button"))?.focus();
  });
  chatActions.replaceChildren(moreButton);
}

async function onToggleBlock(conversation) {
  const { partner, blocked_by_me: blockedByMe } = conversation;
  if (!(blockedByMe ? confirmUnblock(partner.nickname) : confirmBlock(partner.nickname))) return;
  try {
    if (blockedByMe) await unblockUser(partner.id);
    else await blockUser(partner.id);
    // 서버 기준 상태로 입력창·버튼을 다시 맞춘다.
    applyBlockState(await getConversation(conversationId));
    if (blockedByMe) showSafetyNotice(UNBLOCK_DONE_TEXT);
    else showSafetyNotice(...blockDoneContent());
  } catch (error) {
    if (handleFatalError(error)) return;
    setErrorText(safetyNotice, error.message, error.original);
    safetyNotice.hidden = false;
  }
}

// 전송이 400으로 막혔을 때(그사이 상대가 차단함 등) 대화방 상태를 다시 받아 입력창을 맞춘다.
async function refreshBlockState() {
  try {
    applyBlockState(await getConversation(conversationId));
  } catch {
    // 상태를 못 받아도 전송 에러 문구는 이미 보이므로 그대로 둔다.
  }
}

function showSafetyNotice(...content) {
  safetyNotice.replaceChildren(...content);
  safetyNotice.hidden = false;
}

/**
 * 화면을 연 뒤 다른 탭에서 로그인·로그아웃해 토큰이 바뀌었으면 폴링과 전송을 멈추고 안내한다. 같으면 true.
 * 바뀐 토큰으로 계속 요청하면 서버가 새 계정 기준으로 is_mine을 계산해, 상대 메시지가 내 말풍선으로 그려진다.
 */
function checkSameAccount() {
  if (accountChanged) return false;
  if (getToken() === sessionToken) return true;

  accountChanged = true;
  if (cooldownTimer !== null) window.clearInterval(cooldownTimer);
  showPageError(t("chat.account_changed"));
  return false;
}

function showPageError(message, original = null) {
  stopPolling();
  pageStatus.hidden = true;
  chat.hidden = true;
  setErrorText(pageErrorText, message, original);
  pageError.hidden = false;
}

// ---------- 메시지 그리기 ----------

/**
 * 메시지들을 id 순서에 맞는 자리에 넣는다. 이미 그린 메시지는 건너뛴다.
 * 보통은 맨 뒤(새 메시지)나 맨 앞(이전 메시지)에 붙지만, 내가 보낸 메시지의 응답이
 * 상대의 더 새 메시지보다 늦게 도착할 수 있어 자리를 찾아 넣는다.
 * @returns {object[]} 새로 그린 메시지들
 */
function addMessages(messages) {
  const added = [];
  for (const message of messages) {
    if (shownIds.has(message.id)) continue;
    shownIds.add(message.id);
    const next = [...list.children].find((item) => Number(item.dataset.id) > message.id);
    list.insertBefore(renderMessage(message), next ?? null);
    oldestId = oldestId === null ? message.id : Math.min(oldestId, message.id);
    newestId = newestId === null ? message.id : Math.max(newestId, message.id);
    added.push(message);
  }
  emptyText.hidden = shownIds.size > 0;
  emptyHint.hidden = emptyText.hidden; // 짧은 개인정보 안내는 빈 대화에서만
  updateQuickReplies();
  return added;
}

// ---------- 빠른 문장 ----------

/** 칩 3개를 만든다. 누르면 보내지 않고 입력칸에 채운 뒤 포커스만 옮긴다(내용을 고쳐 보낼 수 있게). */
function renderQuickReplies() {
  quickReplies.replaceChildren(
    ...QUICK_REPLY_KEYS.map((key) => {
      const chip = el("button", { type: "button", className: "chat__quick-chip", text: t(key) });
      chip.addEventListener("click", () => fillQuickReply(t(key)));
      return chip;
    }),
  );
}

/** 이미 쓰던 글이 있으면 지우지 않고 한 칸 띄어 뒤에 붙인다. 최대 글자 수는 넘기지 않는다. */
function fillQuickReply(text) {
  const current = textarea.value.trimEnd();
  textarea.value = (current ? `${current} ${text}` : text).slice(0, MAX_LENGTH);
  updateCounter();
  fitTextarea();
  updateSendButtons();
  textarea.focus();
  textarea.setSelectionRange(textarea.value.length, textarea.value.length);
}

/** 빈 대화 + 구매자 + 보낼 수 있는 상태일 때만 보인다. 메시지가 하나라도 생기면 사라진다. */
function updateQuickReplies() {
  quickReplies.hidden = !(myRole === "BUYER" && shownIds.size === 0 && canSend);
}

function renderMessage(message) {
  const bubble = message.content ? el("p", { className: "message__bubble", text: message.content }) : null;
  // 사진 메시지는 사진 아래에 함께 보낸 글(있으면)을 둔다.
  const body = message.has_image ? el("div", { className: "message__body" }, renderPhoto(message), bubble) : bubble;
  const item = el(
    "li",
    { className: `message ${message.is_mine ? "message--mine" : "message--theirs"}` },
    // 말풍선 위치만으로는 누가 보냈는지 알 수 없는 화면 낭독기 사용자를 위해 글자로 붙인다.
    el("span", { className: "visually-hidden", text: message.is_mine ? t("common.me_prefix") : t("chat.them_prefix") }),
    // 상대 메시지에만 "⋯"(이 메시지 신고)를 둔다. 내 메시지는 서버도 신고를 400으로 막는다.
    message.is_mine ? body : el("div", { className: "message__row" }, body, messageMenuButton(message)),
    el("time", {
      className: "message__time",
      text: formatShortDate(message.created_at),
      attrs: { datetime: message.created_at },
    }),
  );
  item.dataset.id = String(message.id);
  return item;
}

// ---------- 사진 ----------

/** 사진 썸네일 자리. 누르면 큰 사진을 연다. 그림은 화면에 보일 때 photoObserver가 받아 넣는다. */
function renderPhoto(message) {
  const img = el("img", { className: "message__photo-img", attrs: { alt: t("term.photo"), width: "200", height: "200" } });
  const button = el("button", {
    type: "button",
    className: "message__photo",
    attrs: { "aria-label": message.is_mine ? t("chat.photo_open_mine") : t("chat.photo_open_theirs") },
  }, img);
  button.dataset.messageId = String(message.id);
  button.addEventListener("click", () => openPhotoViewer(message.id, button));
  photoObserver.observe(button);
  return button;
}

async function loadThumbnail(button) {
  const img = button.querySelector("img");
  // 그림 크기를 실제 비율로 바꿔, 자리를 잡아 둔 200x200 상자가 사진 모양에 맞게 바뀌게 한다.
  img.addEventListener("load", () => {
    img.removeAttribute("width");
    img.removeAttribute("height");
    button.classList.add("is-loaded");
  }, { once: true });
  const shown = await showBlobImage(img, () => fetchMessageImage(button.dataset.messageId, "thumb"));
  if (!shown) {
    button.classList.add("is-failed");
    img.alt = t("chat.photo_failed_alt");
  }
}

/** 큰 사진 보기. 신고 창과 같은 <dialog>라 Esc·닫기 버튼으로 닫히고, 닫으면 누른 사진으로 초점이 돌아간다. */
function openPhotoViewer(messageId, opener) {
  const img = el("img", { className: "photo-viewer__img", attrs: { alt: t("term.photo") } });
  const status = el("p", { className: "photo-viewer__status", text: t("common.loading"), attrs: { role: "status" } });
  const close = el("button", { type: "button", className: "button photo-viewer__close", text: t("common.close") });
  const dialog = el("dialog", { className: "photo-viewer", attrs: { "aria-label": t("chat.viewer_aria") } }, img, status, close);
  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener("close", () => {
    dialog.remove();
    if (opener.isConnected) opener.focus();
  });
  img.addEventListener("load", () => {
    status.hidden = true;
  }, { once: true });
  document.body.append(dialog);
  dialog.showModal();
  close.focus();
  showBlobImage(img, () => fetchMessageImage(messageId, "full")).then((shown) => {
    if (!shown) status.textContent = t("chat.photo_failed");
  });
}

function messageMenuButton(message) {
  const button = el("button", {
    type: "button",
    className: "message__menu",
    text: "⋯",
    attrs: { "aria-label": t("chat.menu_aria"), "aria-haspopup": "dialog" },
  });
  button.addEventListener("click", async () => {
    const choice = await openActionMenu({
      heading: t("chat.menu_heading"),
      items: [{ key: "report", label: t("chat.report_message"), danger: true }],
    });
    if (choice === "report") {
      // 신고 창에 어떤 메시지인지 앞부분을 보여준다. 길면 줄여서 창이 커지지 않게 한다.
      const preview = message.content.length > 40 ? `${message.content.slice(0, 40)}…` : message.content;
      const photo = message.has_image ? t("chat.photo_message") : "";
      const reported = await openReportDialog({
        heading: t("chat.report_message_heading"),
        targetText: [photo, preview ? `“${preview}”` : ""].filter(Boolean).join(" · "),
        send: (data) => reportMessage(message.id, data),
      });
      if (reported) showSafetyNotice(REPORT_DONE_TEXT);
    }
    button.focus();
  });
  return button;
}

function isNearBottom() {
  return scrollBox.scrollHeight - scrollBox.scrollTop - scrollBox.clientHeight < NEAR_BOTTOM_PX;
}

function scrollToBottom() {
  scrollBox.scrollTop = scrollBox.scrollHeight;
}

/** 새 메시지를 넣은 뒤 스크롤 처리: 아래를 보고 있었거나 내가 보낸 것이면 따라 내려간다. */
function addNewerMessages(messages) {
  const wasNearBottom = isNearBottom();
  const added = addMessages(messages);
  if (added.length === 0) return added;

  if (wasNearBottom || added.some((message) => message.is_mine)) {
    scrollToBottom();
  } else {
    // 위쪽의 이전 대화를 읽는 중이면 위치를 그대로 두고 알려만 준다.
    newMessageButton.hidden = false;
  }
  return added;
}

// ---------- 이전 메시지 ----------

async function loadOlder() {
  if (!hasOlder || loadingOlder || oldestId === null) return;
  loadingOlder = true;
  updateOlderButton();

  // 위에 메시지가 추가되면 보던 내용이 아래로 밀리므로, 늘어난 높이만큼 스크롤을 보정한다.
  const previousHeight = scrollBox.scrollHeight;
  const previousTop = scrollBox.scrollTop;
  try {
    if (!checkSameAccount()) return;
    const data = await listMessages(conversationId, { before_id: oldestId, limit: PAGE_LIMIT });
    if (!checkSameAccount()) return;
    addMessages(data.items);
    hasOlder = data.has_more;
    scrollBox.scrollTop = previousTop + (scrollBox.scrollHeight - previousHeight);
  } catch (error) {
    if (!handleFatalError(error)) showConnection(t("chat.older_failed"));
  } finally {
    loadingOlder = false;
    updateOlderButton();
  }
}

function updateOlderButton() {
  olderButton.hidden = !hasOlder;
  olderButton.disabled = loadingOlder;
  olderButton.textContent = loadingOlder ? t("common.loading") : t("chat.older");
}

// ---------- 새 메시지 확인 (폴링) ----------

// setInterval 대신 응답이 온 뒤 다음 요청을 예약한다. 응답이 느려도 요청이 겹치지 않게 하기 위해서다.
function schedulePoll(delay) {
  cancelPoll();
  if (stopped || pollInFlight || document.hidden) return;
  pollTimer = window.setTimeout(poll, delay);
}

function cancelPoll() {
  if (pollTimer !== null) window.clearTimeout(pollTimer);
  pollTimer = null;
}

function stopPolling() {
  stopped = true;
  cancelPoll();
}

async function poll() {
  pollTimer = null;
  if (stopped || document.hidden || !checkSameAccount()) return;

  pollInFlight = true;
  const afterId = newestId; // 메시지가 하나도 없으면 null이고, 그때는 최근 메시지를 받는다.
  let nextDelay = POLL_INTERVAL_MS;
  try {
    const data = await listMessages(conversationId, { after_id: afterId, limit: PAGE_LIMIT });
    // 요청하는 사이에 계정이 바뀌었으면 응답의 is_mine이 다른 계정 기준일 수 있어 그리지 않는다.
    if (!checkSameAccount()) return;
    hideConnection();
    const added = addNewerMessages(data.items);
    // 상대 메시지를 받았으면 서버가 방금 읽음 처리했으므로 헤더 숫자를 맞춘다.
    if (added.some((message) => !message.is_mine)) refreshUnreadBadge();
    // 한 번에 다 못 받았으면 쉬지 않고 이어서 받는다. (after_id가 없을 때 has_more는 이전 메시지라 제외)
    if (data.has_more && afterId !== null) nextDelay = 0;
  } catch (error) {
    if (handleFatalError(error)) return;
    showConnection(t("chat.unstable"));
    nextDelay = POLL_RETRY_INTERVAL_MS;
  } finally {
    pollInFlight = false;
  }
  schedulePoll(nextDelay);
}

function showConnection(message) {
  connectionStatus.textContent = message;
  connectionStatus.hidden = false;
}

function hideConnection() {
  connectionStatus.hidden = true;
}

/** 더 진행할 수 없는 에러면 처리하고 true. (토큰 만료, 방이 없어짐, 참여자가 아님) */
function handleFatalError(error) {
  if (error.status === 401) {
    stopPolling();
    redirectToLogin();
    return true;
  }
  if (error.status === 403 || error.status === 404) {
    showPageError(error.message, error.original);
    return true;
  }
  return false;
}

// ---------- 보내기 ----------

function updateCounter() {
  // JS의 length는 이모지 같은 일부 글자를 2자로 센다. 서버(1000자)보다 먼저 막힐 수는 있어도 넘치지는 않는다.
  counter.textContent = `${textarea.value.length} / ${MAX_LENGTH}`;
  counter.hidden = textarea.value.length < COUNTER_FROM;
}

/** 입력칸은 한 줄 높이로 시작해 글이 길어지면 최대 4줄(CSS max-height)까지 자란다. 그 뒤로는 칸 안에서 스크롤. */
function fitTextarea() {
  textarea.style.height = "auto";
  textarea.style.height = `${textarea.scrollHeight}px`;
}

// 넓은 화면에서는 Enter로 보내고 Shift+Enter로 줄을 바꾼다.
// 터치 화면에서는 Enter가 줄바꿈이고 보내기 버튼으로 보낸다. (가상 키보드에는 Shift가 없다)
const enterSends = !window.matchMedia("(pointer: coarse)").matches;

function onTextareaKeydown(event) {
  if (!enterSends || event.key !== "Enter" || event.shiftKey) return;
  // 한글 조합 중에 누른 Enter는 글자 확정용이다. 이때 보내면 마지막 글자가 한 번 더 전송된다.
  if (event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  form.requestSubmit();
}

async function onSubmit(event) {
  event.preventDefault();
  if (sending || cooldownTimer !== null || !canSend) return;
  // 다른 계정의 토큰으로 보내면 그 계정 이름으로 전송되므로 보내기 전에 확인한다.
  if (!checkSameAccount()) return;

  clearFormErrors(form, sendError);
  setSending(true);
  try {
    const message = await sendMessage(conversationId, textarea.value);
    if (!checkSameAccount()) return;
    textarea.value = "";
    updateCounter();
    fitTextarea();
    addNewerMessages([message]);
  } catch (error) {
    handleSendError(error);
  } finally {
    setSending(false);
    textarea.focus();
  }
}

/** 사진 고르기가 끝나면 바로 보낸다. 입력창의 글은 그대로 두고 사진만 보낸다. */
async function onPhotoChosen() {
  const [file] = photoInput.files;
  photoInput.value = ""; // 같은 사진을 다시 골라도 change가 일어나게 비운다.
  if (!file || sending || cooldownTimer !== null || !canSend) return;
  if (!checkSameAccount()) return;

  clearFormErrors(form, sendError);
  setSending(true, t("chat.photo_preparing"));
  try {
    // 휴대폰 원본은 브라우저에서 먼저 줄인다. (판매글 사진과 같은 방법)
    const prepared = await preparePhoto(file);
    if (prepared.file.size > MAX_PHOTO_BYTES) {
      sendError.textContent = t("chat.photo_too_big");
      sendError.hidden = false;
      return;
    }
    const message = await sendMessageImage(conversationId, prepared.file, (ratio) => {
      photoProgress.textContent = `${Math.round(ratio * 100)}%`;
    });
    if (!checkSameAccount()) return;
    addNewerMessages([message]);
  } catch (error) {
    handleSendError(error);
  } finally {
    setSending(false);
  }
}

/** 글·사진 보내기의 공통 에러 처리. */
function handleSendError(error) {
  // 방은 이미 열었으므로 전송의 403은 "남의 방"이 아니라 이용 정지다. 대화는 계속 볼 수 있게 입력창만 잠근다.
  if (error.status === 403) {
    suspendedText = error.message;
    showFormErrors(form, sendError, error);
    refreshBlockState();
    return;
  }
  if (handleFatalError(error)) return;
  if (error.status === 429) {
    // 입력한 내용은 그대로 두고, 다시 보낼 수 있을 때까지 버튼을 잠근다.
    startCooldown(error.retryAfter ?? DEFAULT_RETRY_SECONDS, error);
  } else {
    // 422(빈 내용, 1000자 초과, 사진 형식)는 입력칸 아래나 폼 아래에, 그 밖에는 폼 아래에 보여준다.
    showFormErrors(form, sendError, error);
    // 400은 차단 관계일 수 있으므로 상태를 다시 받아 입력창을 잠근다.
    if (error.status === 400) refreshBlockState();
  }
}

/** 보내는 동안에는 글·사진 버튼을 함께 잠근다. photoText: 사진을 보낼 때 입력 줄 아래에 보일 글자(준비 중·%) */
function setSending(isSending, photoText = null) {
  sending = isSending;
  updateSendButtons();
  // 아이콘 버튼이라 글자 대신 이름(aria-label)으로 보내는 중임을 알린다.
  submitButton.setAttribute("aria-label", isSending && photoText === null ? t("chat.sending") : t("chat.send"));
  const photoSending = isSending && photoText !== null;
  photoProgress.textContent = photoSending ? photoText : "";
  photoProgress.hidden = !photoSending;
  photoButton.setAttribute("aria-busy", String(photoSending));
}

function updateSendButtons() {
  const locked = sending || cooldownTimer !== null || !canSend;
  // 보내기는 입력이 비어 있어도 회색으로 잠근다. (사진은 글 없이 보낼 수 있다)
  submitButton.disabled = locked || textarea.value.trim() === "";
  photoButton.disabled = locked;
}

/** 429: 서버 메시지와 남은 시간을 보여주고, 시간이 지나면 다시 보낼 수 있게 한다. (다른 언어는 원문을 아래에 붙인다) */
function startCooldown(seconds, error) {
  let remaining = Math.max(1, Math.ceil(seconds));
  const render = () => {
    setErrorText(sendError, t("chat.cooldown", { message: error.message, count: remaining }), error.original);
    sendError.hidden = false;
  };
  render();
  submitButton.disabled = true;
  photoButton.disabled = true;
  cooldownTimer = window.setInterval(() => {
    remaining -= 1;
    if (remaining > 0) {
      render();
      return;
    }
    window.clearInterval(cooldownTimer);
    cooldownTimer = null;
    sendError.hidden = true;
    updateSendButtons();
  }, 1000);
}
