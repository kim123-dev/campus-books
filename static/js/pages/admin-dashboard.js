// 관리자 대시보드: 가입자·판매글·미처리 신고 수. 숫자마다 그 목록을 볼 수 있는 화면으로 이어진다.
// "오늘"과 "최근 7일"은 서버가 한국 시간으로 센다. (오늘을 포함한 7일)
import { handleAuthError, startAdminPage } from "../admin-common.js";
import { getAdminDashboard } from "../api.js";
import { el } from "../ui.js";

const main = document.getElementById("admin-main");
const dateText = document.getElementById("dashboard-date");
const listError = document.getElementById("list-error");
const dashboard = document.getElementById("dashboard");

init();

async function init() {
  if ((await startAdminPage(main)) === null) return;
  let data;
  try {
    data = await getAdminDashboard();
  } catch (error) {
    if (handleAuthError(error)) return;
    dateText.textContent = "";
    listError.textContent = error.message;
    listError.hidden = false;
    return;
  }
  render(data);
}

function render(data) {
  const [year, month, day] = data.today.split("-").map(Number);
  dateText.textContent = `${year}년 ${month}월 ${day}일 기준 (한국 시간). 최근 7일은 오늘을 포함합니다.`;

  document.getElementById("stat-reports").replaceChildren(
    statTile("미처리 신고", data.pending_reports, {
      href: "/static/admin.html?status=PENDING",
      // 처리할 신고가 있을 때만 강조한다. 색만으로 알리지 않도록 "처리 필요" 문구를 함께 단다.
      alert: data.pending_reports > 0 ? "처리 필요" : null,
    }),
  );
  document.getElementById("stat-users").replaceChildren(
    statTile("가입자", data.users.total, { note: `관리자 ${data.users.admins}명 포함` }),
    statTile("오늘 가입", data.signups.today),
    statTile("최근 7일 가입", data.signups.last_7_days),
    statTile("정지 중", data.users.suspended),
    statTile("탈퇴한 계정", data.users.withdrawn),
  );
  document.getElementById("stat-posts").replaceChildren(
    statTile("전체 글", data.posts.total),
    statTile("판매 중", data.posts.on_sale),
    statTile("예약 중", data.posts.reserved),
    statTile("판매 완료", data.posts.sold),
    statTile("오늘 작성", data.new_posts.today),
    statTile("최근 7일 작성", data.new_posts.last_7_days),
  );
  dashboard.hidden = false;
}

/** 숫자 타일. href가 있으면 타일 전체가 링크다. */
function statTile(label, value, { href = null, note = null, alert = null } = {}) {
  const children = [
    el("span", { className: "stat-tile__label", text: label }),
    el("strong", { className: "stat-tile__value", text: value.toLocaleString("ko-KR") }),
    alert ? el("span", { className: "stat-tile__alert", text: alert }) : null,
    note ? el("span", { className: "stat-tile__note", text: note }) : null,
  ];
  const className = `card stat-tile${alert ? " stat-tile--alert" : ""}`;
  return href ? el("a", { className: `${className} stat-tile--link`, href }, ...children) : el("div", { className }, ...children);
}
