// 작성·수정 공용 화면. 주소에 ?id=가 있으면 수정 모드, 없으면 작성 모드다.
// 입력 규칙 검사는 서버가 하고, 화면은 서버 메시지를 칸 아래(422)나 폼 아래(400·403·404)에 보여준다.
// 사진은 고르는 즉시 "임시 사진"으로 올려 두고, 저장할 때 글(JSON)과 함께 사진 번호만 보낸다.
// 글을 쓰는 동안 업로드가 끝나므로 저장 버튼을 누른 뒤 기다리는 시간이 거의 없다.
import { createPost, deletePendingImage, getPost, updatePost, uploadPendingImage } from "../api.js";
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

const isEdit = new URLSearchParams(window.location.search).has("id");
const postId = isEdit ? readPostIdFromUrl() : null;
const submitLabel = isEdit ? "저장하기" : "등록하기";

// 이미 올라간 사진: {id, url, thumbnail_url, removed}. removed면 저장할 때 지운다.
let existingPhotos = [];
// 새로 고른 사진: {file, previewUrl, state, pendingId, controller, done}.
// - file은 올리기 좋게 줄인 사진, previewUrl은 브라우저 안에서만 쓰는 임시 주소다. (브라우저가 열 수 없는 사진이면 null)
// - state: "uploading"(올리는 중) → "done"(서버에 임시 사진으로 올라감, pendingId가 생김) 또는 "failed"(다시 시도 가능)
// - controller는 올리는 중에 사진을 빼면 전송을 멈추는 데 쓰고, done은 올리기가 끝나면(성공·실패 모두) 끝나는 Promise다.
let newPhotos = [];
// 고른 사진을 줄이는 중이면 true. 그동안에는 저장과 사진 추가를 막는다.
let preparing = false;
// 저장하는 중이면 true. 그동안에는 사진 추가·빼기를 막는다.
let submitting = false;

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
    const photo = { file: prepared.file, previewUrl, state: "uploading", pendingId: null, controller: null, done: null };
    newPhotos.push(photo);
    // 다음 사진을 줄이는 동안 이 사진은 먼저 올라가기 시작한다.
    startUpload(photo);
    renderPhotos();
  }
  showPhotoStatus("");
  setPreparing(false);
  showPhotosError(problems.join(" "));
  renderPhotos();
}

// 사진 한 장을 임시 사진으로 올린다. 기다리지 않고 시작만 하며, 끝나면 그 칸만 다시 그린다.
function startUpload(photo) {
  photo.state = "uploading";
  photo.controller = new AbortController();
  photo.done = uploadPendingImage(photo.file, (ratio) => showTileProgress(photo, ratio), photo.controller.signal)
    .then((saved) => {
      photo.state = "done";
      photo.pendingId = saved.id;
      // 올라가는 사이에 사진을 뺐다면 서버에 남은 임시 사진을 지운다.
      if (!newPhotos.includes(photo)) discardPending(photo);
    })
    .catch((error) => {
      if (error.aborted) return; // 사용자가 올리는 중에 뺀 사진
      if (error.status === 401) {
        // 토큰이 만료되었다. 저장도 할 수 없으므로 로그인 화면으로 보낸다. (입력한 내용은 남지 않는다)
        redirectToLogin();
        return;
      }
      photo.state = "failed";
      if (newPhotos.includes(photo)) showPhotosError(error.message);
    })
    .finally(() => {
      if (newPhotos.includes(photo)) renderPhotos();
    });
}

// 진행률은 자주 바뀌므로 목록 전체를 다시 그리지 않고 그 칸의 글자만 바꾼다. (미리보기가 깜빡이지 않게)
function showTileProgress(photo, ratio) {
  // 다 보낸 뒤에도 서버가 사진을 처리하는 동안은 끝난 것이 아니므로 99%에서 멈춰 둔다.
  if (photo.progressText) photo.progressText.textContent = `${Math.min(99, Math.floor(ratio * 100))}%`;
}

function removeNewPhoto(photo) {
  newPhotos = newPhotos.filter((item) => item !== photo);
  if (photo.state === "uploading") photo.controller.abort();
  else if (photo.state === "done") discardPending(photo);
  if (photo.previewUrl) URL.revokeObjectURL(photo.previewUrl); // 브라우저가 붙잡고 있는 미리보기 메모리를 놓아준다.
  showPhotosError("");
  renderPhotos();
}

// 뺀 사진은 서버에서도 바로 지운다. 실패해도 화면에는 알리지 않는다. (남은 임시 사진은 서버가 24시간 뒤 지운다)
function discardPending(photo) {
  deletePendingImage(photo.pendingId).catch(() => {});
}

function setPreparing(isPreparing) {
  preparing = isPreparing;
  submitButton.disabled = isPreparing;
  photoInput.disabled = isPreparing || submitting || photoTotal() >= MAX_PHOTOS;
}

// 사진 줄이기 진행 상황(몇 번째 사진). 올리기 진행률은 사진 칸 위에 따로 보여준다.
function showPhotoStatus(step) {
  photoStatus.textContent = step;
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
    ...newPhotos.map((photo, index) => newPhotoTile(photo, `새 사진 ${index + 1}`)),
  ];
  photoList.replaceChildren(...tiles);
  photoList.hidden = tiles.length === 0;

  const total = photoTotal();
  photoCount.textContent = `${total}/${MAX_PHOTOS}`;
  // 3장이 차면 "사진 추가"를 막는다. (label은 disabled가 없으므로 input을 막고 모양만 바꾼다)
  photoInput.disabled = preparing || submitting || total >= MAX_PHOTOS;
  // 올리기가 끝나 칸을 다시 그려도 저장 중에는 버튼이 잠긴 채로 있게 한다.
  for (const button of photoList.querySelectorAll("button")) button.disabled = submitting;
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
    // 사진 위에 올리기 상태를 겹쳐 보여줄 수 있게 틀로 감싼다.
    el(
      "div",
      { className: "photo-tile__frame" },
      el("img", { className: "photo-tile__image", src, alt: removed ? `${label} (저장하면 삭제됨)` : label }),
    ),
    button,
  );
}

// 새로 고른 사진 칸. 올리는 중이면 사진 위에 %를, 실패하면 "실패"와 다시 시도 버튼을 보여준다.
function newPhotoTile(photo, label) {
  const tile = photoTile(photo.previewUrl ?? NO_PREVIEW_IMAGE, label, false, () => removeNewPhoto(photo));
  photo.progressText = null;
  if (photo.state === "done") return tile;

  const failed = photo.state === "failed";
  tile.classList.add(failed ? "photo-tile--failed" : "photo-tile--uploading");
  // 칸이 좁아(375px 화면에서 약 100px) 올리는 중에는 %만 보여준다.
  // 화면 낭독기에는 "올리는 중"만 읽히고, 자주 바뀌는 %는 읽지 않는다.
  const badge = el("span", { className: "photo-tile__state", text: failed ? "실패" : null });
  if (!failed) {
    photo.progressText = el("span", { text: "0%", attrs: { "aria-hidden": "true" } });
    badge.append(el("span", { className: "visually-hidden", text: "올리는 중" }), photo.progressText);
  }
  tile.querySelector(".photo-tile__frame").append(badge);
  if (failed) {
    const retry = el("button", {
      type: "button",
      className: "photo-tile__button",
      text: "다시 시도",
      attrs: { "aria-label": `${label} 다시 올리기` },
    });
    retry.addEventListener("click", () => {
      showPhotosError("");
      startUpload(photo);
      renderPhotos();
    });
    tile.insertBefore(retry, tile.lastElementChild);
  }
  return tile;
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
 * - 사진은 번호만 보낸다. 작성은 올려 둔 임시 사진(image_ids), 수정은 지울 사진과 새 임시 사진을 함께 보낸다.
 */
function readPayload() {
  const payload = {};
  for (const field of TEXT_FIELDS) payload[field] = form.elements.namedItem(field).value;

  const emptyValue = isEdit ? null : undefined; // JSON.stringify는 undefined 값을 빼고 보낸다.
  const condition = form.elements.condition.value;
  const price = form.elements.price.value.trim();
  payload.condition = condition === "" ? emptyValue : condition;
  payload.price = price === "" ? emptyValue : Number(price);

  const pendingIds = newPhotos.map((photo) => photo.pendingId);
  if (isEdit) {
    payload.remove_image_ids = existingPhotos.filter((photo) => photo.removed).map((photo) => photo.id);
    payload.add_image_ids = pendingIds;
  } else {
    payload.image_ids = pendingIds;
  }
  return payload;
}

async function onSubmit(event) {
  event.preventDefault();
  clearFormErrors(form, formError);
  setSubmitting(true);

  // 아직 올라가는 사진이 있으면 끝날 때까지만 기다린다. (보통은 글을 쓰는 동안 이미 끝나 있다)
  if (newPhotos.some((photo) => photo.state === "uploading")) {
    submitButton.textContent = "사진 올리는 중…";
    await Promise.all(newPhotos.map((photo) => photo.done));
    submitButton.textContent = "저장 중…";
  }
  // 올리지 못한 사진을 빼고 저장하면 사진이 빠진 글이 올라가므로, 어떻게 할지 사용자가 정하게 한다.
  if (newPhotos.some((photo) => photo.state !== "done")) {
    showPhotosError("올리지 못한 사진이 있습니다. 다시 시도하거나 빼 주세요.");
    setSubmitting(false);
    return;
  }

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

  // 글과 사진이 한 번에 저장됐다. 미리보기 메모리를 놓아주고 상세 화면으로 간다.
  for (const photo of newPhotos) if (photo.previewUrl) URL.revokeObjectURL(photo.previewUrl);
  // replace를 써서, 뒤로 가기를 눌렀을 때 입력이 끝난 폼으로 돌아오지 않게 한다.
  window.location.replace(postDetailUrl(saved.id));
}

function setSubmitting(isSubmitting) {
  submitting = isSubmitting;
  submitButton.disabled = isSubmitting;
  submitButton.textContent = isSubmitting ? "저장 중…" : submitLabel;
  // 저장하는 동안 사진을 바꾸면 무엇이 저장되는지 헷갈리므로 사진 추가·빼기를 막는다.
  renderPhotos();
}

function postDetailUrl(id) {
  return `/static/post.html?id=${encodeURIComponent(id)}`;
}
