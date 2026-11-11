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

/** 관리 기록의 추가 정보(detail)를 사람이 읽는 문장 목록으로 바꾼다. */
export function describeDetail(detail) {
  const lines = [];
  if (detail.report_id) lines.push(`신고 #${detail.report_id} 처리`);
  if (detail.resolved_ids?.length > 1) lines.push(`함께 처리한 신고 ${detail.resolved_ids.length - 1}건`);
  if (detail.days) lines.push(`${detail.days}일 정지`);
  if (detail.suspended_until) lines.push(`${formatMonthDayTime(detail.suspended_until)}까지`);
  if (detail.previous_until) lines.push(`원래 ${formatMonthDayTime(detail.previous_until)}까지였음`);
  if (detail.post_title) lines.push(`글: ${detail.post_title}${detail.book_title ? ` (${detail.book_title})` : ""}`);
  if (detail.email_banned) lines.push("이메일 재가입 차단");
  return lines;
}
