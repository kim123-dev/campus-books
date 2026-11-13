// 상세 화면: 글 정보를 보여주고, 내 글이면 상태 변경과 삭제를 할 수 있게 한다.
// 권한과 상태 규칙의 최종 판단은 서버가 한다. 화면은 누를 수 없는 버튼을 미리 숨기는 정도만 한다.
import {
  blockUser,
  changePostBuyer,
  changePostStatus,
  deletePost,
  getPost,
  getPostBuyer,
  reportPost,
  startConversation,
  unblockUser,
} from "../api.js";
import { LOGIN_PAGE, authPageUrl, redirectToLogin, renderHeader } from "../auth.js";
import {
  REPORT_DONE_TEXT,
  UNBLOCK_DONE_TEXT,
  blockDoneContent,
  confirmBlock,
  confirmUnblock,
  openReportDialog,
} from "../safety.js";
import {
  CONDITION_LABELS,
  MOBILE_QUERY,
  el,
  formatDate,
  formatPrice,
  readPostIdFromUrl,
  safeImageUrl,
  statusBadge,
} from "../ui.js";
import { openBuyerDialog } from "../trade.js";
import { createWishlistButton } from "../wishlist-button.js";

const HOME_PAGE = "/static/index.html";

// 서버가 허용하는 오픈채팅 주소의 시작 부분. 서버 검증(422)이 1차 방어이고,
// 화면도 이 형식일 때만 링크를 만들어 javascript: 같은 주소가 href에 들어가지 않게 한 번 더 막는다.
const OPEN_CHAT_PREFIX = "https://open.kakao.com/";

// 현재 상태에서 바꿀 수 있는 상태. 서버 app/services/post_service.py의 ALLOWED_TRANSITIONS와 같아야 한다.
// 어긋나더라도 서버가 400으로 막으므로, 여기서는 누르면 실패할 버튼을 보여주지 않는 용도다.
const ALLOWED_TRANSITIONS = {
  ON_SALE: ["RESERVED", "SOLD"],
  RESERVED: ["ON_SALE", "SOLD"],
  SOLD: ["ON_SALE"],
};

// "판매 완료으로"처럼 조사가 틀리지 않도록 버튼 문구를 따로 둔다.
const STATUS_BUTTON_LABELS = {
  ON_SALE: "판매 중으로 변경",
  RESERVED: "예약 중으로 변경",
  SOLD: "판매 완료로 변경",
};
// 판매 완료에서 판매 중으로 가는 버튼은 "변경"이 아니라 실수를 되돌리는 동작이라 문구와 색을 따로 둔다.
const REVERT_SOLD_LABEL = "판매 중으로 되돌리기";

const pageStatus = document.getElementById("page-status");
const pageError = document.getElementById("page-error");
const pageErrorText = document.getElementById("page-error-text");
const detail = document.getElementById("post-detail");
const ownerPanel = document.getElementById("owner-panel");
const ownerActions = document.getElementById("owner-actions");
const actionError = document.getElementById("action-error");

// 로그인한 사용자(없으면 null). 내 글인지, 연락 방법 안내를 어떻게 할지 고를 때 쓴다.
let currentUser = null;

// 모바일 하단 연락 바: 가격·찜 하트·문의 버튼을 화면 아래에 고정해, 긴 설명을 읽다가도 바로 문의할 수 있게 한다.
// 하트와 문의 버튼은 새로 만들지 않고 글 영역에서 옮겨 온다. (같은 버튼이 두 개면 찜 상태가 어긋나기 때문)
// PC(768px 이상)로 바뀌면 원래 자리로 되돌린다.
const mobileQuery = window.matchMedia(MOBILE_QUERY);
const contactBarRow = el("div", { className: "contact-bar__row" });
const contactBar = el("section", { className: "contact-bar", attrs: { "aria-label": "가격과 문의" }, hidden: true }, contactBarRow);
document.body.append(contactBar);
// 바에 넣을 것들. 바가 필요 없는 글(내 글·판매 완료·차단)이면 null.
let barParts = null;
mobileQuery.addEventListener("change", placeContactBar);

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

// 처음 상세를 받을 때 온 판매자의 매너 학점. (renderDetail 참고)
let sellerManner = null;

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
  // value: 글자 또는 요소(판매자 프로필 링크)
  const addInfo = (label, value) =>
    info.append(el("dt", { text: label }), typeof value === "string" ? el("dd", { text: value }) : el("dd", {}, value));
  addInfo("교재명", post.book_title);
  if (post.course_name) addInfo("과목명", post.course_name);
  addInfo("책 상태", CONDITION_LABELS[post.condition] ?? post.condition);
  // 판매자 이름을 누르면 프로필(매너 학점·받은 후기)로 간다.
  // 이름 옆에 매너 학점을 붙여, 프로필에 들어가지 않아도 어떤 판매자인지 보이게 한다.
  // 서버는 상세 조회에서만 학점을 준다. 상태 변경 응답으로 다시 그릴 때는 처음 받은 값을 그대로 쓴다.
  if (post.seller_manner) sellerManner = post.seller_manner;
  const manner = sellerManner;
  addInfo(
    "판매자",
    el(
      "span",
      { className: "post-detail__seller" },
      el("a", {
        className: "post-detail__seller-link",
        href: `/static/user.html?id=${encodeURIComponent(post.seller.id)}`,
        text: post.seller.nickname,
      }),
      manner && el("span", { className: "post-detail__seller-gpa", text: `매너 학점 ${manner.gpa.toFixed(1)} (${manner.grade})` }),
    ),
  );
  addInfo("작성", created);
  // 분 단위로 같으면 작성 직후라 수정 표시를 하지 않는다.
  if (updated !== created) addInfo("수정됨", updated);

  const description = post.description
    ? el("p", { className: "post-detail__description", text: post.description })
    : el("p", { className: "post-detail__description post-detail__description--empty", text: "설명이 없습니다." });

  const heart = renderWishlistButton(post);
  const contact = renderContact(post);
  // replaceChildren은 null을 건너뛰지 않으므로, 연락 영역이 없을 때를 대비해 걸러낸다.
  detail.replaceChildren(
    ...[
      renderGallery(post),
      el("div", { className: "post-detail__top" }, statusBadge(post.status), heart),
      el("h1", { className: "post-detail__title", text: post.title }),
      el("p", { className: "post-detail__price", text: formatPrice(post.price) }),
      info,
      contact,
      el("h2", { className: "post-detail__subtitle", text: "설명" }),
      description,
      renderSafety(post),
    ].filter(Boolean),
  );
  setupContactBar(post, heart, contact);
}

// ---------- 모바일 하단 연락 바 ----------

/**
 * 문의할 수 있는 글(내 글·판매 완료·차단한 판매자가 아님)에만 바를 만든다.
 * - 로그인: 찜 하트 + 가격 + "쪽지로 문의하기" (오픈채팅은 보조 버튼이라 글 영역에 남긴다)
 * - 비로그인: 찜 하트 + 가격 + "로그인하고 문의하기"
 */
function setupContactBar(post, heart, contact) {
  // 다시 그릴 때(상태 변경·차단) 이전 바의 버튼은 이미 지워진 글 영역의 것이므로 비운다.
  contactBarRow.replaceChildren();
  contactBar.querySelector("#contact-error")?.remove();
  barParts = null;
  const isOwner = currentUser !== null && currentUser.id === post.seller.id;
  if (post.status !== "SOLD" && post.is_seller_blocked !== true && !isOwner && contact !== null) {
    const inquiry = contact.querySelector("#inquiry-button");
    const error = contact.querySelector("#contact-error");
    const moved = [heart, inquiry, error].filter(Boolean).map((node) => {
      // 원래 자리를 표시해 두었다가 PC로 바뀌면 그 자리로 되돌린다.
      const marker = document.createComment("");
      node.before(marker);
      return { node, marker };
    });
    barParts = {
      heart,
      error,
      // 가격은 글 영역에도 있으므로 화면 낭독기에는 한 번만 읽히게 숨긴다.
      price: el("p", { className: "contact-bar__price", text: formatPrice(post.price), attrs: { "aria-hidden": "true" } }),
      primary:
        inquiry ?? el("a", { className: "button button--primary", href: authPageUrl(LOGIN_PAGE), text: "로그인하고 문의하기" }),
      moved,
      contact,
    };
  }
  placeContactBar();
}

/** 화면 폭에 맞춰 하트·문의 버튼을 바(모바일) 또는 글 영역(PC)에 둔다. */
function placeContactBar() {
  const onMobile = barParts !== null && mobileQuery.matches;
  if (barParts !== null) {
    const { heart, error, price, primary, moved, contact } = barParts;
    if (onMobile) {
      contactBarRow.replaceChildren(...[heart, price, primary].filter(Boolean));
      if (error) contactBar.prepend(error);
    } else {
      for (const { node, marker } of moved) marker.after(node);
    }
    // 문의 버튼을 옮긴 뒤 글 영역의 "연락하기"에 남은 것이 없으면 제목만 남지 않게 숨긴다.
    const actions = contact.querySelector(".post-detail__contact-actions");
    contact.hidden = onMobile && actions !== null && actions.children.length === 0;
  }
  contactBar.hidden = !onMobile;
  document.body.classList.toggle("has-contact-bar", onMobile);
}

// ---------- 신고·차단 ----------

/**
 * "이 글 신고"·"판매자 차단(또는 차단 해제)" 버튼과 결과 안내. 로그인한 사용자에게만, 내 글에는 없다.
 * 실제 권한 검사(본인 글·자기 자신 400)는 서버가 한다.
 */
function renderSafety(post) {
  if (currentUser === null || currentUser.id === post.seller.id) return null;
  const nickname = post.seller.nickname;

  const reportButton = el("button", { type: "button", className: "link-button", text: "이 글 신고" });
  reportButton.addEventListener("click", async () => {
    const reported = await openReportDialog({
      heading: "이 글 신고",
      targetText: `${post.title} (판매자 ${nickname})`,
      send: (data) => reportPost(post.id, data),
    });
    if (reported) showSafetyNotice(REPORT_DONE_TEXT);
  });

  const blockButton = post.is_seller_blocked
    ? el("button", { type: "button", className: "link-button", text: "판매자 차단 해제" })
    : el("button", { type: "button", className: "link-button link-button--danger", text: "판매자 차단" });
  blockButton.addEventListener("click", () => (post.is_seller_blocked ? onUnblock(post) : onBlock(post)));

  return el(
    "section",
    { className: "post-detail__safety", attrs: { "aria-label": "신고·차단" } },
    el("div", { className: "post-detail__safety-actions" }, reportButton, blockButton),
    el("p", { className: "safety-notice", attrs: { id: "safety-notice", role: "status" }, hidden: true }),
  );
}

async function onBlock(post) {
  if (!confirmBlock(post.seller.nickname)) return;
  await runSafetyAction(async () => {
    await blockUser(post.seller.id);
    // 서버 기준으로 다시 그려 문의·찜 버튼을 숨기고 "차단 해제"로 바꾼다.
    render(await getPost(post.id));
    showSafetyNotice(...blockDoneContent());
  });
}

async function onUnblock(post) {
  if (!confirmUnblock(post.seller.nickname)) return;
  await runSafetyAction(async () => {
    await unblockUser(post.seller.id);
    render(await getPost(post.id));
    showSafetyNotice(UNBLOCK_DONE_TEXT);
  });
}

async function runSafetyAction(task) {
  try {
    await task();
  } catch (error) {
    if (error.status === 401) {
      redirectToLogin();
      return;
    }
    // 404(그사이 탈퇴·삭제) 등은 서버 메시지를 그대로 보여준다.
    showSafetyNotice(error.message);
  }
}

function showSafetyNotice(...content) {
  const notice = document.getElementById("safety-notice");
  if (notice === null) return;
  notice.replaceChildren(...content);
  notice.hidden = false;
}

/**
 * 찜 하트. 내 글에는 없다. 판매 완료된 글은 찜해 둔 경우에만 (해제할 수 있게) 보여준다.
 * 로그인하지 않았으면 하트를 보여주고, 누르면 로그인 화면으로 보낸다.
 */
function renderWishlistButton(post) {
  if (currentUser !== null && currentUser.id === post.seller.id) return null;
  // 차단한 판매자의 글은 찜도 쪽지도 하지 않도록 하트를 숨긴다. (해제하면 다시 보인다)
  if (post.is_seller_blocked === true) return null;
  if (post.status === "SOLD" && post.is_wishlisted !== true) return null;
  return createWishlistButton(post, { className: "wish-button--detail" });
}

/**
 * 사진 영역. 사진이 없으면 null.
 * 사진을 가로로 이어 붙인 줄(track)을 한 장 너비의 칸으로 보여준다.
 * - 모바일: 손가락으로 좌우로 넘기고(scroll-snap), "1 / 3"으로 몇 번째인지 보여준다.
 * - PC: 줄이 스크롤되지 않게 두고, 아래 작은 사진 버튼을 누르면 그 사진으로 넘어간다. (이전과 같은 모습)
 * 작은 사진 버튼은 두 화면 모두에 있고, 보이는 사진과 눌린 버튼(aria-pressed)을 항상 같게 맞춘다.
 */
function renderGallery(post) {
  const images = Array.isArray(post.images) ? post.images : [];
  if (images.length === 0) return null;

  const slides = images.map((image, index) =>
    el("img", {
      className: "gallery__main",
      src: safeImageUrl(image.url),
      alt: `${post.book_title} 사진 ${index + 1}/${images.length}`,
      decoding: "async",
    }),
  );
  const track = el("div", { className: "gallery__track" }, ...slides);
  const frame = el("div", { className: "gallery__frame" }, track);
  const gallery = el("div", { className: "gallery" }, frame);
  if (images.length === 1) return gallery;

  // 몇 번째 사진인지. 사진의 대체 글에 같은 내용이 있어 화면 낭독기에는 숨긴다.
  const counter = el("span", { className: "gallery__counter mobile-only", attrs: { "aria-hidden": "true" } });
  frame.append(counter);
  let shownIndex = -1;
  const showIndex = (index) => {
    if (index === shownIndex) return;
    shownIndex = index;
    counter.textContent = `${index + 1} / ${images.length}`;
    for (const [i, thumb] of thumbs.entries()) thumb.setAttribute("aria-pressed", String(i === index));
  };
  // 넘기는 동안 scroll이 계속 오므로, 한 프레임에 한 번만 지금 보이는 사진을 계산한다.
  let frameRequested = false;
  track.addEventListener(
    "scroll",
    () => {
      if (frameRequested) return;
      frameRequested = true;
      window.requestAnimationFrame(() => {
        frameRequested = false;
        const index = Math.round(track.scrollLeft / Math.max(1, track.clientWidth));
        showIndex(Math.min(images.length - 1, Math.max(0, index)));
      });
    },
    { passive: true },
  );

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
      track.scrollTo({ left: index * track.clientWidth });
      showIndex(index);
    });
    return button;
  });
  gallery.append(el("div", { className: "gallery__thumbs" }, ...thumbs));
  showIndex(0);
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
  // 차단한 판매자에게는 서버도 문의를 막으므로(400) 버튼 대신 이유를 보여준다.
  if (post.is_seller_blocked === true) {
    return contactSection(
      el("p", {
        className: "post-detail__contact-login",
        text: "차단한 사용자의 글입니다. 차단을 해제하기 전까지 쪽지를 보낼 수 없어요.",
      }),
    );
  }

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
  const button = el("button", {
    type: "button",
    className: "button button--primary",
    text: "쪽지로 문의하기",
    attrs: { id: "inquiry-button" },
  });
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
    const isRevert = post.status === "SOLD" && status === "ON_SALE";
    const button = el("button", {
      type: "button",
      className: isRevert ? "button button--primary" : "button",
      text: isRevert ? REVERT_SOLD_LABEL : STATUS_BUTTON_LABELS[status],
    });
    button.addEventListener("click", () => onChangeStatus(post, status));
    return button;
  });

  const deleteButton = el("button", { type: "button", className: "button button--danger", text: "삭제" });
  deleteButton.addEventListener("click", () => onDelete(post));

  // 후기가 있어 되돌릴 수 없는 경우에도 버튼은 숨기지 않고, 누르면 서버의 409 메시지를 보여준다.
  const soldNotice =
    post.status === "SOLD"
      ? el("p", {
          className: "owner-panel__notice",
          text: "판매 완료된 글은 수정할 수 없어요. 후기를 남기기 전이면 판매 중으로 되돌릴 수 있어요.",
        })
      : null;

  // 판매 완료된 글은 거래한 사람(구매자)을 보여주고, 후기가 없으면 바꿀 수 있게 한다. (서버에서 따로 불러온다)
  const buyerLine = post.status === "SOLD" ? el("div", { className: "owner-panel__buyer", attrs: { id: "buyer-line" } }) : null;

  ownerActions.replaceChildren(
    ...[
      soldNotice,
      buyerLine,
      el("div", { className: "owner-actions__buttons" }, editLink, ...statusButtons, deleteButton),
    ].filter(Boolean),
  );
  if (buyerLine !== null) loadBuyerLine(post, buyerLine);
}

async function loadBuyerLine(post, line) {
  let info;
  try {
    info = await getPostBuyer(post.id);
  } catch {
    // 구매자 정보는 보조 정보라, 불러오지 못해도 나머지 관리 기능은 그대로 쓰게 한다.
    line.remove();
    return;
  }
  const name = info.buyer === null ? "선택 안 함" : info.buyer.nickname;
  const parts = [el("span", { text: `거래한 사람: ${name}` })];
  if (info.changeable) {
    const button = el("button", { type: "button", className: "link-button", text: "구매자 변경" });
    button.addEventListener("click", () => onChangeBuyer(post, info));
    parts.push(button);
  } else if (info.buyer !== null) {
    parts.push(el("span", { className: "owner-panel__buyer-note", text: "후기가 있어 바꿀 수 없어요." }));
  }
  line.replaceChildren(...parts);
}

// ---------- 동작 ----------

function onChangeStatus(post, status) {
  if (status === "SOLD") {
    onSell(post);
    return;
  }
  // 되돌리면 거래 기록이 지워져 구매자가 후기를 남길 수 없게 되므로 한 번 확인한다.
  if (
    post.status === "SOLD" &&
    !window.confirm("판매 중으로 되돌릴까요? 거래한 사람 기록이 지워져 서로 후기를 남길 수 없게 돼요.")
  ) {
    return;
  }
  runAction(async () => {
    const updated = await changePostStatus(post.id, status);
    // 서버가 돌려준 최신 글로 배지, 버튼, 수정 시각, 연락 버튼을 다시 그린다.
    render(updated);
  });
}

/** 판매 완료: 거래한 사람을 고르는 창을 띄운다. 후기가 남으면 되돌릴 수 없어 창 안에서 한 번 더 알린다. */
function onSell(post) {
  runAction(async () => {
    const info = await getPostBuyer(post.id);
    const updated = await openBuyerDialog({
      heading: "판매 완료로 변경",
      intro: "후기가 남은 뒤에는 판매 중으로 되돌릴 수 없어요. 거래한 사람은 후기를 남기기 전까지 바꿀 수 있어요.",
      candidates: info.candidates,
      currentBuyer: null,
      preselect: false,
      submitText: "판매 완료",
      send: (buyerId) => changePostStatus(post.id, "SOLD", buyerId),
    });
    // 취소했으면 그대로 두고 버튼만 다시 켠다.
    if (updated === null) {
      setBusy(false);
      return;
    }
    render(updated);
  });
}

/** 잘못 고른 구매자를 다른 사람이나 "선택 안 함"으로 바꾼다. 후기가 하나라도 있으면 서버가 409로 막는다. */
function onChangeBuyer(post, info) {
  runAction(async () => {
    const changed = await openBuyerDialog({
      heading: "구매자 변경",
      intro: "후기를 남기기 전까지만 바꿀 수 있어요. 후기를 쓸 수 있는 기간은 처음 판매 완료한 날부터 계산돼요.",
      candidates: info.candidates,
      currentBuyer: info.buyer,
      preselect: true,
      submitText: "변경",
      send: (buyerId) => changePostBuyer(post.id, buyerId),
    });
    if (changed === null) {
      setBusy(false);
      return;
    }
    render(await getPost(post.id));
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
    // 400(바꿀 수 없는 상태), 403(남의 글), 404(이미 삭제된 글), 409(후기가 있어 되돌릴 수 없음)는 서버 메시지를 그대로 보여준다.
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
