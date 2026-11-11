// 재가입 차단 화면 (관리자 전용): 차단 목록(차단 시각·사유)과 이메일로 차단 풀기.
// 이메일은 해시로만 저장되므로 목록에서 어떤 이메일인지 알 수 없다. 풀 때는 관리자가 이메일을 입력한다.
import { handleAuthError, reasonForm, startAdminPage } from "../admin-common.js";
import { listEmailBans, unbanEmail } from "../api.js";
import { el, formatDate, renderPagination } from "../ui.js";

const PAGE_SIZE = 20;

const main = document.getElementById("admin-main");
const notice = document.getElementById("admin-notice");
const summary = document.getElementById("result-summary");
const listError = document.getElementById("list-error");
const list = document.getElementById("ban-list");
const pagination = document.getElementById("pagination");

let latestRequestId = 0;

init();

async function init() {
  if ((await startAdminPage(main)) === null) return;
  document.getElementById("unban-box").replaceChildren(unbanForm());
  window.addEventListener("popstate", load);
  load();
}

function unbanForm() {
  const email = el("input", { id: "unban-email", type: "email", autocomplete: "off", maxLength: 255 });
  return reasonForm({
    id: "unban-form",
    submitText: "차단 해제",
    fields: [el("div", { className: "field" }, el("label", { htmlFor: "unban-email", text: "이메일" }), email)],
    validate: () => (email.value.trim() === "" ? "이메일을 입력해 주세요." : null),
    confirm: (reason) => `${email.value.trim()}의 재가입 차단을 풀까요?\n풀면 이 이메일로 다시 가입할 수 있어요.\n\n사유: ${reason}`,
    onSubmit: async (reason) => {
      await unbanEmail({ email: email.value.trim(), reason });
      // 입력한 이메일은 화면에 남기지 않는다.
      document.getElementById("unban-box").replaceChildren(unbanForm());
      notice.textContent = "재가입 차단을 해제했습니다.";
      notice.hidden = false;
      load();
    },
  });
}

function currentPage() {
  return new URLSearchParams(window.location.search).get("page") ?? "1";
}

async function load() {
  const requestId = ++latestRequestId;
  summary.textContent = "불러오는 중…";
  listError.hidden = true;
  list.replaceChildren();
  pagination.replaceChildren();
  let data;
  try {
    data = await listEmailBans({ page: currentPage(), size: PAGE_SIZE });
  } catch (error) {
    if (requestId !== latestRequestId) return;
    if (handleAuthError(error)) return;
    summary.textContent = "";
    listError.textContent = error.fieldErrors?.page ?? error.message;
    listError.hidden = false;
    return;
  }
  if (requestId !== latestRequestId) return;
  const { items, total, page, size } = data;
  if (total === 0) {
    summary.textContent = "재가입을 막은 이메일이 없습니다.";
    return;
  }
  summary.textContent = items.length === 0 ? `이 페이지에는 차단이 없습니다. (전체 ${total}건)` : `총 ${total}건`;
  list.replaceChildren(
    ...items.map((ban) =>
      el(
        "li",
        { className: "card admin-card" },
        el("p", { className: "admin-card__meta", text: `차단 #${ban.id} · ${formatDate(ban.created_at)}` }),
        el("p", { className: "admin-card__reason", text: ban.reason ? `사유: ${ban.reason}` : "사유 없음" }),
      ),
    ),
  );
  renderPagination(pagination, page, Math.max(1, Math.ceil(total / size)), (next) => {
    const params = new URLSearchParams(window.location.search);
    if (next > 1) params.set("page", String(next));
    else params.delete("page");
    history.pushState(null, "", `?${params}`);
    load();
    window.scrollTo({ top: 0 });
  });
}
