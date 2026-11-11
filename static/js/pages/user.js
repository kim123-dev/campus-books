// 프로필 화면: 닉네임, 매너 점수, 판매 중인 글, 받은 거래 후기. 로그인하지 않아도 볼 수 있다.
// 글과 후기는 각자 페이지를 넘긴다. 둘을 함께 주소에 담으면 복잡해지므로 페이지 번호는 화면 안에서만 기억한다.
import { getProfile, listProfilePosts, listProfileReviews } from "../api.js";
import { renderHeader } from "../auth.js";
import { RATING_LABELS, REVIEWEE_ROLE_LABELS } from "../trade.js";
import { el, formatDate, readPostIdFromUrl, renderPagination, renderPostCard } from "../ui.js";

const PAGE_SIZE = 10;

const pageStatus = document.getElementById("page-status");
const pageError = document.getElementById("page-error");
const pageErrorText = document.getElementById("page-error-text");
const profile = document.getElementById("profile");

renderHeader(document.getElementById("site-header"));
// 주소의 ?id=는 글 상세와 같은 형식(양의 정수)이라 같은 검사 함수를 쓴다.
const userId = readPostIdFromUrl();
if (userId === null) {
  showPageError("프로필 주소가 올바르지 않습니다.");
} else {
  init(userId);
}

async function init(id) {
  let data;
  try {
    data = await getProfile(id);
  } catch (error) {
    // 404 "사용자를 찾을 수 없습니다."(없거나 탈퇴) 같은 서버 메시지를 그대로 보여준다.
    showPageError(error.message);
    return;
  }
  document.title = `${data.nickname}님의 프로필 | Campus Books`; // document.title은 글자로만 처리되어 안전하다.
  document.getElementById("profile-name").textContent = data.nickname;
  renderManner(data.manner);
  pageStatus.hidden = true;
  profile.hidden = false;
  loadPosts(1);
  loadReviews(1);
}

/** 매너 점수. 후기가 3개 미만이면 서버가 비율을 비워 보내므로(null) 개수만 보여준다. */
function renderManner({ good, bad, total, good_ratio: ratio }) {
  const box = document.getElementById("profile-manner");
  if (total === 0) {
    box.replaceChildren(el("p", { className: "profile__manner-note", text: "아직 받은 거래 후기가 없어요." }));
    return;
  }
  const headline =
    ratio === null
      ? el("p", { className: "profile__manner-note", text: "아직 후기가 적어요. 후기가 3개 이상이면 좋아요 비율을 보여줘요." })
      : el("p", { className: "profile__ratio" }, el("strong", { text: `${ratio}%` }), " 좋아요");
  box.replaceChildren(
    headline,
    el(
      "p",
      { className: "profile__counts" },
      el("span", { className: "rating rating--good", text: `${RATING_LABELS.GOOD} ${good}` }),
      el("span", { className: "rating rating--bad", text: `${RATING_LABELS.BAD} ${bad}` }),
    ),
  );
}

// ---------- 판매 중인 글 ----------

async function loadPosts(page) {
  const summary = document.getElementById("posts-summary");
  const list = document.getElementById("post-list");
  const pagination = document.getElementById("posts-pagination");
  summary.textContent = "불러오는 중…";
  try {
    const data = await listProfilePosts(userId, { page, size: PAGE_SIZE });
    summary.textContent = data.total === 0 ? "판매 중인 글이 없어요." : `${data.total}개`;
    list.replaceChildren(...data.items.map((post) => renderPostCard(post)));
    renderPagination(pagination, data.page, Math.max(1, Math.ceil(data.total / data.size)), (next) => {
      loadPosts(next);
      document.getElementById("posts-title").scrollIntoView();
    });
  } catch (error) {
    summary.textContent = error.message;
  }
}

// ---------- 받은 후기 ----------

async function loadReviews(page) {
  const summary = document.getElementById("reviews-summary");
  const list = document.getElementById("review-list");
  const pagination = document.getElementById("reviews-pagination");
  summary.textContent = "불러오는 중…";
  try {
    const data = await listProfileReviews(userId, { page, size: PAGE_SIZE });
    summary.textContent = data.total === 0 ? "받은 후기가 없어요." : `${data.total}개`;
    list.replaceChildren(...data.items.map(renderReview));
    renderPagination(pagination, data.page, Math.max(1, Math.ceil(data.total / data.size)), (next) => {
      loadReviews(next);
      document.getElementById("reviews-title").scrollIntoView();
    });
  } catch (error) {
    summary.textContent = error.message;
  }
}

function renderReview(review) {
  const rating = review.rating === "GOOD" ? "good" : "bad";
  return el(
    "li",
    { className: "card review" },
    el(
      "div",
      { className: "review__top" },
      el("span", { className: `rating rating--${rating}`, text: RATING_LABELS[review.rating] ?? review.rating }),
      el("span", { className: "review__role", text: REVIEWEE_ROLE_LABELS[review.reviewee_role] ?? "" }),
    ),
    review.content ? el("p", { className: "review__content", text: review.content }) : null,
    el("p", {
      className: "review__meta",
      text: `${review.reviewer_nickname} · ${review.book_title} · ${formatDate(review.created_at)}`,
    }),
  );
}

function showPageError(message) {
  pageStatus.hidden = true;
  profile.hidden = true;
  pageErrorText.textContent = message;
  pageError.hidden = false;
}
