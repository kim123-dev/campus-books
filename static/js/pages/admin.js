// 신고 관리 화면 (관리자 전용): 신고 카드 목록과 처리(기각·글 삭제·기간 정지).
// 관리자가 아니면 목록 화면으로 보낸다. 화면을 숨기는 것은 편의일 뿐이고, 권한은 서버가 /admin API마다 확인한다.
// 상태 탭과 페이지 번호는 주소창(?status=RESOLVED&page=2)에 저장한다.
import { listAdminReports, resolveReport } from "../api.js";
import { redirectToLogin, renderHeader } from "../auth.js";
import { REPORT_REASONS } from "../safety.js";
import { getToken } from "../token.js";
import { el, formatDate, formatMonthDayTime, renderPagination } from "../ui.js";

const HOME_PAGE = "/static/index.html";
const PAGE_SIZE = 20;
const STATUSES = ["PENDING", "RESOLVED", "ALL"];
// 신고 창의 "기타 (설명 필수)" 같은 입력 안내는 관리 화면에서 필요 없으므로 괄호 부분을 뺀다.
const REASON_LABELS = Object.fromEntries(REPORT_REASONS.map(([value, label]) => [value, label.replace(/\s*\(.*\)$/, "")]));
// 서버 규칙과 같은 값. (app/models/report.py, app/schemas/admin.py) 최종 검사는 서버가 한다.
export const ACTION_LABELS = { DISMISS: "기각", DELETE_POST: "글 삭제", SUSPEND: "기간 정지", HIDE_REVIEW: "후기 숨김" };
const TARGET_LABELS = { POST: "글 신고", USER: "사용자 신고", REVIEW: "후기 신고" };
const RATING_TEXT = { GOOD: "좋아요", BAD: "아쉬워요" };
const SUSPEND_DAY_OPTIONS = [1, 3, 7, 30];
const MAX_NOTE = 500;

const main = document.getElementById("admin-main");
const notice = document.getElementById("admin-notice");
const summary = document.getElementById("result-summary");
const listError = document.getElementById("list-error");
const list = document.getElementById("report-list");
const pagination = document.getElementById("pagination");

// 응답이 늦게 도착한 이전 요청이 최신 결과를 덮어쓰지 않도록 요청마다 번호를 붙인다.
let latestRequestId = 0;

init();

async function init() {
  if (!getToken()) {
    redirectToLogin();
    return;
  }
  const me = await renderHeader(document.getElementById("site-header"));
  if (me === null) {
    if (!getToken()) {
      redirectToLogin();
    } else {
      main.hidden = false;
      showError("서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
    }
    return;
  }
  if (me.role !== "ADMIN") {
    leave();
    return;
  }
  main.hidden = false;
  window.addEventListener("popstate", load);
  load();
}

// 관리자가 아니면 이 화면을 기록에 남기지 않고 목록으로 보낸다. (뒤로 가기로 다시 오지 않게)
function leave() {
  window.location.replace(HOME_PAGE);
}

// ---------- 불러오기와 그리기 ----------

function readQuery() {
  const params = new URLSearchParams(window.location.search);
  const status = STATUSES.includes(params.get("status")) ? params.get("status") : "PENDING";
  return { status, page: params.get("page") ?? "1" };
}

async function load() {
  const requestId = ++latestRequestId;
  const { status, page } = readQuery();
  markTab(status);
  summary.textContent = "불러오는 중…";
  listError.hidden = true;
  list.replaceChildren();
  pagination.replaceChildren();

  let data;
  try {
    data = await listAdminReports({ status: status === "ALL" ? undefined : status, page, size: PAGE_SIZE });
  } catch (error) {
    if (requestId !== latestRequestId) return;
    if (error.status === 401) {
      redirectToLogin();
      return;
    }
    if (error.status === 403) {
      leave();
      return;
    }
    showError(error.fieldErrors?.page ?? error.message);
    return;
  }
  if (requestId !== latestRequestId) return;
  render(data);
}

function markTab(status) {
  for (const tab of document.querySelectorAll(".tabs__item")) {
    if (tab.dataset.status === status) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
  }
}

function render({ items, total, page, size }) {
  const totalPages = Math.max(1, Math.ceil(total / size));
  if (total === 0) {
    summary.textContent = "신고가 없습니다.";
    return;
  }
  summary.textContent = items.length === 0 ? `이 페이지에는 신고가 없습니다. (전체 ${total}건)` : `총 ${total}건`;
  list.replaceChildren(...items.map(renderReportCard));
  renderPagination(pagination, page, totalPages, goToPage);
}

function goToPage(page) {
  const params = new URLSearchParams(window.location.search);
  if (page > 1) params.set("page", String(page));
  else params.delete("page");
  history.pushState(null, "", `?${params}`);
  load();
  window.scrollTo({ top: 0 });
}

// ---------- 신고 카드 ----------

function renderReportCard(report) {
  const isPost = report.target_type === "POST";
  const resolved = report.status === "RESOLVED";
  const titleId = `report-${report.id}-title`;

  const card = el(
    "li",
    {
      className: `card report-card${resolved ? " report-card--resolved" : ""}`,
      attrs: { "aria-labelledby": titleId },
    },
    el(
      "div",
      { className: "report-card__head" },
      el("span", { className: "report-card__type", text: TARGET_LABELS[report.target_type] ?? report.target_type }),
      el("h2", {
        id: titleId,
        className: "report-card__reason",
        text: `#${report.id} ${REASON_LABELS[report.reason] ?? report.reason}`,
      }),
      el("span", {
        className: `report-card__status${resolved ? " report-card__status--done" : ""}`,
        text: resolved ? "처리됨" : "미처리",
      }),
    ),
    el("p", { className: "report-card__meta", text: `${formatDate(report.created_at)} 접수` }),
    renderPeople(report),
    isPost ? renderSnapshot(report) : null,
    report.review ? renderReviewTarget(report.review) : null,
    report.description ? el("p", { className: "report-card__description", text: report.description }) : null,
    !resolved && report.other_pending_count > 0
      ? el("p", {
          className: "report-card__more",
          text: `이 사용자에 대한 미처리 신고가 ${report.other_pending_count}건 더 있습니다.`,
        })
      : null,
    resolved ? renderResolution(report.resolution) : renderActions(report),
  );
  return card;
}

function renderPeople({ reporter, reported_user: reported }) {
  const reportedText = reported ? reported.nickname : "(탈퇴한 사용자)";
  const people = el(
    "p",
    { className: "report-card__people" },
    `신고자 ${reporter ? reporter.nickname : "(탈퇴한 사용자)"} → 대상 `,
    el("strong", { text: reportedText }),
  );
  if (reported?.suspended_until) {
    people.append(
      el("span", {
        className: "report-card__suspended",
        text: `${formatMonthDayTime(reported.suspended_until)}까지 정지 중`,
      }),
    );
  }
  return people;
}

function renderSnapshot(report) {
  const title = report.post_exists
    ? el("a", { href: `/static/post.html?id=${encodeURIComponent(report.target_id)}`, text: report.post_title_snapshot ?? "(제목 없음)" })
    : el("span", { text: report.post_title_snapshot ?? "(제목 없음)" });
  return el(
    "div",
    { className: "report-card__snapshot" },
    el(
      "p",
      { className: "report-card__snapshot-title" },
      title,
      report.post_exists ? null : el("span", { className: "report-card__deleted", text: "글 삭제됨" }),
    ),
    el("p", {
      className: "report-card__snapshot-content",
      text: report.post_content_snapshot || "설명이 없는 글입니다.",
    }),
    el("p", { className: "report-card__snapshot-hint", text: "신고 시점의 글 내용입니다." }),
  );
}

/** 후기 신고의 대상 후기. 후기는 작성자가 고치거나 지울 수 없어 지금 내용이 곧 신고 시점의 내용이다. */
function renderReviewTarget(review) {
  const reviewee = review.reviewee ? `${review.reviewee.nickname}님이 받은 후기` : "탈퇴한 사용자가 받은 후기";
  return el(
    "div",
    { className: "report-card__snapshot" },
    el(
      "p",
      { className: "report-card__snapshot-title" },
      el("span", { text: `${RATING_TEXT[review.rating] ?? review.rating} · ${review.book_title}` }),
      review.hidden ? el("span", { className: "report-card__deleted", text: "숨김" }) : null,
    ),
    el("p", { className: "report-card__snapshot-content", text: review.content || "글 없이 평가만 남긴 후기입니다." }),
    el("p", { className: "report-card__snapshot-hint", text: reviewee }),
  );
}

function renderResolution(resolution) {
  if (resolution === null) return null;
  const by = resolution.resolved_by ? resolution.resolved_by.nickname : "(삭제된 관리자)";
  return el(
    "div",
    { className: "report-card__resolution" },
    el("p", {
      className: "report-card__resolution-line",
      text: `${ACTION_LABELS[resolution.action] ?? resolution.action} · ${by} · ${formatDate(resolution.resolved_at)}`,
    }),
    resolution.resolved_with_report_id
      ? el("p", { className: "report-card__resolution-with", text: `신고 #${resolution.resolved_with_report_id}와 함께 처리` })
      : null,
    resolution.note ? el("p", { className: "report-card__note", text: `메모: ${resolution.note}` }) : null,
  );
}

// ---------- 처리 ----------

function renderActions(report) {
  const prefix = `report-${report.id}`;
  const canDeletePost = report.target_type === "POST" && report.post_exists === true;
  const canHideReview = report.review !== null && report.review !== undefined && !report.review.hidden;
  const canSuspend = report.reported_user !== null;
  const actions = [
    "DISMISS",
    ...(canDeletePost ? ["DELETE_POST"] : []),
    ...(canHideReview ? ["HIDE_REVIEW"] : []),
    ...(canSuspend ? ["SUSPEND"] : []),
  ];

  const radios = actions.map((action) =>
    el(
      "label",
      { className: "report-card__choice" },
      el("input", { type: "radio", name: `${prefix}-action`, value: action }),
      el("span", { text: ACTION_LABELS[action] }),
    ),
  );
  const days = el(
    "select",
    { id: `${prefix}-days`, name: "suspend_days" },
    ...SUSPEND_DAY_OPTIONS.map((day) => el("option", { value: String(day), text: `${day}일` })),
  );
  const daysField = el(
    "div",
    { className: "report-card__days", hidden: true },
    el("label", { htmlFor: `${prefix}-days`, text: "정지 기간" }),
    days,
  );
  const together = el("input", { type: "checkbox", id: `${prefix}-together` });
  const togetherField = el(
    "label",
    { className: "report-card__together", htmlFor: `${prefix}-together`, hidden: true },
    together,
    el("span", { text: `같은 사용자의 미처리 신고 ${report.other_pending_count}건도 함께 처리` }),
  );
  const note = el("textarea", { id: `${prefix}-note`, rows: 2, maxLength: MAX_NOTE });
  const errorText = el("p", { className: "form-error", attrs: { role: "alert" }, hidden: true });
  const submit = el("button", { type: "submit", className: "button button--primary", text: "처리하기" });

  const form = el(
    "form",
    { className: "report-card__actions", noValidate: true },
    el(
      "fieldset",
      { className: "report-card__choices" },
      el("legend", { text: "조치" }),
      ...radios,
    ),
    daysField,
    togetherField,
    el("div", { className: "field" }, el("label", { htmlFor: `${prefix}-note`, text: "처리 메모 (선택)" }), note),
    errorText,
    submit,
  );

  // 고른 조치에 따라 필요한 칸만 보여준다. 글 삭제는 "함께 처리"를 쓸 수 없다. (서버도 422로 막는다)
  form.addEventListener("change", () => {
    const action = form.elements[`${prefix}-action`].value;
    daysField.hidden = action !== "SUSPEND";
    togetherField.hidden = !(report.other_pending_count > 0 && (action === "DISMISS" || action === "SUSPEND"));
    if (togetherField.hidden) together.checked = false;
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorText.hidden = true;
    const action = form.elements[`${prefix}-action`].value;
    if (!action) {
      showFormError(errorText, "조치를 골라 주세요.");
      return;
    }
    const data = { action, note: note.value.trim() || null, include_same_user: together.checked };
    if (action === "SUSPEND") data.suspend_days = Number(days.value);
    if (!window.confirm(confirmText(report, data))) return;

    submit.disabled = true;
    submit.textContent = "처리 중…";
    try {
      const result = await resolveReport(report.id, data);
      const extra = result.resolved_ids.length - 1;
      showNotice(
        `신고 #${report.id}을(를) ${ACTION_LABELS[action]}(으)로 처리했습니다.` +
          (extra > 0 ? ` 함께 처리한 신고 ${extra}건.` : "") +
          (result.suspended_until ? ` ${formatMonthDayTime(result.suspended_until)}까지 정지됩니다.` : ""),
      );
      // 함께 처리된 카드도 바뀌므로 목록을 서버 기준으로 다시 그린다.
      load();
    } catch (error) {
      if (error.status === 401) {
        redirectToLogin();
        return;
      }
      if (error.status === 403) {
        leave();
        return;
      }
      // 409(다른 관리자가 먼저 처리), 400(그사이 글이 삭제됨 등)은 서버 메시지를 보여준다.
      showFormError(errorText, error.message);
      submit.disabled = false;
      submit.textContent = "처리하기";
    }
  });
  return form;
}

function confirmText(report, data) {
  const target = report.reported_user ? `${report.reported_user.nickname}님` : "대상";
  const lines = [`신고 #${report.id}을(를) 처리할까요? 처리한 신고는 되돌릴 수 없어요.`, ""];
  if (data.action === "DISMISS") lines.push("· 기각: 조치 없이 처리 완료로 표시합니다.");
  if (data.action === "DELETE_POST") {
    lines.push(`· 글 삭제: "${report.post_title_snapshot}" 글과 사진을 지웁니다.`);
    lines.push("· 같은 글에 대한 다른 미처리 신고도 함께 처리됩니다.");
  }
  if (data.action === "HIDE_REVIEW") {
    lines.push("· 후기 숨김: 프로필 목록과 매너 점수에서 이 후기를 뺍니다.");
    lines.push("· 같은 후기에 대한 다른 미처리 신고도 함께 처리됩니다.");
  }
  if (data.action === "SUSPEND") {
    lines.push(`· 기간 정지: ${target}을(를) ${data.suspend_days}일 동안 정지합니다.`);
    lines.push("· 정지 중에는 로그인과 글쓰기·쪽지·찜·신고를 할 수 없습니다.");
  }
  if (data.include_same_user) lines.push(`· ${target}에 대한 미처리 신고 ${report.other_pending_count}건도 같은 조치로 처리합니다.`);
  return lines.join("\n");
}

function showFormError(errorText, message) {
  errorText.textContent = message;
  errorText.hidden = false;
}

function showNotice(message) {
  notice.textContent = message;
  notice.hidden = false;
}

function showError(message) {
  summary.textContent = "";
  listError.textContent = message;
  listError.hidden = false;
}
