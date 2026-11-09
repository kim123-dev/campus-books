// 작성·수정 공용 화면. 주소에 ?id=가 있으면 수정 모드, 없으면 작성 모드다.
// 입력 규칙 검사는 서버가 하고, 화면은 서버 메시지를 칸 아래(422)나 폼 아래(400·403·404)에 보여준다.
import { createPost, getPost, updatePost } from "../api.js";
import { redirectToLogin, renderHeader } from "../auth.js";
import { getToken } from "../token.js";
import { clearFormErrors, readPostIdFromUrl, showFormErrors } from "../ui.js";

const HOME_PAGE = "/static/index.html";
const TEXT_FIELDS = ["title", "book_title", "course_name", "description", "open_chat_url"];

const isEdit = new URLSearchParams(window.location.search).has("id");
const postId = isEdit ? readPostIdFromUrl() : null;
const submitLabel = isEdit ? "저장하기" : "등록하기";

const pageStatus = document.getElementById("page-status");
const pageError = document.getElementById("page-error");
const pageErrorText = document.getElementById("page-error-text");
const pageErrorLink = document.getElementById("page-error-link");
const formCard = document.getElementById("form-card");
const form = document.getElementById("post-form");
const formError = document.getElementById("form-error");
const submitButton = form.querySelector('button[type="submit"]');

form.addEventListener("submit", onSubmit);
init();

// ---------- 화면 준비 ----------

async function init() {
  // 로그인하지 않았으면 폼을 그리지 않고 로그인 화면으로 보낸다. 로그인 후 이 화면으로 돌아온다.
  if (!getToken()) {
    redirectToLogin();
    return;
  }

  const me = await renderHeader(document.getElementById("site-header"));
  if (me === null) {
    // renderHeader는 401이면 토큰을 지우고 null을, 서버 연결 실패면 토큰을 남긴 채 null을 돌려준다.
    if (!getToken()) {
      redirectToLogin();
    } else {
      showPageError("서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.", HOME_PAGE, "목록으로");
    }
    return;
  }

  if (!isEdit) {
    showForm();
    return;
  }
  if (postId === null) {
    showPageError("글 주소가 올바르지 않습니다.", HOME_PAGE, "목록으로");
    return;
  }

  let post;
  try {
    post = await getPost(postId);
  } catch (error) {
    // 404 "게시글을 찾을 수 없습니다." 같은 서버 메시지를 그대로 보여준다.
    showPageError(error.message, HOME_PAGE, "목록으로");
    return;
  }

  // 아래 두 검사는 수정할 수 없는 글에 폼을 보여주지 않기 위한 UX용이다.
  // 최종 권한·상태 검사는 저장(PATCH)할 때 서버가 한다. 화면을 연 뒤 다른 탭에서 판매 완료로 바꾸는 등
  // 상황이 바뀌면, 저장할 때 서버의 403·400 메시지가 폼 아래에 표시된다.
  const detailUrl = postDetailUrl(post.id);
  if (post.seller.id !== me.id) {
    showPageError("본인이 작성한 글만 수정할 수 있습니다.", detailUrl, "상세 화면으로");
    return;
  }
  if (post.status === "SOLD") {
    showPageError("판매 완료된 글은 수정할 수 없습니다.", detailUrl, "상세 화면으로");
    return;
  }

  fillForm(post);
  showForm();
}

function showForm() {
  const title = isEdit ? "판매글 수정" : "판매글 작성";
  document.title = `${title} | Campus Books`;
  document.getElementById("form-title").textContent = title;
  submitButton.textContent = submitLabel;
  // 취소하면 작성은 목록으로, 수정은 보던 글로 돌아간다.
  document.getElementById("cancel-link").href = isEdit ? postDetailUrl(postId) : HOME_PAGE;

  pageStatus.hidden = true;
  formCard.hidden = false;
  form.elements.title.focus();
}

function showPageError(message, linkHref, linkText) {
  pageStatus.hidden = true;
  formCard.hidden = true;
  pageErrorText.textContent = message;
  pageErrorLink.href = linkHref;
  pageErrorLink.textContent = linkText;
  pageError.hidden = false;
}

// 입력칸의 value는 HTML로 해석되지 않으므로 사용자 값을 그대로 넣어도 안전하다.
function fillForm(post) {
  for (const field of TEXT_FIELDS) form.elements.namedItem(field).value = post[field] ?? "";
  form.elements.condition.value = post.condition;
  form.elements.price.value = String(post.price);
}

// ---------- 저장 ----------

/**
 * 폼 값을 API 요청 본문으로 바꾼다.
 * - 과목명·설명·오픈채팅 링크를 비우면 빈 문자열을 보내고, 서버가 "없음(null)"으로 바꾼다. (수정에서 지울 수 있게)
 * - 가격은 숫자로 보낸다. 서버가 "1000" 같은 문자열을 거절하기 때문이다.
 * - 책 상태·가격을 비우면 작성에서는 빼고 보내 서버가 "필수 항목입니다."를 주게 하고,
 *   수정에서는 null을 보내 서버가 거절하게 한다. 수정에서 빼면 "변경 안 함"으로 조용히 넘어가기 때문이다.
 * - status는 보내지 않는다. 상태는 상세 화면에서만 바꾼다.
 */
function readPayload() {
  const payload = {};
  for (const field of TEXT_FIELDS) payload[field] = form.elements.namedItem(field).value;

  const emptyValue = isEdit ? null : undefined; // JSON.stringify는 undefined 값을 빼고 보낸다.
  const condition = form.elements.condition.value;
  const price = form.elements.price.value.trim();
  payload.condition = condition === "" ? emptyValue : condition;
  payload.price = price === "" ? emptyValue : Number(price);
  return payload;
}

async function onSubmit(event) {
  event.preventDefault();
  clearFormErrors(form, formError);
  setSubmitting(true);

  try {
    const saved = isEdit ? await updatePost(postId, readPayload()) : await createPost(readPayload());
    // replace를 써서, 뒤로 가기를 눌렀을 때 입력이 끝난 폼으로 돌아오지 않게 한다.
    window.location.replace(postDetailUrl(saved.id));
  } catch (error) {
    if (error.status === 401) {
      // 토큰이 만료되었다. 로그인 후 이 화면으로 돌아온다. (입력한 내용은 남지 않는다)
      redirectToLogin();
      return;
    }
    // 422는 칸 아래에, 400·403·404는 서버 메시지를 폼 아래에 보여준다.
    showFormErrors(form, formError, error);
    form.querySelector('[aria-invalid="true"]')?.focus();
    setSubmitting(false);
  }
}

function setSubmitting(isSubmitting) {
  submitButton.disabled = isSubmitting;
  submitButton.textContent = isSubmitting ? "저장 중…" : submitLabel;
}

function postDetailUrl(id) {
  return `/static/post.html?id=${encodeURIComponent(id)}`;
}
