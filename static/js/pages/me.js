// 내 정보 화면: 내 정보(닉네임·이메일·가입일·매너 점수), 계정 관리(닉네임·비밀번호 변경, 본인 확인 질문, 탈퇴), 내 글·찜 목록 탭.
// 예전의 "내 글"(my-posts.html)과 "찜"(wishlist.html) 화면을 이 화면 하나로 모았다. 로그인이 필요하다.
// 고른 탭과 페이지는 주소창(?tab=wishlist&page=2)에 저장한다. 새로고침과 뒤로 가기에도 같은 목록이 나오게 하기 위해서다.
import { changePassword, getProfile, listMyPosts, listWishlist, setSecurityQuestion, updateMe, withdraw } from "../api.js";
import { logout, redirectToLogin, renderHeader } from "../auth.js";
import { renderSecurityQuestionFields } from "../security-question.js";
import { clearToken, getToken, setToken } from "../token.js";
import {
  clearFormErrors,
  el,
  EMPTY_POSTS_IMAGE,
  EMPTY_WISHLIST_IMAGE,
  formatDate,
  formatMonthDayTime,
  renderEmptyState,
  renderPagination,
  renderPostCard,
  showFormErrors,
} from "../ui.js";
import { createWishlistButton } from "../wishlist-button.js";

const PAGE_SIZE = 10; // 목록 화면과 같게 맞춘다. (서버 기본값은 20)

// 탭마다 다른 것: 불러올 API, 빈 화면 문구·그림·버튼, 카드 옆 버튼
const TAB_CONFIG = {
  posts: {
    load: listMyPosts,
    emptyText: "아직 작성한 글이 없습니다.",
    emptyImage: EMPTY_POSTS_IMAGE,
    emptyAction: { href: "/static/post-form.html", text: "첫 글 쓰기" },
    // 모두 내 글이라 찜 하트를 두지 않는다. (서버도 내 글 찜을 400으로 막는다)
    action: () => null,
  },
  wishlist: {
    load: listWishlist,
    emptyText: "아직 찜한 글이 없습니다. 마음에 드는 교재에서 하트를 눌러 보세요.",
    emptyImage: EMPTY_WISHLIST_IMAGE,
    emptyAction: { href: "/static/index.html", text: "교재 둘러보기" },
    // 해제한 카드를 바로 지우지 않는다. 실수로 눌렀을 때 다시 찜할 수 있고, 목록이 갑자기 밀리지 않는다.
    action: (post) => createWishlistButton(post, { className: "wish-button--card" }),
  },
};
const DEFAULT_TAB = "posts";

const profile = document.getElementById("profile");
const tabs = document.getElementById("me-tabs");
const summary = document.getElementById("result-summary");
const listError = document.getElementById("list-error");
const emptyActions = document.getElementById("empty-actions");
const list = document.getElementById("post-list");
const pagination = document.getElementById("pagination");

// 응답이 늦게 도착한 이전 요청이 최신 결과를 덮어쓰지 않도록 요청마다 번호를 붙인다.
let latestRequestId = 0;

init();

async function init() {
  // 로그인하지 않았으면 로그인 화면으로 보낸다. 로그인 후 이 화면(보던 탭·페이지 포함)으로 돌아온다.
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
  loadManner(me.id);
  setUpAccount(me);
  setUpTabs();
  // 뒤로 가기/앞으로 가기로 주소가 바뀌면 그 탭·페이지를 다시 불러온다.
  window.addEventListener("popstate", load);
  load();
}

// ---------- 내 정보 ----------

function renderProfile(me) {
  document.getElementById("profile-nickname").textContent = `${me.nickname}님`;
  // 가입일은 날짜만 보여준다. (formatDate는 "2026.11.06 14:20" 형식)
  document.getElementById("profile-meta").textContent = `${me.email} · ${formatDate(me.created_at).slice(0, 10)} 가입`;
  document.getElementById("profile-public-link").href = `/static/user.html?id=${encodeURIComponent(me.id)}`;
  // 모바일에서는 헤더 메뉴 대신 하단 탭 바를 쓰므로, 헤더에 있던 "관리"·"로그아웃"을 이 화면에 둔다.
  // PC에서는 헤더에 그대로 있으므로 CSS(mobile-only)가 숨긴다.
  const actions = profile.querySelector(".profile-card__actions");
  if (me.role === "ADMIN") {
    actions.append(el("a", { className: "button mobile-only", href: "/static/admin-dashboard.html", text: "관리" }));
  }
  const logoutButton = el("button", { type: "button", className: "button mobile-only", text: "로그아웃" });
  logoutButton.addEventListener("click", logout);
  actions.append(logoutButton);
  profile.hidden = false;
  document.getElementById("account").hidden = false;
}

/** 매너 점수 요약 한 줄. 다른 사람이 보는 공개 프로필과 같은 값이다. 보조 정보라 실패하면 줄을 숨긴다. */
async function loadManner(userId) {
  const line = document.getElementById("profile-manner");
  try {
    const { manner } = await getProfile(userId);
    line.textContent = mannerText(manner);
  } catch {
    line.hidden = true;
  }
}

function mannerText({ good, bad, total, good_ratio: ratio }) {
  if (total === 0) return "매너 점수: 아직 받은 거래 후기가 없어요.";
  // 후기가 3개 미만이면 서버가 비율을 비워 보낸다(null). 개수만 보여준다.
  const counts = `좋아요 ${good} · 아쉬워요 ${bad}`;
  return ratio === null ? `매너 점수: ${counts}` : `매너 점수: ${ratio}% 좋아요 (${counts})`;
}

// ---------- 계정 관리: 닉네임 변경·비밀번호 변경·본인 확인 질문·회원 탈퇴 ----------

function setUpAccount(me) {
  const notice = document.getElementById("account-notice");
  const nicknameForm = document.getElementById("nickname-form");
  const passwordForm = document.getElementById("password-form");
  const withdrawForm = document.getElementById("withdraw-form");
  const questionForm = document.getElementById("question-form");
  const questionToggle = document.getElementById("question-toggle");
  const nicknameToggle = document.getElementById("nickname-toggle");
  const passwordToggle = document.getElementById("password-toggle");
  const withdrawToggle = document.getElementById("withdraw-toggle");
  const pairs = [
    [nicknameForm, nicknameToggle],
    [passwordForm, passwordToggle],
    [questionForm, questionToggle],
    [withdrawForm, withdrawToggle],
  ];

  // 버튼 하나를 누르면 그 폼만 펼친다. 폼이 함께 열려 있으면 어떤 칸인지 헷갈린다.
  function toggle(form) {
    const open = form.hidden;
    for (const [f, b] of pairs) {
      f.hidden = !(open && f === form);
      b.setAttribute("aria-expanded", String(!f.hidden));
    }
    notice.hidden = true;
    if (open) form.querySelector("input").focus();
  }
  function close(form, message) {
    form.reset();
    toggle(form);
    notice.textContent = message;
    notice.hidden = false;
  }
  nicknameToggle.addEventListener("click", () => toggle(nicknameForm));
  passwordToggle.addEventListener("click", () => toggle(passwordForm));
  // 관리자는 탈퇴할 수 없으므로(서버도 400) 버튼을 두지 않는다.
  if (me.role === "ADMIN") withdrawToggle.hidden = true;
  else withdrawToggle.addEventListener("click", () => toggle(withdrawForm));

  updateNicknameHint(me);
  setUpSecurityQuestion(me, { form: questionForm, toggle: questionToggle, open: () => toggle(questionForm), close });

  nicknameForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = nicknameForm.querySelector(".form-error");
    clearFormErrors(nicknameForm, errorBox);
    const nickname = nicknameForm.elements.nickname.value.trim();
    if (nickname.length < 2) {
      showFormErrors(nicknameForm, errorBox, { fieldErrors: { nickname: "닉네임은 2자 이상이어야 합니다." } });
      return;
    }
    const submit = nicknameForm.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      const updated = await updateMe({ nickname });
      // 헤더(PC의 "○○님")는 다음 화면부터 새 이름이 나온다. 이 화면의 카드는 바로 바꾼다.
      document.getElementById("profile-nickname").textContent = `${updated.nickname}님`;
      updateNicknameHint(updated);
      close(nicknameForm, `닉네임을 "${updated.nickname}"(으)로 바꿨습니다.`);
    } catch (error) {
      if (error.status === 401) {
        redirectToLogin();
        return;
      }
      // 중복(409)·30일 제한(400)·형식(422)은 모두 닉네임 칸 아래에 보여준다.
      const message = error.fieldErrors?.nickname ?? (error.status === 400 || error.status === 409 ? error.message : null);
      if (message) showFormErrors(nicknameForm, errorBox, { fieldErrors: { nickname: message } });
      else showFormErrors(nicknameForm, errorBox, error);
    } finally {
      submit.disabled = false;
    }
  });

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
      close(passwordForm, "비밀번호를 변경했습니다. 다른 기기에서는 다시 로그인해야 합니다.");
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

// 본인 확인 질문 등록·변경. 관리자는 질문을 쓸 수 없으므로(서버도 400) 버튼과 안내를 두지 않는다.
function setUpSecurityQuestion(me, { form, toggle, open, close }) {
  const status = document.getElementById("question-status");
  if (me.role === "ADMIN") {
    toggle.hidden = true;
    status.hidden = true;
    return;
  }
  const fields = renderSecurityQuestionFields(document.getElementById("question-fields"), { idPrefix: "me" });
  updateQuestionStatus(me);
  toggle.addEventListener("click", open);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = form.querySelector(".form-error");
    clearFormErrors(form, errorBox);
    const password = form.elements.password;
    if (password.value === "") {
      showFormErrors(form, errorBox, { fieldErrors: { password: "비밀번호를 입력해 주세요." } });
      return;
    }
    const questionErrors = fields.check();
    if (questionErrors !== null) {
      showFormErrors(form, errorBox, { fieldErrors: questionErrors });
      return;
    }
    const submit = form.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      const updated = await setSecurityQuestion(password.value, fields.value());
      fields.reset();
      updateQuestionStatus(updated);
      close(form, "본인 확인 질문을 저장했어요.");
    } catch (error) {
      if (error.status === 401) {
        redirectToLogin();
        return;
      }
      // 비밀번호 틀림(400)만 비밀번호 칸 아래에 보여준다. 7일 제한(400)은 비밀번호와 관계없어 공통 영역에 보여준다.
      if (error.status === 400 && error.message.startsWith("현재 비밀번호")) {
        showFormErrors(form, errorBox, { fieldErrors: { password: error.message } });
      } else {
        showFormErrors(form, errorBox, error);
      }
    } finally {
      submit.disabled = false;
    }
  });
}

// 지금 등록된 질문과, 없으면 등록하라는 안내. 답은 서버도 보여주지 않는다.
function updateQuestionStatus(me) {
  const status = document.getElementById("question-status");
  if (!me.security_question) {
    status.textContent = '아직 본인 확인 질문이 없어요. "본인 확인 질문"을 눌러 등록해 두세요. 질문이 없으면 비밀번호를 잊었을 때 재설정할 수 없어요.';
    status.classList.add("account-card__notice--warning");
    return;
  }
  status.classList.remove("account-card__notice--warning");
  const lock = me.security_question_changeable_at
    ? ` 질문으로 비밀번호가 재설정돼서 ${formatMonthDayTime(me.security_question_changeable_at)}부터 바꿀 수 있어요.`
    : "";
  status.textContent = `본인 확인 질문: ${me.security_question}${lock}`;
}

// 30일 안에 이미 바꿨으면 언제부터 다시 바꿀 수 있는지 미리 알려준다. (눌러 보고 400을 받기 전에)
function updateNicknameHint(me) {
  document.getElementById("nickname-hint").textContent = me.nickname_changeable_at
    ? `2~30자 · ${formatMonthDayTime(me.nickname_changeable_at)}부터 다시 바꿀 수 있어요.`
    : "2~30자 · 30일에 한 번 바꿀 수 있어요.";
}

// 비밀번호가 틀리면(400) 공통 영역 대신 비밀번호 칸 아래에 보여준다.
function showPasswordError(form, errorBox, error, field) {
  if (error.status === 400) {
    showFormErrors(form, errorBox, { fieldErrors: { [field]: error.message } });
  } else {
    showFormErrors(form, errorBox, error);
  }
}

// ---------- 탭: 내 글 | 찜 목록 ----------

function readState() {
  const params = new URLSearchParams(window.location.search);
  const tab = params.get("tab");
  // page는 서버가 검증한다. (0이나 문자이면 422 메시지를 보여준다)
  return { tab: Object.hasOwn(TAB_CONFIG, tab ?? "") ? tab : DEFAULT_TAB, page: params.get("page") ?? "1" };
}

function setUpTabs() {
  for (const link of tabs.querySelectorAll(".tabs__item")) {
    // 링크라서 새 탭으로 열기도 되지만, 그냥 누르면 화면을 다시 불러오지 않고 목록만 바꾼다.
    link.addEventListener("click", (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
      event.preventDefault();
      if (link.dataset.tab === readState().tab) return;
      history.pushState(null, "", `?tab=${link.dataset.tab}`);
      load();
    });
  }
  tabs.hidden = false;
}

function markCurrentTab(tab) {
  for (const link of tabs.querySelectorAll(".tabs__item")) {
    if (link.dataset.tab === tab) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

// ---------- 불러오기와 그리기 ----------

async function load() {
  const requestId = ++latestRequestId;
  const { tab, page } = readState();
  markCurrentTab(tab);
  summary.textContent = "불러오는 중…";
  listError.hidden = true;
  emptyActions.hidden = true;
  list.replaceChildren();
  pagination.replaceChildren();

  let data;
  try {
    data = await TAB_CONFIG[tab].load({ page, size: PAGE_SIZE });
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
  render(tab, data);
}

function render(tab, { items, total, page, size }) {
  const config = TAB_CONFIG[tab];
  const totalPages = Math.max(1, Math.ceil(total / size));

  if (total === 0) {
    renderEmptyState(summary, config.emptyText, { image: config.emptyImage });
    emptyActions.replaceChildren(el("a", { className: "button button--primary", href: config.emptyAction.href, text: config.emptyAction.text }));
    emptyActions.hidden = false;
    return;
  }

  summary.textContent =
    items.length === 0
      ? `이 페이지에는 글이 없습니다. (전체 ${total}개, ${totalPages}페이지까지)`
      : `총 ${total}개`;
  list.replaceChildren(...items.map((post) => renderPostCard(post, { action: config.action(post) })));
  renderPagination(pagination, page, totalPages, (next) => goToPage(tab, next));
}

function goToPage(tab, page) {
  history.pushState(null, "", `?tab=${tab}${page > 1 ? `&page=${page}` : ""}`);
  load();
  // 페이지를 넘기면 목록 맨 위(탭)로 간다. 화면 맨 위로 가면 내 정보 카드를 지나 다시 내려와야 한다.
  tabs.scrollIntoView({ block: "start" });
}

function showError(message) {
  summary.textContent = "";
  listError.textContent = message;
  listError.hidden = false;
}
