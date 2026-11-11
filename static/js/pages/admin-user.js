// 사용자 상세 화면 (관리자 전용): 계정 정보(이메일 포함), 활동 수, 정지 이력.
// 숫자는 그 목록을 볼 수 있는 화면으로 이어진다. 주소: /static/admin-user.html?id=3
import {
  ADMIN_ACTION_LABELS,
  describeDetail,
  handleAuthError,
  startAdminPage,
  userBadges,
  userLabel,
} from "../admin-common.js";
import { getAdminUser } from "../api.js";
import { el, formatDate } from "../ui.js";

const main = document.getElementById("admin-main");
const title = document.getElementById("user-title");
const listError = document.getElementById("list-error");
const detail = document.getElementById("user-detail");

init();

async function init() {
  if ((await startAdminPage(main)) === null) return;
  const userId = new URLSearchParams(window.location.search).get("id") ?? "";
  if (!/^\d+$/.test(userId)) {
    showError("사용자 번호가 올바르지 않습니다.");
    return;
  }
  let user;
  try {
    user = await getAdminUser(userId);
  } catch (error) {
    if (handleAuthError(error)) return;
    showError(error.status === 404 ? "없는 사용자입니다." : error.message);
    return;
  }
  render(user);
}

function render(user) {
  title.textContent = userLabel(user);
  document.title = `${userLabel(user)} | 사용자 상세 | Campus Books`;
  const badges = userBadges(user);
  const badgeBox = document.getElementById("user-badges");
  badgeBox.replaceChildren(...badges);
  badgeBox.hidden = badges.length === 0;

  document.getElementById("user-info").replaceChildren(
    ...info("번호", `#${user.id}`),
    ...info("이메일", user.email ?? "(탈퇴로 지워짐)"),
    ...info("닉네임", userLabel(user)),
    ...info("가입", formatDate(user.created_at)),
  );

  const { counts } = user;
  const id = encodeURIComponent(user.id);
  document.getElementById("user-counts").replaceChildren(
    countTile("작성한 글", counts.posts),
    countTile("받은 신고", counts.reports_received, `/static/admin.html?status=ALL&reported_user_id=${id}`),
    countTile("미처리 신고", counts.reports_pending, `/static/admin.html?status=PENDING&reported_user_id=${id}`, {
      alert: counts.reports_pending > 0 ? "처리 필요" : null,
    }),
    countTile("받은 후기", counts.reviews_received, null, {
      note: counts.reviews_hidden > 0 ? `숨긴 후기 ${counts.reviews_hidden}개 포함` : null,
    }),
    countTile("쓴 후기", counts.reviews_written),
  );

  document.getElementById("log-link").href = `/static/admin-log.html?target_user_id=${id}`;
  const history = document.getElementById("suspension-list");
  history.replaceChildren(
    ...(user.suspensions.length
      ? user.suspensions.map(renderHistory)
      : [el("li", { className: "admin-card__meta", text: "정지 이력이 없습니다." })]),
  );
  detail.hidden = false;
}

function info(label, value) {
  return [el("dt", { text: label }), el("dd", { text: value })];
}

/** 숫자 타일. href가 있으면 타일 전체가 링크다. (대시보드와 같은 모양) */
function countTile(label, value, href = null, { note = null, alert = null } = {}) {
  const children = [
    el("span", { className: "stat-tile__label", text: label }),
    el("strong", { className: "stat-tile__value", text: value.toLocaleString("ko-KR") }),
    alert ? el("span", { className: "stat-tile__alert", text: alert }) : null,
    note ? el("span", { className: "stat-tile__note", text: note }) : null,
  ];
  const className = `card stat-tile${alert ? " stat-tile--alert" : ""}`;
  return href ? el("a", { className: `${className} stat-tile--link`, href }, ...children) : el("div", { className }, ...children);
}

function renderHistory(entry) {
  const details = describeDetail(entry.detail);
  return el(
    "li",
    { className: "card admin-card" },
    el(
      "div",
      { className: "admin-card__head" },
      el("span", {
        className: `admin-badge admin-badge--${entry.action.toLowerCase().replaceAll("_", "-")}`,
        text: ADMIN_ACTION_LABELS[entry.action] ?? entry.action,
      }),
      el("span", { className: "admin-card__meta", text: `${formatDate(entry.created_at)} · ${userLabel(entry.admin)}` }),
    ),
    el("p", { className: "admin-card__reason", text: entry.reason ? `사유: ${entry.reason}` : "사유 없음" }),
    details.length ? el("p", { className: "admin-card__meta", text: details.join(" · ") }) : null,
  );
}

function showError(message) {
  listError.textContent = message;
  listError.hidden = false;
}
