// 상세 화면: 글 정보를 보여주고, 내 글이면 상태 변경과 삭제를 할 수 있게 한다.
// 권한과 상태 규칙의 최종 판단은 서버가 한다. 화면은 누를 수 없는 버튼을 미리 숨기는 정도만 한다.
import { changePostStatus, deletePost, getPost } from "../api.js";
import { redirectToLogin, renderHeader } from "../auth.js";
import { CONDITION_LABELS, el, formatDate, formatPrice, readPostIdFromUrl, statusBadge } from "../ui.js";

const HOME_PAGE = "/static/index.html";

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
  const me = await mePromise;
  pageStatus.hidden = true;
  render(post, me !== null && me.id === post.seller.id);
}

function showPageError(message) {
  pageStatus.hidden = true;
  detail.hidden = true;
  ownerPanel.hidden = true;
  pageErrorText.textContent = message;
  pageError.hidden = false;
}

// ---------- 그리기 ----------

function render(post, isOwner) {
  document.title = `${post.title} | Campus Books`; // document.title은 글자로만 처리되어 안전하다.
  renderDetail(post);
  detail.hidden = false;

  if (isOwner) {
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

  detail.replaceChildren(
    el("div", { className: "post-detail__top" }, statusBadge(post.status)),
    el("h1", { className: "post-detail__title", text: post.title }),
    el("p", { className: "post-detail__price", text: formatPrice(post.price) }),
    info,
    el("h2", { className: "post-detail__subtitle", text: "설명" }),
    description,
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
    // 서버가 돌려준 최신 글로 배지, 버튼, 수정 시각을 다시 그린다.
    render(updated, true);
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
