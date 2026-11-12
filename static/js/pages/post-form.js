// 작성·수정 공용 화면. 주소에 ?id=가 있으면 수정 모드, 없으면 작성 모드다.
// 입력 규칙 검사는 서버가 하고, 화면은 서버 메시지를 칸 아래(422)나 폼 아래(400·403·404)에 보여준다.
// 사진은 글(JSON)을 저장한 뒤 지울 사진 → 새 사진 순서로 한 장씩 따로 보낸다.
import { createPost, deletePostImage, getPost, updatePost, uploadPostImage } from "../api.js";
import { redirectToLogin, renderHeader } from "../auth.js";
import { preparePhoto } from "../photo-resize.js";
import { getToken } from "../token.js";
import { clearFormErrors, el, readPostIdFromUrl, safeImageUrl, showFormErrors } from "../ui.js";

const HOME_PAGE = "/static/index.html";
const TEXT_FIELDS = ["title", "book_title", "course_name", "description", "open_chat_url"];

// 서버 규칙과 같은 값. 서버가 최종 검사하고(400·413·422), 화면은 올리기 전에 미리 알려주는 용도다.
// 용량은 줄인 뒤의 크기로 본다. 보통 1MB 안팎으로 줄어들어, 줄이지 못한 사진(원본 그대로 보냄)에만 걸린다.
const MAX_PHOTOS = 3;
const MAX_PHOTO_BYTES = 25 * 1024 * 1024;
const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"];
// 일부 브라우저는 HEIC 파일의 형식(type)을 비워서 주므로 확장자로도 확인한다.
const HEIC_NAME = /\.hei[cf]$/i;
// 이 브라우저가 열 수 없어 미리보기를 못 그리는 사진(예: 안드로이드 크롬의 HEIC)에 대신 보여줄 그림
const NO_PREVIEW_IMAGE = "/static/img/book-placeholder.svg";

// 사진 업로드가 일부 실패하면 작성 모드에서 수정 모드로 바뀌므로 let으로 둔다.
let isEdit = new URLSearchParams(window.location.search).has("id");
let postId = isEdit ? readPostIdFromUrl() : null;
let submitLabel = isEdit ? "저장하기" : "등록하기";

// 이미 올라간 사진: {id, url, thumbnail_url, removed}. removed면 저장할 때 지운다.
let existingPhotos = [];
// 새로 고른 사진: {file, previewUrl}. file은 올리기 좋게 줄인 사진이고, previewUrl은 브라우저 안에서만 쓰는 임시 주소다.
// (브라우저가 열 수 없는 사진이면 previewUrl이 null이다)
let newPhotos = [];
// 고른 사진을 줄이는 중이면 true. 그동안에는 저장과 사진 추가를 막는다.
let preparing = false;

const pageStatus = document.getElementById("page-status");
const pageError = document.getElementById("page-error");
const pageErrorText = document.getElementById("page-error-text");
const pageErrorLink = document.getElementById("page-error-link");
const formCard = document.getElementById("form-card");
const form = document.getElementById("post-form");
const formError = document.getElementById("form-error");
const submitButton = form.querySelector('button[type="submit"]');
const photoInput = document.getElementById("photos");
const photoList = document.getElementById("photo-list");
const photoCount = document.getElementById("photo-count");
const photosError = document.getElementById("photos-error");
const photoStatus = document.getElementById("photo-status");

form.addEventListener("submit", onSubmit);
photoInput.addEventListener("change", onPhotosSelected);
renderPhotos();
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
  setExistingPhotos(post.images);
}

// ---------- 사진 고르기 ----------

function setExistingPhotos(images) {
  existingPhotos = (Array.isArray(images) ? images : []).map((image) => ({ ...image, removed: false }));
  renderPhotos();
}

function photoTotal() {
  return existingPhotos.filter((photo) => !photo.removed).length + newPhotos.length;
}

// 고른 파일을 미리 검사한다. 걸린 파일은 빼고 이유를 보여주며, 통과한 파일은 미리보기에 더한다.
async function onPhotosSelected() {
  const files = [...photoInput.files];
  // 같은 파일을 지웠다가 다시 고를 수 있도록 선택값을 비운다.
  photoInput.value = "";
  const problems = [];
  const accepted = [];
  for (const file of files) {
    if (!PHOTO_TYPES.includes(file.type) && !HEIC_NAME.test(file.name)) {
      problems.push(`${file.name}: JPG, PNG, WebP, HEIC 사진만 올릴 수 있습니다.`);
    } else if (photoTotal() + accepted.length >= MAX_PHOTOS) {
      problems.push(`사진은 ${MAX_PHOTOS}장까지 올릴 수 있어 ${file.name}은(는) 빼었습니다.`);
    } else {
      accepted.push(file);
    }
  }

  setPreparing(true);
  for (const [index, file] of accepted.entries()) {
    showPhotoStatus(`사진 줄이는 중… (${index + 1}/${accepted.length})`);
    const prepared = await preparePhoto(file);
    if (prepared.file.size > MAX_PHOTO_BYTES) {
      problems.push(`${file.name}: 사진은 한 장에 25MB까지 올릴 수 있습니다.`);
      continue;
    }
    const previewUrl = prepared.previewable ? URL.createObjectURL(prepared.file) : null;
    newPhotos.push({ file: prepared.file, previewUrl });
  }
  showPhotoStatus("");
  setPreparing(false);
  showPhotosError(problems.join(" "));
  renderPhotos();
}

function setPreparing(isPreparing) {
  preparing = isPreparing;
  submitButton.disabled = isPreparing;
  photoInput.disabled = isPreparing || photoTotal() >= MAX_PHOTOS;
}

// 사진 줄이기·올리기 진행 상황. 단계(몇 번째 사진)만 화면 낭독기로 읽히고, 자주 바뀌는 %는 읽지 않는다.
function showPhotoStatus(step, percent = null) {
  photoStatus.replaceChildren(
    el("span", { text: step }),
    ...(percent === null ? [] : [el("span", { text: ` · ${percent}%`, attrs: { "aria-hidden": "true" } })]),
  );
  photoStatus.hidden = step === "";
}

function renderPhotos() {
  const tiles = [
    ...existingPhotos.map((photo, index) =>
      photoTile(safeImageUrl(photo.thumbnail_url), `올린 사진 ${index + 1}`, photo.removed, () => {
        // 이미 올린 사진은 바로 지우지 않고 표시만 해 두었다가 저장할 때 지운다. 다시 누르면 되돌린다.
        if (photo.removed && photoTotal() >= MAX_PHOTOS) {
          showPhotosError(`사진은 ${MAX_PHOTOS}장까지라 되돌리려면 새 사진을 먼저 빼 주세요.`);
          return;
        }
        photo.removed = !photo.removed;
        showPhotosError("");
        renderPhotos();
      }),
    ),
    ...newPhotos.map((photo, index) =>
      photoTile(photo.previewUrl ?? NO_PREVIEW_IMAGE, `새 사진 ${index + 1}`, false, () => {
        if (photo.previewUrl) URL.revokeObjectURL(photo.previewUrl); // 브라우저가 붙잡고 있는 미리보기 메모리를 놓아준다.
        newPhotos = newPhotos.filter((item) => item !== photo);
        showPhotosError("");
        renderPhotos();
      }),
    ),
  ];
  photoList.replaceChildren(...tiles);
  photoList.hidden = tiles.length === 0;

  const total = photoTotal();
  photoCount.textContent = `${total}/${MAX_PHOTOS}`;
  // 3장이 차면 "사진 추가"를 막는다. (label은 disabled가 없으므로 input을 막고 모양만 바꾼다)
  photoInput.disabled = preparing || total >= MAX_PHOTOS;
}

function photoTile(src, label, removed, onToggle) {
  const button = el("button", {
    type: "button",
    className: "photo-tile__button",
    text: removed ? "되돌리기" : "빼기",
    attrs: { "aria-label": `${label} ${removed ? "되돌리기" : "빼기"}` },
  });
  button.addEventListener("click", onToggle);
  return el(
    "li",
    { className: removed ? "photo-tile photo-tile--removed" : "photo-tile" },
    el("img", { className: "photo-tile__image", src, alt: removed ? `${label} (저장하면 삭제됨)` : label }),
    button,
  );
}

function showPhotosError(message) {
  photosError.textContent = message;
  photosError.hidden = message === "";
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

  let saved;
  try {
    saved = isEdit ? await updatePost(postId, readPayload()) : await createPost(readPayload());
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
    return;
  }

  const failures = await savePhotos(saved.id);
  if (failures === null) return; // 로그인 화면으로 이동했다.
  if (failures.length === 0) {
    // replace를 써서, 뒤로 가기를 눌렀을 때 입력이 끝난 폼으로 돌아오지 않게 한다.
    window.location.replace(postDetailUrl(saved.id));
    return;
  }
  await showPartialFailure(saved.id, failures);
}

/**
 * 지울 사진을 지우고 새 사진을 한 장씩 올린다. 실패한 사진의 메시지 목록을 돌려준다. (401이면 null)
 * 지우기를 먼저 해야 "3장 중 1장 바꾸기"가 3장 제한(400)에 걸리지 않는다.
 */
async function savePhotos(id) {
  const failures = [];
  const tasks = [
    ...existingPhotos.filter((photo) => photo.removed).map((photo) => () => deletePostImage(id, photo.id)),
    ...newPhotos.map((photo) => (onProgress) => uploadPostImage(id, photo.file, onProgress)),
  ];
  for (const [index, task] of tasks.entries()) {
    const step = `사진 저장 중 ${index + 1}/${tasks.length}`;
    submitButton.textContent = `${step}…`;
    showPhotoStatus(step);
    try {
      // 지우기는 진행률이 없고, 올리기는 보낸 비율을 %로 보여준다.
      await task((ratio) => showPhotoStatus(step, Math.floor(ratio * 100)));
    } catch (error) {
      if (error.status === 401) {
        redirectToLogin();
        return null;
      }
      failures.push(error.message);
    }
  }
  showPhotoStatus("");
  return failures;
}

// 글은 저장됐으므로 다시 저장해도 글이 두 번 생기지 않게 수정 모드로 바꾸고, 서버의 현재 사진을 다시 보여준다.
async function showPartialFailure(id, failures) {
  for (const photo of newPhotos) if (photo.previewUrl) URL.revokeObjectURL(photo.previewUrl);
  newPhotos = [];
  if (!isEdit) {
    isEdit = true;
    postId = String(id);
    submitLabel = "저장하기";
    window.history.replaceState(null, "", `/static/post-form.html?id=${encodeURIComponent(id)}`);
    showForm();
  }
  try {
    setExistingPhotos((await getPost(id)).images);
  } catch {
    setExistingPhotos([]);
  }
  const count = failures.length;
  formError.textContent = `글은 저장됐지만 사진 ${count}장을 처리하지 못했습니다: ${[...new Set(failures)].join(" ")}`;
  formError.hidden = false;
  setSubmitting(false);
}

function setSubmitting(isSubmitting) {
  submitButton.disabled = isSubmitting;
  // 저장하는 동안 사진을 바꾸면 무엇이 올라갔는지 헷갈리므로 막는다.
  photoInput.disabled = isSubmitting || photoTotal() >= MAX_PHOTOS;
  for (const button of photoList.querySelectorAll("button")) button.disabled = isSubmitting;
  submitButton.textContent = isSubmitting ? "저장 중…" : submitLabel;
}

function postDetailUrl(id) {
  return `/static/post.html?id=${encodeURIComponent(id)}`;
}
