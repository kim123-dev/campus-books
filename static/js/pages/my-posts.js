// 내 글 화면: 내 정보와 내 판매글 목록(판매 완료 포함)을 보여준다. 로그인이 필요하다.
// 페이지 번호는 주소창(?page=2)에 저장한다. 새로고침과 뒤로 가기에도 같은 페이지가 나오게 하기 위해서다.
import { changePassword, listMyPosts, withdraw } from "../api.js";
import { logout, redirectToLogin, renderHeader } from "../auth.js";
import { clearToken, getToken, setToken } from "../token.js";
import { clearFormErrors, el, formatDate, renderPagination, renderPostCard, showFormErrors } from "../ui.js";

const PAGE_SIZE = 10; // 목록 화면과 같게 맞춘다. (서버 기본값은 20)

const profile = document.getElementById("profile");
const summary = document.getElementById("result-summary");
const listError = document.getElementById("list-error");
const emptyActions = document.getElementById("empty-actions");
const list = document.getElementById("post-list");
const pagination = document.getElementById("pagination");

// 응답이 늦게 도착한 이전 요청이 최신 결과를 덮어쓰지 않도록 요청마다 번호를 붙인다.
let latestRequestId = 0;

init();

async function init() {
  // 로그인하지 않았으면 로그인 화면으로 보낸다. 로그인 후 이 화면(보던 페이지 포함)으로 돌아온다.
  if (!getToken()) {
    redirectToLogin();
    return;
  }

  // 헤더가 부르는 /users/me 결과를 내 정보로 그대로 쓴다. 같은 요청을 두 번 보내지 않기 위해서다.
  const me = await renderHeader(document.getElementById("site-header"));
  if (me === null) {
    // renderHeader는 401이면 토큰을 지우고 null을, 서버 연결 실패면 토큰을 남긴 채 null을 돌려준다.
    if (!getToken()) {
      redirectToLogin();
    } else {
      showError("서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
    }
    return;
  }

  renderProfile(me);
  setUpAccount(me);
  // 뒤로 가기/앞으로 가기로 주소가 바뀌면 그 페이지를 다시 불러온다.
  window.addEventListener("popstate", load);
  load();
}

function renderProfile(me) {
  document.getElementById("profile-nickname").textContent = `${me.nickname}님`;
  // 가입일은 날짜만 보여준다. (formatDate는 "2026.11.06 14:20" 형식)
  document.getElementById("profile-meta").textContent = `${me.email} · ${formatDate(me.created_at).slice(0, 10)} 가입`;
  // 모바일에서는 헤더 메뉴 대신 하단 탭 바를 쓰므로, 헤더에 있던 "관리"·"로그아웃"을 이 화면(내 정보)에 둔다.
  // PC에서는 헤더에 그대로 있으므로 CSS(mobile-only)가 숨긴다.
  const actions = profile.querySelector(".profile-card__actions");
  if (me.role === "ADMIN") {
    actions.append(el("a", { className: "button mobile-only", href: "/static/admin.html", text: "관리" }));
  }
  const logoutButton = el("button", { type: "button", className: "button mobile-only", text: "로그아웃" });
  logoutButton.addEventListener("click", logout);
  actions.append(logoutButton);
  profile.hidden = false;
  document.getElementById("account").hidden = false;
}

// ---------- 계정 관리: 비밀번호 변경·회원 탈퇴 ----------

function setUpAccount(me) {
  const account = document.getElementById("account");
  const notice = document.getElementById("account-notice");
  const passwordForm = document.getElementById("password-form");
  const withdrawForm = document.getElementById("withdraw-form");
  const passwordToggle = document.getElementById("password-toggle");
  const withdrawToggle = document.getElementById("withdraw-toggle");

  // 버튼 하나를 누르면 그 폼만 펼친다. 두 폼이 함께 열려 있으면 어떤 비밀번호 칸인지 헷갈린다.
  function toggle(form, button) {
    const open = form.hidden;
    for (const [f, b] of [[passwordForm, passwordToggle], [withdrawForm, withdrawToggle]]) {
      f.hidden = !(open && f === form);
      b.setAttribute("aria-expanded", String(!f.hidden));
    }
    notice.hidden = true;
    if (open) form.querySelector("input").focus();
  }
  passwordToggle.addEventListener("click", () => toggle(passwordForm, passwordToggle));
  // 관리자는 탈퇴할 수 없으므로(서버도 400) 버튼을 두지 않는다.
  if (me.role === "ADMIN") withdrawToggle.hidden = true;
  else withdrawToggle.addEventListener("click", () => toggle(withdrawForm, withdrawToggle));

  passwordForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = passwordForm.querySelector(".form-error");
    clearFormErrors(passwordForm, errorBox);
    const { current_password: current, new_password: next, new_password_confirm: confirm } = passwordForm.elements;
    if (next.value !== confirm.value) {
      showFormErrors(passwordForm, errorBox, { fieldErrors: { new_password_confirm: "새 비밀번호가 일치하지 않습니다." } });
      return;
    }
    const submit = passwordForm.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      const { access_token: token } = await changePassword(current.value, next.value);
      // 서버가 변경 전 토큰을 모두 무효로 만들었으므로, 받은 새 토큰으로 바로 바꿔 이 기기의 로그인을 유지한다.
      setToken(token);
      passwordForm.reset();
      passwordForm.hidden = true;
      passwordToggle.setAttribute("aria-expanded", "false");
      notice.textContent = "비밀번호를 변경했습니다. 다른 기기에서는 다시 로그인해야 합니다.";
      notice.hidden = false;
    } catch (error) {
      if (error.status === 401) {
        redirectToLogin();
        return;
      }
      showPasswordError(passwordForm, errorBox, error, "current_password");
    } finally {
      submit.disabled = false;
    }
  });

  withdrawForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = withdrawForm.querySelector(".form-error");
    clearFormErrors(withdrawForm, errorBox);
    const password = withdrawForm.elements.password;
    if (password.value === "") {
      showFormErrors(withdrawForm, errorBox, { fieldErrors: { password: "비밀번호를 입력해 주세요." } });
      return;
    }
    // 되돌릴 수 없는 작업이라 실수로 누르지 않게 두 번 묻는다.
    if (!window.confirm("정말 탈퇴할까요? 내 글과 사진, 찜, 차단 목록이 모두 삭제됩니다.")) return;
    if (!window.confirm("탈퇴하면 되돌릴 수 없습니다. 마지막으로 확인할게요. 탈퇴할까요?")) return;

    const submit = withdrawForm.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      await withdraw(password.value);
    } catch (error) {
      submit.disabled = false;
      if (error.status === 401) {
        redirectToLogin();
        return;
      }
      showPasswordError(withdrawForm, errorBox, error, "password");
      return;
    }
    clearToken();
    window.alert("탈퇴가 완료되었습니다. 그동안 이용해 주셔서 감사합니다.");
    window.location.replace("/static/index.html");
  });
}

// 비밀번호가 틀리면(400) 공통 영역 대신 비밀번호 칸 아래에 보여준다.
function showPasswordError(form, errorBox, error, field) {
  if (error.status === 400) {
    showFormErrors(form, errorBox, { fieldErrors: { [field]: error.message } });
  } else {
    showFormErrors(form, errorBox, error);
  }
}

// ---------- 불러오기와 그리기 ----------

function readPage() {
  // page는 서버가 검증한다. (0이나 문자이면 422 메시지를 보여준다)
  return new URLSearchParams(window.location.search).get("page") ?? "1";
}

async function load() {
  const requestId = ++latestRequestId;
  summary.textContent = "불러오는 중…";
  listError.hidden = true;
  emptyActions.hidden = true;
  list.replaceChildren();
  pagination.replaceChildren();

  let data;
  try {
    data = await listMyPosts({ page: readPage(), size: PAGE_SIZE });
  } catch (error) {
    if (requestId !== latestRequestId) return;
    if (error.status === 401) {
      // 토큰이 만료되었다. (api.js가 토큰을 이미 지웠다)
      redirectToLogin();
      return;
    }
    // 422(잘못된 page)는 필드 메시지를, 그 밖에는 서버 메시지를 보여준다.
    showError(error.fieldErrors?.page ?? error.message);
    return;
  }
  if (requestId !== latestRequestId) return;
  render(data);
}

function render({ items, total, page, size }) {
  const totalPages = Math.max(1, Math.ceil(total / size));

  if (total === 0) {
    summary.textContent = "아직 작성한 글이 없습니다.";
    emptyActions.hidden = false;
    return;
  }

  summary.textContent =
    items.length === 0
      ? `이 페이지에는 글이 없습니다. (전체 ${total}개, ${totalPages}페이지까지)`
      : `총 ${total}개`;
  // 모두 내 글이라 찜 하트를 두지 않는다. (서버도 내 글 찜을 400으로 막는다)
  list.replaceChildren(...items.map((post) => renderPostCard(post)));
  renderPagination(pagination, page, totalPages, goToPage);
}

function goToPage(page) {
  history.pushState(null, "", page > 1 ? `?page=${page}` : window.location.pathname);
  load();
  window.scrollTo({ top: 0 });
}

function showError(message) {
  summary.textContent = "";
  listError.textContent = message;
  listError.hidden = false;
}
