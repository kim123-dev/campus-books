// 프로필 화면: 닉네임, 매너 학점, 판매 중인 글, 받은 거래 후기. 로그인하지 않아도 볼 수 있다.
// 글과 후기는 각자 페이지를 넘긴다. 둘을 함께 주소에 담으면 복잡해지므로 페이지 번호는 화면 안에서만 기억한다.
import { getProfile, listProfilePosts, listProfileReviews, reportReview } from "../api.js";
import { renderHeader } from "../auth.js";
import { REPORT_DONE_TEXT, openReportDialog } from "../safety.js";
import { RATING_LABELS, REVIEWEE_ROLE_LABELS } from "../trade.js";
import { el, formatDate, readPostIdFromUrl, renderPagination, renderPostCard } from "../ui.js";

const PAGE_SIZE = 10;
// 매너 학점의 만점. 서버(review_service.MANNER_GPA_MAX)와 같은 값이어야 한다. (tests/test_static.py가 확인)
const MAX_GPA = 4.5;

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
  // 프로필·글·후기를 한꺼번에 요청한다. 글·후기는 숨겨 둔 칸에 먼저 그려지고, 프로필이 오면 함께 보인다.
  // 없거나 탈퇴한 사용자면 세 요청 모두 404이고, 화면은 프로필의 오류만 보여준다.
  loadPosts(1);
  loadReviews(1);
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
}

/**
 * 매너 학점(4.5 만점)과 등급, 채워진 막대, 받은 후기 수. 학점·등급은 서버가 계산해 준다.
 * 후기가 없어도 기본 학점(3.5, B+)을 보여주고, 아직 후기가 없다는 안내를 붙인다.
 */
function renderManner({ good, bad, total, gpa, grade }) {
  const box = document.getElementById("profile-manner");
  const bar = el("div", { className: "manner-gpa__bar", attrs: { "aria-hidden": "true" } }, el("span", { className: "manner-gpa__fill" }));
  // 막대 길이는 학점에 비례한다. (0.0~4.5 → 0~100%)
  bar.firstElementChild.style.width = `${Math.round((gpa / MAX_GPA) * 100)}%`;
  box.replaceChildren(
    el(
      "p",
      { className: "manner-gpa" },
      el("span", { className: "manner-gpa__label", text: "매너 학점" }),
      el("strong", { className: "manner-gpa__score", text: gpa.toFixed(1) }),
      el("span", { className: "manner-gpa__max", text: ` / ${MAX_GPA.toFixed(1)}` }),
      el("span", { className: "manner-gpa__grade", text: grade }),
    ),
    bar,
    total === 0
      ? el("p", { className: "profile__manner-note", text: "아직 받은 거래 후기가 없어 기본 학점이에요." })
      : el(
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
  // 로그인했고 내가 쓴 후기가 아니면 신고할 수 있다. (is_mine: 로그인하지 않았으면 null)
  const notice = el("p", { className: "safety-notice", attrs: { role: "status" }, hidden: true });
  let reportButton = null;
  if (review.is_mine === false) {
    reportButton = el("button", { type: "button", className: "link-button review__report", text: "신고" });
    reportButton.addEventListener("click", async () => {
      const reported = await openReportDialog({
        heading: "후기 신고",
        targetText: `${review.reviewer_nickname}님이 남긴 후기`,
        send: (data) => reportReview(review.id, data),
      });
      if (reported) {
        notice.textContent = REPORT_DONE_TEXT;
        notice.hidden = false;
      }
    });
  }
  return el(
    "li",
    { className: "card review" },
    el(
      "div",
      { className: "review__top" },
      el("span", { className: `rating rating--${rating}`, text: RATING_LABELS[review.rating] ?? review.rating }),
      el("span", { className: "review__role", text: REVIEWEE_ROLE_LABELS[review.reviewee_role] ?? "" }),
      reportButton,
    ),
    review.content ? el("p", { className: "review__content", text: review.content }) : null,
    el("p", {
      className: "review__meta",
      text: `${review.reviewer_nickname} · ${review.book_title} · ${formatDate(review.created_at)}`,
    }),
    notice,
  );
}

function showPageError(message) {
  pageStatus.hidden = true;
  profile.hidden = true;
  pageErrorText.textContent = message;
  pageError.hidden = false;
}
