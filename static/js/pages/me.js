// 내 정보 화면: 내 정보(닉네임·이메일·가입일·매너 학점), 계정 관리(닉네임·비밀번호 변경, 본인 확인 질문, 탈퇴), 내 글·찜 목록 탭.
// 예전의 "내 글"(my-posts.html)과 "찜"(wishlist.html) 화면을 이 화면 하나로 모았다. 로그인이 필요하다.
// 고른 탭과 페이지는 주소창(?tab=wishlist&page=2)에 저장한다. 새로고침과 뒤로 가기에도 같은 목록이 나오게 하기 위해서다.
import { changePassword, getProfile, listMyPosts, listWishlist, setSecurityQuestion, updateMe, withdraw } from "../api.js";
import { logout, redirectToLogin, renderHeader } from "../auth.js";
import { t } from "../i18n.js";
import { languageOptions } from "../lang-picker.js";
import { renderSecurityQuestionFields } from "../security-question.js";
import { clearToken, getToken, setToken } from "../token.js";
import {
  clearFormErrors,
  el,
  EMPTY_POSTS_IMAGE,
  EMPTY_WISHLIST_IMAGE,
  formatDateOnly,
  formatMonthDayTime,
  parseServerDate,
  renderEmptyState,
  renderPagination,
  renderPostCard,
  setErrorText,
  showFormErrors,
  withContextMessage,
} from "../ui.js";
import { createWishlistButton } from "../wishlist-button.js";

const PAGE_SIZE = 10; // 목록 화면과 같게 맞춘다. (서버 기본값은 20)

// 탭마다 다른 것: 불러올 API, 빈 화면 문구·그림·버튼, 카드 옆 버튼
const TAB_CONFIG = {
  posts: {
    load: listMyPosts,
    emptyText: t("me.empty_posts"),
    emptyImage: EMPTY_POSTS_IMAGE,
    emptyAction: { href: "/static/post-form.html", text: t("me.first_post") },
    // 모두 내 글이라 찜 하트를 두지 않는다. (서버도 내 글 찜을 400으로 막는다)
    action: () => null,
  },
  wishlist: {
    load: listWishlist,
    emptyText: t("me.empty_wishlist"),
    emptyImage: EMPTY_WISHLIST_IMAGE,
    emptyAction: { href: "/static/index.html", text: t("common.browse_books") },
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
      showError(t("err.network"));
    }
    return;
  }

  renderProfile(me);
  loadManner(me.id);
  setUpAccount(me);
  setUpLanguage();
  setUpTabs();
  // 뒤로 가기/앞으로 가기로 주소가 바뀌면 그 탭·페이지를 다시 불러온다.
  window.addEventListener("popstate", load);
  load();
}

// ---------- 내 정보 ----------

function renderProfile(me) {
  document.getElementById("profile-nickname").textContent = t("me.nickname", { nickname: me.nickname });
  // 가입일은 날짜만 보여준다.
  document.getElementById("profile-meta").textContent = t("me.meta", { email: me.email, date: formatDateOnly(me.created_at) });
  document.getElementById("profile-public-link").href = `/static/user.html?id=${encodeURIComponent(me.id)}`;
  // 모바일에서는 헤더 메뉴 대신 하단 탭 바를 쓰므로, 헤더에 있던 "관리"·"로그아웃"을 이 화면에 둔다.
  // PC에서는 헤더에 그대로 있으므로 CSS(mobile-only)가 숨긴다.
  const actions = profile.querySelector(".profile-card__actions");
  if (me.role === "ADMIN") {
    actions.append(el("a", { className: "button mobile-only", href: "/static/admin-dashboard.html", text: t("term.admin") }));
  }
  const logoutButton = el("button", { type: "button", className: "button mobile-only", text: t("term.logout") });
  logoutButton.addEventListener("click", logout);
  actions.append(logoutButton);
  profile.hidden = false;
  document.getElementById("account").hidden = false;
}

/** 매너 학점 요약 한 줄. 다른 사람이 보는 공개 프로필과 같은 값이다. 보조 정보라 실패하면 줄을 숨긴다. */
async function loadManner(userId) {
  const line = document.getElementById("profile-manner");
  try {
    const { manner } = await getProfile(userId);
    line.textContent = mannerText(manner);
  } catch {
    line.hidden = true;
  }
}

function mannerText({ good, bad, total, gpa, grade }) {
  const manner = t("me.manner", { score: `${gpa.toFixed(1)} / 4.5 (${grade})` });
  // 후기가 없으면 기본 학점(3.5, B+)이다.
  return total === 0 ? t("me.manner_none", { manner }) : t("me.manner_counts", { manner, good, bad });
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
      showFormErrors(nicknameForm, errorBox, { fieldErrors: { nickname: t("me.nickname_too_short") } });
      return;
    }
    const submit = nicknameForm.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      const updated = await updateMe({ nickname });
      // 헤더(PC의 "○○님")는 다음 화면부터 새 이름이 나온다. 이 화면의 카드는 바로 바꾼다.
      document.getElementById("profile-nickname").textContent = t("me.nickname", { nickname: updated.nickname });
      updateNicknameHint(updated);
      close(nicknameForm, t("me.nickname_changed", { nickname: updated.nickname }));
    } catch (error) {
      if (error.status === 401) {
        redirectToLogin();
        return;
      }
      // 중복(409)·30일 제한(400)·형식(422)은 모두 닉네임 칸 아래에 보여준다. (다른 언어는 원문을 아래에 붙인다)
      // 400은 30일 제한과 "지금 닉네임과 같음" 두 가지라 상태 코드별 문장을, 409는 중복뿐이라 맞춤 문장을 쓴다.
      if (error.fieldErrors?.nickname) {
        showFormErrors(nicknameForm, errorBox, error);
      } else if (error.status === 400 || error.status === 409) {
        const { message, original } = error.status === 409 ? withContextMessage(error, "me.nickname_taken") : error;
        showFormErrors(nicknameForm, errorBox, { fieldErrors: { nickname: message }, fieldOriginals: { nickname: original } });
      } else {
        showFormErrors(nicknameForm, errorBox, error);
      }
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
      showFormErrors(passwordForm, errorBox, { fieldErrors: { new_password_confirm: t("reset.password_mismatch") } });
      return;
    }
    const submit = passwordForm.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      const { access_token: token } = await changePassword(current.value, next.value);
      // 서버가 변경 전 토큰을 모두 무효로 만들었으므로, 받은 새 토큰으로 바로 바꿔 이 기기의 로그인을 유지한다.
      setToken(token);
      close(passwordForm, t("me.password_changed"));
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
      showFormErrors(withdrawForm, errorBox, { fieldErrors: { password: t("me.password_required") } });
      return;
    }
    // 되돌릴 수 없는 작업이라 실수로 누르지 않게 두 번 묻는다.
    if (!window.confirm(t("me.confirm_withdraw"))) return;
    if (!window.confirm(t("me.confirm_withdraw_final"))) return;

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
    window.alert(t("me.withdrawn"));
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
  // 저장할 때마다 서버가 준 최신 내 정보로 바꾼다. 400이 어떤 사유인지 판단할 때 쓴다.
  let current = me;
  updateQuestionStatus(me);
  toggle.addEventListener("click", open);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = form.querySelector(".form-error");
    clearFormErrors(form, errorBox);
    const password = form.elements.password;
    if (password.value === "") {
      showFormErrors(form, errorBox, { fieldErrors: { password: t("me.password_required") } });
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
      current = updated;
      updateQuestionStatus(updated);
      close(form, t("me.question_saved"));
    } catch (error) {
      if (error.status === 401) {
        redirectToLogin();
        return;
      }
      // 비밀번호 틀림(400)만 비밀번호 칸 아래에 보여준다. 7일 제한(400)은 비밀번호와 관계없어 공통 영역에 보여준다.
      // 서버 문구 내용으로 구분하면 화면 언어를 바꿨을 때(문구가 번역됨) 동작이 달라지므로,
      // 이미 알고 있는 7일 제한 여부로 구분한다. 제한 중이 아닌데 400이면 비밀번호가 틀린 것이다.
      if (error.status === 400 && !questionChangeLocked(current)) {
        showFormErrors(form, errorBox, { fieldErrors: { password: t("err.wrong_password") } });
      } else {
        showFormErrors(form, errorBox, error);
      }
    } finally {
      submit.disabled = false;
    }
  });
}

// 질문으로 비밀번호를 재설정한 뒤 7일 동안은 질문을 바꿀 수 없다. 서버가 그 끝 시각을 내 정보에 담아 준다.
function questionChangeLocked(me) {
  const until = parseServerDate(me.security_question_changeable_at);
  return until !== null && until > new Date();
}

// 지금 등록된 질문과, 없으면 등록하라는 안내. 답은 서버도 보여주지 않는다.
function updateQuestionStatus(me) {
  const status = document.getElementById("question-status");
  if (!me.security_question) {
    status.textContent = t("me.question_missing");
    status.classList.add("account-card__notice--warning");
    return;
  }
  status.classList.remove("account-card__notice--warning");
  // 질문 문장은 서버가 저장한 한국어 원문 그대로다. (고른 질문도 문장으로 저장된다)
  const lock = me.security_question_changeable_at
    ? ` ${t("me.question_locked", { date: formatMonthDayTime(me.security_question_changeable_at) })}`
    : "";
  status.textContent = `${t("me.question_current", { question: me.security_question })}${lock}`;
}

// 30일 안에 이미 바꿨으면 언제부터 다시 바꿀 수 있는지 미리 알려준다. (눌러 보고 400을 받기 전에)
function updateNicknameHint(me) {
  document.getElementById("nickname-hint").textContent = me.nickname_changeable_at
    ? t("me.nickname_hint_until", { date: formatMonthDayTime(me.nickname_changeable_at) })
    : t("me.nickname_hint");
}

// 비밀번호가 틀리면(400) 공통 영역 대신 비밀번호 칸 아래에 보여준다.
// 비밀번호 변경·탈퇴의 400은 비밀번호 틀림뿐이라(관리자 탈퇴는 버튼이 없다) 그 문장으로 바꾼다. (한국어는 서버 문장과 같다)
function showPasswordError(form, errorBox, error, field) {
  if (error.status === 400) {
    showFormErrors(form, errorBox, { fieldErrors: { [field]: t("err.wrong_password") } });
  } else {
    showFormErrors(form, errorBox, error);
  }
}

// ---------- 언어 ----------

// 화면 언어 고르기. 기능 플래그가 꺼져 있으면 languageOptions()가 null이라 칸을 숨긴 채로 둔다.
function setUpLanguage() {
  const options = languageOptions();
  if (options === null) return;
  const section = document.getElementById("language");
  section.append(options);
  section.hidden = false;
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
  summary.textContent = t("common.loading");
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
    // 422(잘못된 page)는 필드 메시지를, 그 밖에는 서버 메시지를 보여준다. (다른 언어는 원문을 아래에 붙인다)
    showError(error.fieldErrors?.page ?? error.message, error.fieldErrors?.page ? error.fieldOriginals?.page : error.original);
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
      ? t("home.page_empty", { total, pages: totalPages })
      : t("home.total", { count: total });
  list.replaceChildren(...items.map((post) => renderPostCard(post, { action: config.action(post) })));
  renderPagination(pagination, page, totalPages, (next) => goToPage(tab, next));
}

function goToPage(tab, page) {
  history.pushState(null, "", `?tab=${tab}${page > 1 ? `&page=${page}` : ""}`);
  load();
  // 페이지를 넘기면 목록 맨 위(탭)로 간다. 화면 맨 위로 가면 내 정보 카드를 지나 다시 내려와야 한다.
  tabs.scrollIntoView({ block: "start" });
}

function showError(message, original = null) {
  summary.textContent = "";
  setErrorText(listError, message, original);
  listError.hidden = false;
}
