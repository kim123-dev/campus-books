// 상세 화면: 글 정보를 보여주고, 내 글이면 상태 변경과 삭제를 할 수 있게 한다.
// 권한과 상태 규칙의 최종 판단은 서버가 한다. 화면은 누를 수 없는 버튼을 미리 숨기는 정도만 한다.
import { changePostStatus, deletePost, getPost, startConversation } from "../api.js";
import { LOGIN_PAGE, authPageUrl, redirectToLogin, renderHeader } from "../auth.js";
import { CONDITION_LABELS, el, formatDate, formatPrice, readPostIdFromUrl, safeImageUrl, statusBadge } from "../ui.js";

const HOME_PAGE = "/static/index.html";

// 서버가 허용하는 오픈채팅 주소의 시작 부분. 서버 검증(422)이 1차 방어이고,
// 화면도 이 형식일 때만 링크를 만들어 javascript: 같은 주소가 href에 들어가지 않게 한 번 더 막는다.
const OPEN_CHAT_PREFIX = "https://open.kakao.com/";

// 현재 상태에서 바꿀 수 있는 상태. 서버 app/services/post_service.py의 ALLOWED_TRANSITIONS와 같아야 한다.
// 어긋나더라도 서버가 400으로 막으므로, 여기서는 누르면 실패할 버튼을 보여주지 않는 용도다.
const ALLOWED_TRANSITIONS = {
  ON_SALE: ["RESERVED", "SOLD"],
  RESERVED: ["ON_SALE", "SOLD"],
  SOLD: [],
};

// "판매 완료으로"처럼 조사가 틀리지 않도록 버튼 문구를 따로 둔다.
const STATUS_BUTTON_LABELS = {
  ON_SALE: "판매 중으로 변경",
  RESERVED: "예약 중으로 변경",
  SOLD: "판매 완료로 변경",
};

const pageStatus = document.getElementById("page-status");
const pageError = document.getElementById("page-error");
const pageErrorText = document.getElementById("page-error-text");
const detail = document.getElementById("post-detail");
const ownerPanel = document.getElementById("owner-panel");
const ownerActions = document.getElementById("owner-actions");
const actionError = document.getElementById("action-error");

// 로그인한 사용자(없으면 null). 내 글인지, 연락 방법 안내를 어떻게 할지 고를 때 쓴다.
let currentUser = null;

// 헤더(/users/me)와 글 조회를 동시에 시작한다. renderHeader는 실패해도 null을 돌려주고 멈추지 않는다.
const mePromise = renderHeader(document.getElementById("site-header"));
const postId = readPostIdFromUrl();

if (postId === null) {
  showPageError("글 주소가 올바르지 않습니다.");
} else {
  load(postId);
}

// ---------- 불러오기 ----------

async function load(id) {
  let post;
  try {
    post = await getPost(id);
  } catch (error) {
    // 404 "게시글을 찾을 수 없습니다." 같은 서버 메시지를 그대로 보여준다.
    showPageError(error.message);
    return;
  }
  currentUser = await mePromise;
  pageStatus.hidden = true;
  render(post);
}

function showPageError(message) {
  pageStatus.hidden = true;
  detail.hidden = true;
  ownerPanel.hidden = true;
  pageErrorText.textContent = message;
  pageError.hidden = false;
}

// ---------- 그리기 ----------

function render(post) {
  document.title = `${post.title} | Campus Books`; // document.title은 글자로만 처리되어 안전하다.
  renderDetail(post);
  detail.hidden = false;

  if (currentUser !== null && currentUser.id === post.seller.id) {
    renderOwnerActions(post);
    ownerPanel.hidden = false;
  } else {
    ownerPanel.hidden = true;
  }
}

function renderDetail(post) {
  const created = formatDate(post.created_at);
  const updated = formatDate(post.updated_at);

  const info = el("dl", { className: "post-detail__info" });
  const addInfo = (label, value) => info.append(el("dt", { text: label }), el("dd", { text: value }));
  addInfo("교재명", post.book_title);
  if (post.course_name) addInfo("과목명", post.course_name);
  addInfo("책 상태", CONDITION_LABELS[post.condition] ?? post.condition);
  addInfo("판매자", post.seller.nickname);
  addInfo("작성", created);
  // 분 단위로 같으면 작성 직후라 수정 표시를 하지 않는다.
  if (updated !== created) addInfo("수정됨", updated);

  const description = post.description
    ? el("p", { className: "post-detail__description", text: post.description })
    : el("p", { className: "post-detail__description post-detail__description--empty", text: "설명이 없습니다." });

  // replaceChildren은 null을 건너뛰지 않으므로, 연락 영역이 없을 때를 대비해 걸러낸다.
  detail.replaceChildren(
    ...[
      renderGallery(post),
      el("div", { className: "post-detail__top" }, statusBadge(post.status)),
      el("h1", { className: "post-detail__title", text: post.title }),
      el("p", { className: "post-detail__price", text: formatPrice(post.price) }),
      info,
      renderContact(post),
      el("h2", { className: "post-detail__subtitle", text: "설명" }),
      description,
    ].filter(Boolean),
  );
}

/**
 * 사진 영역. 사진이 없으면 null.
 * 큰 사진 하나와, 2장 이상이면 아래에 작은 사진 버튼을 둔다. 버튼을 누르면 큰 사진이 바뀐다.
 */
function renderGallery(post) {
  const images = Array.isArray(post.images) ? post.images : [];
  if (images.length === 0) return null;

  const altFor = (index) => `${post.book_title} 사진 ${index + 1}/${images.length}`;
  const main = el("img", {
    className: "gallery__main",
    src: safeImageUrl(images[0].url),
    alt: altFor(0),
    decoding: "async",
  });
  const gallery = el("div", { className: "gallery" }, el("div", { className: "gallery__frame" }, main));
  if (images.length === 1) return gallery;

  const thumbs = images.map((image, index) => {
    const button = el(
      "button",
      {
        type: "button",
        className: "gallery__thumb",
        attrs: { "aria-label": `사진 ${index + 1} 크게 보기`, "aria-pressed": String(index === 0) },
      },
      el("img", { src: safeImageUrl(image.thumbnail_url), alt: "", loading: "lazy" }),
    );
    button.addEventListener("click", () => {
      main.src = safeImageUrl(image.url);
      main.alt = altFor(index);
      for (const other of thumbs) other.setAttribute("aria-pressed", String(other === button));
    });
    return button;
  });
  gallery.append(el("div", { className: "gallery__thumbs" }, ...thumbs));
  return gallery;
}

/**
 * 연락 방법 영역. 보여줄 것이 없으면 null을 돌려준다.
 * - 판매 완료: 더 연락할 이유가 없으므로 아무것도 보여주지 않는다. (이미 시작한 대화는 쪽지함에서 이어 간다)
 * - 로그인한 구매자: "문의하기"(쪽지). 내 글에는 보여주지 않는다. 서버도 400으로 막는다.
 * - 오픈채팅 링크가 있음: 새 탭으로 여는 버튼. noopener noreferrer로 열린 페이지가 이 창(window.opener)과 주소를 알 수 없게 한다.
 * - 로그인하지 않음: 서버가 링크를 비워 보냈을 수 있고 쪽지도 로그인이 필요하므로 로그인을 안내한다.
 */
function renderContact(post) {
  if (post.status === "SOLD") return null;

  const isOwner = currentUser !== null && currentUser.id === post.seller.id;
  const actions = [];
  if (currentUser !== null && !isOwner) actions.push(renderInquiryButton(post));

  const url = post.open_chat_url;
  if (typeof url === "string" && url.startsWith(OPEN_CHAT_PREFIX)) {
    actions.push(
      el("a", {
        // 쪽지 버튼이 있으면 그쪽을 주 버튼으로 두고, 오픈채팅은 보조 버튼으로 보여준다.
        className: actions.length > 0 ? "button" : "button button--primary",
        href: url,
        target: "_blank",
        rel: "noopener noreferrer",
        text: "오픈채팅으로 연락하기",
      }),
    );
  }

  if (currentUser === null) {
    return contactSection(
      el(
        "p",
        { className: "post-detail__contact-login" },
        "로그인하면 쪽지로 문의하거나 연락 방법을 볼 수 있어요. ",
        el("a", { href: authPageUrl(LOGIN_PAGE), text: "로그인" }),
      ),
    );
  }
  if (actions.length === 0) return null;
  return contactSection(
    el("div", { className: "post-detail__contact-actions" }, ...actions),
    el("p", { className: "form-error", attrs: { id: "contact-error", role: "alert" }, hidden: true }),
  );
}

// 누르면 대화방을 만들거나(201) 이미 있는 방(200)을 받아 대화 화면으로 이동한다.
function renderInquiryButton(post) {
  const button = el("button", { type: "button", className: "button button--primary", text: "쪽지로 문의하기" });
  button.addEventListener("click", async () => {
    const errorText = document.getElementById("contact-error");
    errorText.hidden = true;
    button.disabled = true;
    try {
      const conversation = await startConversation(post.id);
      window.location.href = `/static/chat.html?id=${encodeURIComponent(conversation.id)}`;
    } catch (error) {
      if (error.status === 401) {
        redirectToLogin();
        return;
      }
      // 400(내 글, 그사이 판매 완료됨), 404(그사이 삭제됨)는 서버 메시지를 그대로 보여준다.
      errorText.textContent = error.message;
      errorText.hidden = false;
      button.disabled = false;
    }
  });
  return button;
}

function contactSection(...content) {
  return el(
    "section",
    { className: "post-detail__contact", attrs: { "aria-label": "연락 방법" } },
    el("h2", { className: "post-detail__subtitle", text: "연락하기" }),
    ...content,
  );
}

function renderOwnerActions(post) {
  const nextStatuses = ALLOWED_TRANSITIONS[post.status] ?? [];

  // 판매 완료된 글은 서버가 수정을 막으므로(400) 수정 버튼을 보여주지 않는다.
  const editLink =
    post.status !== "SOLD"
      ? el("a", { className: "button", href: `/static/post-form.html?id=${encodeURIComponent(post.id)}`, text: "수정" })
      : null;

  const statusButtons = nextStatuses.map((status) => {
    const button = el("button", { type: "button", className: "button", text: STATUS_BUTTON_LABELS[status] });
    button.addEventListener("click", () => onChangeStatus(post, status));
    return button;
  });

  const deleteButton = el("button", { type: "button", className: "button button--danger", text: "삭제" });
  deleteButton.addEventListener("click", () => onDelete(post));

  const soldNotice =
    nextStatuses.length === 0
      ? el("p", { className: "owner-panel__notice", text: "판매 완료된 글은 상태를 바꾸거나 수정할 수 없습니다." })
      : null;

  ownerActions.replaceChildren(
    ...[soldNotice, el("div", { className: "owner-actions__buttons" }, editLink, ...statusButtons, deleteButton)].filter(
      Boolean,
    ),
  );
}

// ---------- 동작 ----------

function onChangeStatus(post, status) {
  // 판매 완료는 되돌릴 수 없는 마지막 상태라 한 번 더 확인한다.
  if (status === "SOLD" && !window.confirm("판매 완료로 바꾸면 다시 되돌릴 수 없습니다. 계속할까요?")) return;

  runAction(async () => {
    const updated = await changePostStatus(post.id, status);
    // 서버가 돌려준 최신 글로 배지, 버튼, 수정 시각, 연락 버튼을 다시 그린다.
    render(updated);
  });
}

function onDelete(post) {
  if (!window.confirm("이 글을 삭제할까요? 삭제한 글은 되돌릴 수 없습니다.")) return;

  runAction(async () => {
    await deletePost(post.id);
    // replace를 써서, 뒤로 가기를 눌렀을 때 삭제된 글 화면이 다시 나오지 않게 한다.
    window.location.replace(HOME_PAGE);
  });
}

/**
 * 상태 변경·삭제의 공통 처리: 중복 클릭 방지, 에러 표시, 토큰 만료 처리.
 * 성공하면 task가 화면을 다시 그리거나 이동하므로 버튼을 다시 켜지 않는다.
 */
async function runAction(task) {
  hideActionError();
  setBusy(true);
  try {
    await task();
  } catch (error) {
    if (error.status === 401) {
      // 토큰이 만료되었다. (api.js가 토큰을 이미 지웠다) 로그인 후 이 글로 돌아오게 한다.
      redirectToLogin();
      return;
    }
    // 400(판매 완료된 글), 403(남의 글), 404(이미 삭제된 글)는 서버 메시지를 그대로 보여준다.
    actionError.textContent = error.message;
    actionError.hidden = false;
    setBusy(false);
  }
}

function setBusy(isBusy) {
  for (const button of ownerActions.querySelectorAll("button")) button.disabled = isBusy;
}

function hideActionError() {
  actionError.textContent = "";
  actionError.hidden = true;
}
