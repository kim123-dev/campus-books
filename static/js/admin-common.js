// 관리자 화면 공통: 로그인·권한 확인, 관리 메뉴, 오류 처리, 관리 기록 표시 문구.
// 관리자가 아니면 목록 화면으로 보낸다. 화면을 숨기는 것은 편의일 뿐이고, 권한은 서버가 /admin API마다 확인한다.
import { redirectToLogin, renderHeader } from "./auth.js";
import { getToken } from "./token.js";
import { el, formatMonthDayTime } from "./ui.js";

const HOME_PAGE = "/static/index.html";

// 관리 메뉴. 화면마다 HTML 1개 + 스크립트 1개를 두고, 이 메뉴로 오간다.
export const ADMIN_PAGES = [
  { href: "/static/admin-dashboard.html", label: "대시보드" },
  { href: "/static/admin.html", label: "신고" },
  { href: "/static/admin-users.html", label: "사용자" },
  { href: "/static/admin-posts.html", label: "글" },
  { href: "/static/admin-reviews.html", label: "후기" },
  { href: "/static/admin-log.html", label: "기록" },
];

// 관리 기록의 조치 이름. 서버 값과 같다. (app/models/admin_action.py)
export const ADMIN_ACTION_LABELS = {
  DISMISS_REPORT: "신고 기각",
  DELETE_POST: "글 삭제",
  SUSPEND: "기간 정지",
  UNSUSPEND: "정지 해제",
  HIDE_REVIEW: "후기 숨김",
  UNHIDE_REVIEW: "후기 숨김 해제",
  WITHDRAW_USER: "강제 탈퇴",
  UNBAN_EMAIL: "재가입 차단 해제",
};

// 사유 글자 수 제한. 서버와 같은 값이다. (app/schemas/admin.py MAX_REASON_LENGTH)
export const MAX_REASON = 500;

/**
 * 관리자 화면을 시작한다. 헤더를 그리고 관리자인지 확인한 뒤, <main>을 보이고 관리 메뉴를 그린다.
 * @returns {Promise<object|null>} 관리자 정보. 로그인 화면이나 목록 화면으로 보냈으면 null
 */
export async function startAdminPage(main) {
  if (!getToken()) {
    redirectToLogin();
    return null;
  }
  const me = await renderHeader(document.getElementById("site-header"));
  if (me === null) {
    if (!getToken()) {
      redirectToLogin();
    } else {
      main.hidden = false;
      renderAdminNav();
      showPageError("서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
    }
    return null;
  }
  if (me.role !== "ADMIN") {
    leaveAdmin();
    return null;
  }
  main.hidden = false;
  renderAdminNav();
  return me;
}

/** 관리자가 아니면 이 화면을 기록에 남기지 않고 목록으로 보낸다. (뒤로 가기로 다시 오지 않게) */
export function leaveAdmin() {
  window.location.replace(HOME_PAGE);
}

/** 401·403은 화면을 옮기고 true를 돌려준다. 그 밖의 오류는 화면이 메시지를 보여준다. */
export function handleAuthError(error) {
  if (error.status === 401) {
    redirectToLogin();
    return true;
  }
  if (error.status === 403) {
    leaveAdmin();
    return true;
  }
  return false;
}

function renderAdminNav() {
  const container = document.getElementById("admin-nav");
  if (!container) return;
  const here = window.location.pathname;
  container.replaceChildren(
    ...ADMIN_PAGES.map((page) =>
      el("a", {
        className: "admin-nav__item",
        href: page.href,
        text: page.label,
        attrs: here === page.href ? { "aria-current": "page" } : {},
      }),
    ),
  );
}

function showPageError(message) {
  const target = document.getElementById("list-error");
  if (!target) return;
  target.textContent = message;
  target.hidden = false;
}

/** 관리 화면의 사용자 이름. 탈퇴한 사용자는 번호를 함께 보여준다. */
export function userLabel(user) {
  if (!user) return "(없음)";
  return user.withdrawn ? `탈퇴한 사용자 #${user.id}` : user.nickname;
}

/**
 * 사유를 꼭 적는 관리자 조치 폼. 사유가 비면 보내지 않고, 확인 창을 거쳐 onSubmit(사유)를 부른다.
 * 실패하면 서버 메시지를 폼 안에 보여주고 다시 누를 수 있게 한다. (409: 다른 관리자가 먼저 처리 등)
 * @param {{id: string, submitText: string, danger?: boolean, fields?: Node[], confirm: (reason: string) => string|null,
 *          onSubmit: (reason: string) => Promise<void>, reasonLabel?: string,
 *          validate?: () => string|null, cancel?: () => void}} options
 *   validate: 사유 말고 더 확인할 것이 있으면 오류 문구를 돌려준다. cancel: 있으면 "취소" 버튼을 함께 둔다. (창 안의 폼)
 */
export function reasonForm({
  id,
  submitText,
  danger = false,
  fields = [],
  confirm,
  onSubmit,
  reasonLabel = "사유 (필수)",
  validate = () => null,
  cancel = null,
}) {
  const reason = el("textarea", { id: `${id}-reason`, rows: 2, maxLength: MAX_REASON });
  const errorText = el("p", { className: "form-error", attrs: { role: "alert" }, hidden: true });
  const submit = el("button", {
    type: "submit",
    className: `button ${danger ? "button--danger" : "button--primary"}`,
    text: submitText,
  });
  const form = el(
    "form",
    { className: "admin-action-form", id, noValidate: true },
    ...fields,
    el("div", { className: "field" }, el("label", { htmlFor: reason.id, text: reasonLabel }), reason),
    errorText,
    cancel
      ? el(
          "div",
          { className: "admin-action-form__buttons" },
          el("button", { type: "button", className: "button", text: "취소", onclick: cancel }),
          submit,
        )
      : submit,
  );
  const showError = (message) => {
    errorText.textContent = message;
    errorText.hidden = false;
  };
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorText.hidden = true;
    const text = reason.value.trim();
    // 서버가 422로 막는 내용을 보내기 전에 알려준다.
    if (text === "") {
      showError("사유를 입력해 주세요.");
      reason.focus();
      return;
    }
    const invalid = validate();
    if (invalid) {
      showError(invalid);
      return;
    }
    const message = confirm(text);
    if (message === null || !window.confirm(message)) return;
    submit.disabled = true;
    submit.textContent = "처리 중…";
    try {
      await onSubmit(text);
    } catch (error) {
      if (handleAuthError(error)) return;
      showError(Object.values(error.fieldErrors ?? {})[0] ?? error.message);
      submit.disabled = false;
      submit.textContent = submitText;
    }
  });
  return form;
}

/**
 * 사유를 받는 관리자 조치 창(<dialog>). 조치가 끝나면 true, 취소하면 false로 끝난다.
 * 창을 한 번 더 거치는 것은 목록에서 잘못 눌러 바로 지우는 일을 막기 위해서다. (보내기 전 확인 창도 따로 뜬다)
 * @param {{title: string, targetText: string, submitText: string, fields?: Node[], validate?: () => string|null,
 *          confirm: (reason: string) => string|null, onSubmit: (reason: string) => Promise<void>}} options
 */
export function openReasonDialog({ title, targetText, submitText, fields = [], validate, confirm, onSubmit }) {
  const titleId = "admin-dialog-title";
  return new Promise((resolve) => {
    let done = false;
    const dialog = el("dialog", { className: "report-dialog admin-dialog", attrs: { "aria-labelledby": titleId } });
    const form = reasonForm({
      id: "admin-dialog-form",
      submitText,
      danger: true,
      fields: [
        el("h2", { id: titleId, className: "report-dialog__title", text: title }),
        el("p", { className: "report-dialog__target", text: targetText }),
        ...fields,
      ],
      validate,
      confirm,
      cancel: () => dialog.close(),
      onSubmit: async (reason) => {
        await onSubmit(reason);
        done = true;
        dialog.close();
      },
    });
    dialog.append(form);
    // Esc·취소·완료 모두 close 이벤트 한 곳에서 정리한다.
    dialog.addEventListener("close", () => {
      dialog.remove();
      resolve(done);
    });
    document.body.append(dialog);
    dialog.showModal();
    form.querySelector("textarea, input").focus();
  });
}

/** 관리 화면의 사용자 이름을 사용자 상세로 가는 링크로. 사용자가 없으면 글자만. */
export function adminUserLink(user, fallback = "(탈퇴한 사용자)") {
  if (!user) return el("span", { text: fallback });
  return el("a", { className: "admin-user-link", href: adminUserHref(user.id), text: userLabel(user) });
}

export function adminUserHref(userId) {
  return `/static/admin-user.html?id=${encodeURIComponent(userId)}`;
}

/** 계정 상태 이름표. 색만으로 구분하지 않도록 글자로 적는다. (사용자 목록·상세) */
export function userBadges(user) {
  const badges = [];
  if (user.withdrawn) badges.push(el("span", { className: "admin-badge", text: "탈퇴" }));
  if (user.role === "ADMIN") badges.push(el("span", { className: "admin-badge admin-badge--admin", text: "관리자" }));
  if (user.suspended_until) {
    badges.push(
      el("span", {
        className: "admin-badge admin-badge--suspend",
        text: `${formatMonthDayTime(user.suspended_until)}까지 정지`,
      }),
    );
  }
  return badges;
}

/** 관리 기록의 추가 정보(detail)를 사람이 읽는 문장 목록으로 바꾼다. */
export function describeDetail(detail) {
  const lines = [];
  if (detail.report_id) lines.push(`신고 #${detail.report_id} 처리`);
  if (detail.resolved_ids?.length > 1) lines.push(`함께 처리한 신고 ${detail.resolved_ids.length - 1}건`);
  if (detail.days) lines.push(`${detail.days}일 정지`);
  if (detail.suspended_until) lines.push(`${formatMonthDayTime(detail.suspended_until)}까지`);
  if (detail.previous_until) lines.push(`원래 ${formatMonthDayTime(detail.previous_until)}까지였음`);
  if (detail.post_title) lines.push(`글: ${detail.post_title}${detail.book_title ? ` (${detail.book_title})` : ""}`);
  else if (detail.book_title) lines.push(`교재: ${detail.book_title}`);
  if (detail.email_banned) lines.push("이메일 재가입 차단");
  return lines;
}
