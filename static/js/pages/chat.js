// 대화 화면: 한 대화방의 메시지를 보여주고 보낸다. 로그인이 필요하다.
// - 새 메시지는 몇 초마다 after_id로 확인한다(폴링). 탭이 숨겨지면 멈춘다.
// - 맨 위로 스크롤하면 before_id로 이전 메시지를 불러온다.
// - 메시지 목록을 조회하면 서버가 상대 메시지를 읽음 처리하므로, 화면은 헤더 배지만 다시 불러온다.
// - 처음 불러오기·폴링·전송·이전 메시지가 모두 addMessages → renderMessage 한 경로로 그리고,
//   내 메시지인지는 서버 응답의 is_mine을 그대로 쓴다.
// - 토큰은 탭끼리 공유된다. 다른 탭에서 계정이 바뀌면 이 화면이 새 계정 토큰으로 폴링·전송하게 되어
//   상대 메시지가 내 말풍선으로 그려지거나 다른 계정 이름으로 전송되므로, 계정이 바뀌면 멈춘다.
import { getConversation, listMessages, sendMessage } from "../api.js";
import { redirectToLogin, refreshUnreadBadge, renderHeader } from "../auth.js";
import { getToken, onTokenChangedInOtherTab } from "../token.js";
import { clearFormErrors, el, formatShortDate, readPostIdFromUrl, showFormErrors, statusBadge } from "../ui.js";

const POLL_INTERVAL_MS = 5000; // 새 메시지 확인 간격
const POLL_RETRY_INTERVAL_MS = 15000; // 연결이 불안정할 때는 서버에 부담을 덜 주도록 늦춘다.
const PAGE_LIMIT = 30; // 한 번에 불러올 메시지 수 (서버 최대 100)
const NEAR_BOTTOM_PX = 80; // 이만큼 안쪽이면 "맨 아래를 보고 있다"고 본다.
const MAX_LENGTH = 1000; // 서버 규칙과 같다. (app/schemas/conversation.py)
const DEFAULT_RETRY_SECONDS = 10; // 429에 Retry-After가 없을 때

const pageStatus = document.getElementById("page-status");
const pageError = document.getElementById("page-error");
const pageErrorText = document.getElementById("page-error-text");
const chat = document.getElementById("chat");
const scrollBox = document.getElementById("chat-scroll");
const list = document.getElementById("message-list");
const emptyText = document.getElementById("chat-empty");
const olderButton = document.getElementById("older-button");
const olderSentinel = document.getElementById("older-sentinel");
const newMessageButton = document.getElementById("new-message-button");
const connectionStatus = document.getElementById("connection-status");
const form = document.getElementById("message-form");
const textarea = form.elements.content;
const counter = document.getElementById("content-count");
const submitButton = form.querySelector('button[type="submit"]');
const sendError = document.getElementById("send-error");

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
let cooldownTimer = null;

// 이 화면을 연 계정의 토큰. 요청 전후로 비교해, 다른 탭에서 계정이 바뀌었는지 확인한다.
let sessionToken = null;
let accountChanged = false;

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
    else showPageError("서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
    return;
  }
  if (conversationId === null) {
    showPageError("대화방 주소가 올바르지 않습니다.");
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
    // 404(없는 방), 403(남의 방)은 서버 메시지를 그대로 보여준다.
    showPageError(error.message);
    return;
  }
  if (!checkSameAccount()) return;

  renderChatHeader(conversation);
  addMessages(first.items);
  hasOlder = first.has_more;
  updateOlderButton();

  pageStatus.hidden = true;
  chat.hidden = false;
  scrollToBottom();
  // 처음 그린 메시지를 모두 읽어 주지 않도록, 그린 뒤에 새 메시지 알림 영역으로 지정한다.
  list.setAttribute("role", "log");
  list.setAttribute("aria-label", "메시지");

  refreshUnreadBadge(); // 방금 읽음 처리된 만큼 헤더 숫자가 줄어든다.
  bindEvents();
  schedulePoll(POLL_INTERVAL_MS);
}

function bindEvents() {
  form.addEventListener("submit", onSubmit);
  textarea.addEventListener("input", updateCounter);
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

function renderChatHeader(conversation) {
  const { partner, post, my_role: role } = conversation;
  document.title = `${partner.nickname}님과의 쪽지 | Campus Books`; // document.title은 글자로만 처리되어 안전하다.
  document.getElementById("chat-partner").textContent = partner.nickname;

  const roleText = role === "BUYER" ? "내가 문의한 글" : "내 글에 온 문의";
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
      el("span", { className: "chat__post-deleted", text: "삭제된 글" }),
    );
  }
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
  showPageError("다른 탭에서 로그인 상태가 바뀌어 이 대화를 멈췄습니다. 새로고침하면 지금 로그인한 계정으로 다시 열립니다.");
  return false;
}

function showPageError(message) {
  stopPolling();
  pageStatus.hidden = true;
  chat.hidden = true;
  pageErrorText.textContent = message;
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
  return added;
}

function renderMessage(message) {
  const item = el(
    "li",
    { className: `message ${message.is_mine ? "message--mine" : "message--theirs"}` },
    // 말풍선 위치만으로는 누가 보냈는지 알 수 없는 화면 낭독기 사용자를 위해 글자로 붙인다.
    el("span", { className: "visually-hidden", text: message.is_mine ? "나: " : "상대: " }),
    el("p", { className: "message__bubble", text: message.content }),
    el("time", {
      className: "message__time",
      text: formatShortDate(message.created_at),
      attrs: { datetime: message.created_at },
    }),
  );
  item.dataset.id = String(message.id);
  return item;
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
    if (!handleFatalError(error)) showConnection("이전 메시지를 불러오지 못했습니다. 다시 시도해 주세요.");
  } finally {
    loadingOlder = false;
    updateOlderButton();
  }
}

function updateOlderButton() {
  olderButton.hidden = !hasOlder;
  olderButton.disabled = loadingOlder;
  olderButton.textContent = loadingOlder ? "불러오는 중…" : "이전 메시지 보기";
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
    showConnection("연결이 불안정합니다. 잠시 후 다시 확인합니다.");
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
    showPageError(error.message);
    return true;
  }
  return false;
}

// ---------- 보내기 ----------

function updateCounter() {
  // JS의 length는 이모지 같은 일부 글자를 2자로 센다. 서버(1000자)보다 먼저 막힐 수는 있어도 넘치지는 않는다.
  counter.textContent = `${textarea.value.length} / ${MAX_LENGTH}`;
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
  if (sending || cooldownTimer !== null) return;
  // 다른 계정의 토큰으로 보내면 그 계정 이름으로 전송되므로 보내기 전에 확인한다.
  if (!checkSameAccount()) return;

  clearFormErrors(form, sendError);
  setSending(true);
  try {
    const message = await sendMessage(conversationId, textarea.value);
    if (!checkSameAccount()) return;
    textarea.value = "";
    updateCounter();
    addNewerMessages([message]);
  } catch (error) {
    if (handleFatalError(error)) return;
    if (error.status === 429) {
      // 입력한 내용은 그대로 두고, 다시 보낼 수 있을 때까지 버튼을 잠근다.
      startCooldown(error.retryAfter ?? DEFAULT_RETRY_SECONDS, error.message);
    } else {
      // 422(빈 내용, 1000자 초과)는 입력칸 아래에, 그 밖에는 폼 아래에 보여준다.
      showFormErrors(form, sendError, error);
    }
  } finally {
    setSending(false);
    textarea.focus();
  }
}

function setSending(isSending) {
  sending = isSending;
  submitButton.disabled = isSending || cooldownTimer !== null;
  submitButton.textContent = isSending ? "보내는 중…" : "보내기";
}

/** 429: 서버 메시지와 남은 시간을 보여주고, 시간이 지나면 다시 보낼 수 있게 한다. */
function startCooldown(seconds, message) {
  let remaining = Math.max(1, Math.ceil(seconds));
  const render = () => {
    sendError.textContent = `${message} (${remaining}초 후 다시 보낼 수 있어요)`;
    sendError.hidden = false;
  };
  render();
  submitButton.disabled = true;
  cooldownTimer = window.setInterval(() => {
    remaining -= 1;
    if (remaining > 0) {
      render();
      return;
    }
    window.clearInterval(cooldownTimer);
    cooldownTimer = null;
    sendError.hidden = true;
    submitButton.disabled = sending;
  }, 1000);
}
