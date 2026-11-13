// 서버 API 호출은 모두 이 파일을 거친다.
// 화면 코드(pages/*.js)가 fetch, 토큰 헤더, 에러 형식을 직접 다루지 않게 하기 위해서다.
import { clearToken, getToken } from "./token.js";

/** API 실패를 화면에서 한 가지 형식으로 다루기 위한 에러. */
export class ApiError extends Error {
  /**
   * @param {number} status HTTP 상태 코드 (서버에 연결하지 못하면 0)
   * @param {string} message 화면에 보여줄 메시지
   * @param {Record<string, string>} fieldErrors 422일 때 필드 이름별 메시지
   */
  constructor(status, message, fieldErrors = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
    /** 429일 때 서버가 알려준 재시도 대기 시간(초). 그 밖에는 null. */
    this.retryAfter = null;
  }
}

/**
 * 공통 요청 함수.
 * @param {string} path 예: "/posts"
 * @param {{method?: string, query?: object, json?: object, form?: object}} options
 */
export async function request(path, { method = "GET", query, json, form } = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    // 빈 값은 보내지 않는다. 서버에서 "조건 없음"으로 처리되도록 하기 위해서다.
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  }

  const headers = { Accept: "application/json" };
  let body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form !== undefined) {
    // 로그인 API는 OAuth2 규격상 form 형식으로 받는다.
    body = new URLSearchParams(form);
  }
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(url, { method, headers, body });
  } catch {
    throw new ApiError(0, "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
  }

  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) throw failure(response.status, data, response.headers.get("Retry-After"));
  return data;
}

/** 실패 응답을 ApiError로 바꾼다. fetch와 XHR(업로드 진행률) 요청이 함께 쓴다. */
function failure(status, data, retryAfterHeader) {
  // 토큰이 만료되었거나 잘못되었으면 지워서, 다음 요청부터는 로그인하지 않은 상태로 동작하게 한다.
  if (status === 401) clearToken();
  const error = toApiError(status, data);
  // 쪽지 도배 제한(429)은 몇 초 뒤에 다시 보낼 수 있는지 헤더로 알려준다.
  if (status === 429) error.retryAfter = Number(retryAfterHeader) || null;
  return error;
}

/**
 * 파일 업로드. fetch는 보낸 양(진행률)을 알려주지 않으므로 XMLHttpRequest를 쓴다.
 * @param {(ratio: number) => void} [onProgress] 0~1 사이 값으로 보낸 비율을 알려준다.
 * @param {AbortSignal} [signal] 취소하면 전송을 멈추고, aborted가 true인 ApiError로 끝난다.
 */
function uploadWithProgress(path, formData, onProgress, signal) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", new URL(path, window.location.origin));
    xhr.setRequestHeader("Accept", "application/json");
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && onProgress) onProgress(event.loaded / event.total);
    });
    xhr.addEventListener("load", () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {}
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(failure(xhr.status, data, xhr.getResponseHeader("Retry-After")));
    });
    const offline = () => reject(new ApiError(0, "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."));
    xhr.addEventListener("error", offline);
    xhr.addEventListener("abort", () => {
      // 사용자가 사진을 빼서 멈춘 것과 연결이 끊긴 것을 화면이 구분할 수 있게 표시해 둔다.
      const error = new ApiError(0, "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
      error.aborted = signal?.aborted === true;
      reject(error);
    });
    signal?.addEventListener("abort", () => xhr.abort());
    // Content-Type은 브라우저가 multipart 경계(boundary) 값을 붙여 직접 정하므로 지정하지 않는다.
    xhr.send(formData);
  });
}

/**
 * 로그인이 필요한 사진을 받아 Blob으로 돌려준다. (쪽지 사진·신고된 쪽지 사진)
 * <img src="...">로는 토큰을 붙일 수 없어 fetch로 받고, 화면은 URL.createObjectURL로 보여준다.
 */
async function requestBlob(path, query = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(query)) url.searchParams.set(key, value);
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(url, { headers });
  } catch {
    throw new ApiError(0, "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw failure(response.status, data, response.headers.get("Retry-After"));
  }
  return response.blob();
}

// ---------- 화면에서 쓰는 API ----------

/** 판매글 목록. params: q, status, course_name, min_price, max_price, page, size */
export function listPosts(params) {
  return request("/posts", { query: params });
}

/** 내 판매글 목록. 판매 완료를 포함한 모든 상태를 최신순으로 준다. params: page, size */
export function listMyPosts(params) {
  return request("/users/me/posts", { query: params });
}

/** 판매글 상세. 로그인하지 않아도 볼 수 있다. */
export function getPost(postId) {
  return request(`/posts/${encodeURIComponent(postId)}`);
}

/** 판매글 작성. data: {title, book_title, course_name, condition, price, description} */
export function createPost(data) {
  return request("/posts", { method: "POST", json: data });
}

/** 판매글 수정. 보낸 필드만 바뀐다. (status는 changePostStatus로만 바꾼다) */
export function updatePost(postId, data) {
  return request(`/posts/${encodeURIComponent(postId)}`, { method: "PATCH", json: data });
}

/**
 * 판매 상태 변경. 바뀐 글 전체를 돌려받아 화면을 다시 그리는 데 쓴다.
 * buyerId: 판매 완료(SOLD)로 바꿀 때 거래한 사람. 생략하면 구매자 없이 완료한다.
 */
export function changePostStatus(postId, status, buyerId = null) {
  const json = buyerId === null ? { status } : { status, buyer_id: buyerId };
  return request(`/posts/${encodeURIComponent(postId)}/status`, { method: "PATCH", json });
}

/** 판매자용 구매자 정보. 응답: {buyer: {id, nickname} | null, candidates: [...], changeable} */
export function getPostBuyer(postId) {
  return request(`/posts/${encodeURIComponent(postId)}/buyer`);
}

/** 판매 완료된 글의 구매자 변경. buyerId가 null이면 "선택 안 함". 409(후기가 있음·구매자 없이 완료) */
export function changePostBuyer(postId, buyerId) {
  return request(`/posts/${encodeURIComponent(postId)}/buyer`, { method: "PUT", json: { buyer_id: buyerId } });
}

/** 판매글 삭제. 성공하면 본문 없이 204가 오므로 null을 돌려준다. */
export function deletePost(postId) {
  return request(`/posts/${encodeURIComponent(postId)}`, { method: "DELETE" });
}

/**
 * 임시 사진 한 장 올리기(글에 붙이기 전). 응답: {id}. 글을 저장할 때 이 id를 image_ids·add_image_ids로 보낸다.
 * 413(25MB 초과), 422(형식·해상도·손상), 429. onProgress(0~1)로 보낸 비율을 알려주고, signal로 취소한다.
 */
export function uploadPendingImage(file, onProgress, signal) {
  const formData = new FormData();
  formData.append("file", file);
  return uploadWithProgress("/pending-images", formData, onProgress, signal);
}

/** 임시 사진 한 장 삭제(글쓰기 화면에서 사진을 뺐을 때). 서버가 파일도 함께 지운다. */
export function deletePendingImage(pendingId) {
  return request(`/pending-images/${encodeURIComponent(pendingId)}`, { method: "DELETE" });
}

// ---------- 찜 ----------

/** 찜하기. 새로 찜하면 201, 이미 찜했으면 200. 응답: {post_id, is_wishlisted} */
export function addWishlist(postId) {
  return request(`/posts/${encodeURIComponent(postId)}/wishlist`, { method: "POST" });
}

/** 찜 해제. 찜하지 않은 글이어도 성공(204)한다. */
export function removeWishlist(postId) {
  return request(`/posts/${encodeURIComponent(postId)}/wishlist`, { method: "DELETE" });
}

/** 내 찜 목록(찜한 순서 최신순, 판매 완료 포함). params: page, size */
export function listWishlist(params) {
  return request("/users/me/wishlist", { query: params });
}

// ---------- 차단·신고 ----------

/** 사용자 차단. 새로 차단하면 201, 이미 차단했으면 200. 자기 자신은 400. */
export function blockUser(userId) {
  return request(`/users/${encodeURIComponent(userId)}/block`, { method: "POST" });
}

/** 차단 해제. 차단하지 않은 사람이어도 성공(204)한다. */
export function unblockUser(userId) {
  return request(`/users/${encodeURIComponent(userId)}/block`, { method: "DELETE" });
}

/** 내 차단 목록(차단한 순서 최신순). params: page, size */
export function listBlocks(params) {
  return request("/users/me/blocks", { query: params });
}

/** 글 신고. data: {reason, description}. 409(이미 신고), 429(횟수 제한) */
export function reportPost(postId, data) {
  return request(`/posts/${encodeURIComponent(postId)}/reports`, { method: "POST", json: data });
}

/** 관리자: 신고 목록. params: {status: PENDING|RESOLVED|생략, page, size}. 관리자가 아니면 403 */
export function listAdminReports(params) {
  return request("/admin/reports", { query: params });
}

/** 관리자: 신고 처리. data: {action, suspend_days?, note?, include_same_user?}. 기각 외에는 note 필수. 409(이미 처리) */
export function resolveReport(reportId, data) {
  return request(`/admin/reports/${encodeURIComponent(reportId)}/resolve`, { method: "POST", json: data });
}

/** 관리자: 대시보드 (가입자·글·미처리 신고 수) */
export function getAdminDashboard() {
  return request("/admin/dashboard");
}

/** 관리자: 사용자 목록·검색. params: {status, q, page, size} */
export function listAdminUsers(params) {
  return request("/admin/users", { query: params });
}

/** 관리자: 사용자 상세 (이메일, 글·신고·후기 수, 정지 이력) */
export function getAdminUser(userId) {
  return request(`/admin/users/${encodeURIComponent(userId)}`);
}

/** 관리자: 직접 정지. data: {days, reason} */
export function suspendUser(userId, data) {
  return request(`/admin/users/${encodeURIComponent(userId)}/suspend`, { method: "POST", json: data });
}

/** 관리자: 정지 해제. data: {reason} */
export function unsuspendUser(userId, data) {
  return request(`/admin/users/${encodeURIComponent(userId)}/unsuspend`, { method: "POST", json: data });
}

/** 관리자: 강제 탈퇴. data: {reason, ban_email} */
export function forceWithdrawUser(userId, data) {
  return request(`/admin/users/${encodeURIComponent(userId)}/withdraw`, { method: "POST", json: data });
}

/** 관리자: 재가입 차단 목록 (차단 시각·사유만). params: {page, size} */
export function listEmailBans(params) {
  return request("/admin/email-bans", { query: params });
}

/** 관리자: 재가입 차단 해제. data: {email, reason}. 성공하면 204(null) */
export function unbanEmail(data) {
  return request("/admin/email-bans/unban", { method: "POST", json: data });
}

/** 관리자: 글 목록. params: {q, status, seller_id, page, size} */
export function listAdminPosts(params) {
  return request("/admin/posts", { query: params });
}

/** 관리자: 후기 목록. params: {hidden, reviewee_id, reviewer_id, page, size} */
export function listAdminReviews(params) {
  return request("/admin/reviews", { query: params });
}

/** 관리자: 글 삭제. data: {reason}. 함께 처리한 신고 번호를 돌려준다. */
export function adminDeletePost(postId, data) {
  return request(`/admin/posts/${encodeURIComponent(postId)}/delete`, { method: "POST", json: data });
}

/** 관리자: 후기 숨김 해제. data: {reason}. 성공하면 204(null) */
export function unhideReview(reviewId, data) {
  return request(`/admin/reviews/${encodeURIComponent(reviewId)}/unhide`, { method: "POST", json: data });
}

/** 관리자: 관리 기록. params: {action, admin_id, target_user_id, page, size} */
export function listAdminActions(params) {
  return request("/admin/actions", { query: params });
}

/** 거래 후기 신고. data: {reason, description}. 400(내가 쓴 후기), 404(숨긴 후기), 409, 429 */
export function reportReview(reviewId, data) {
  return request(`/reviews/${encodeURIComponent(reviewId)}/reports`, { method: "POST", json: data });
}

/** 사용자 신고. data: {reason, description}. 409(이미 신고), 429(횟수 제한) */
/** 쪽지 한 건 신고. 상대가 보낸 메시지만 신고할 수 있다. data: {reason, description} */
export function reportMessage(messageId, data) {
  return request(`/messages/${encodeURIComponent(messageId)}/reports`, { method: "POST", json: data });
}

export function reportUser(userId, data) {
  return request(`/users/${encodeURIComponent(userId)}/reports`, { method: "POST", json: data });
}

// ---------- 거래 후기·프로필 ----------

/** 거래 후기 작성. data: {rating: "GOOD"|"BAD", content}. 409(이미 작성), 400(기간 지남), 404(상대 탈퇴) */
export function createReview(tradeId, data) {
  return request(`/trades/${encodeURIComponent(tradeId)}/reviews`, { method: "POST", json: data });
}

/** 프로필(닉네임, 매너 점수). 로그인하지 않아도 볼 수 있다. 없거나 탈퇴한 사용자는 404. */
export function getProfile(userId) {
  return request(`/users/${encodeURIComponent(userId)}/profile`);
}

/** 프로필의 판매 중·예약 중인 글. params: page, size */
export function listProfilePosts(userId, params) {
  return request(`/users/${encodeURIComponent(userId)}/posts`, { query: params });
}

/** 프로필의 받은 후기(최신순). params: page, size */
export function listProfileReviews(userId, params) {
  return request(`/users/${encodeURIComponent(userId)}/reviews`, { query: params });
}

// ---------- 쪽지 ----------

/** 판매글 문의 시작. 이미 대화방이 있으면 그 방을 돌려준다. (새 방 201, 기존 방 200) */
export function startConversation(postId) {
  return request(`/posts/${encodeURIComponent(postId)}/conversations`, { method: "POST" });
}

/** 내 대화방 목록(최신 메시지순). params: page, size */
export function listConversations(params) {
  return request("/conversations", { query: params });
}

/** 대화방 정보 하나 (상대 닉네임, 글 제목 등). */
export function getConversation(conversationId) {
  return request(`/conversations/${encodeURIComponent(conversationId)}`);
}

/** 헤더 배지용 안 읽은 쪽지 수. */
export function getUnreadCount() {
  return request("/conversations/unread-count");
}

/**
 * 메시지 목록. 서버가 이 조회로 상대 메시지를 읽음 처리한다.
 * params: after_id(새 메시지) 또는 before_id(이전 메시지), limit. 응답 items는 오래된 것부터.
 */
export function listMessages(conversationId, params) {
  return request(`/conversations/${encodeURIComponent(conversationId)}/messages`, { query: params });
}

/** 메시지 전송. 짧은 시간에 많이 보내면 429(error.retryAfter초 뒤 재시도). */
/** 대화방 나가기. 내 목록에서만 사라지고 상대에게는 남는다. */
export function leaveConversation(conversationId) {
  return request(`/conversations/${encodeURIComponent(conversationId)}/leave`, { method: "POST" });
}

/**
 * 사진 한 장을 쪽지로 보낸다. 응답은 sendMessage와 같은 메시지(has_image: true).
 * 413(25MB 초과), 422(형식·해상도·손상), 400(차단·탈퇴), 403(이용 정지), 429(쪽지 10초 5건·사진 10분 10장).
 */
export function sendMessageImage(conversationId, file, onProgress) {
  const formData = new FormData();
  formData.append("file", file);
  return uploadWithProgress(`/conversations/${encodeURIComponent(conversationId)}/images`, formData, onProgress);
}

/** 쪽지 사진(Blob). size: "thumb"(대화 화면) 또는 "full"(크게 보기). 대화 참여자만 받을 수 있다. */
export function fetchMessageImage(messageId, size = "full") {
  return requestBlob(`/messages/${encodeURIComponent(messageId)}/image`, { size });
}

/** 관리자: 쪽지 신고에 남은 사진(Blob). 신고된 메시지의 사진만 볼 수 있다. */
export function fetchReportedImage(reportId) {
  return requestBlob(`/admin/reports/${encodeURIComponent(reportId)}/image`);
}

export function sendMessage(conversationId, content) {
  return request(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: "POST",
    json: { content },
  });
}

/** 로그인. 서버 규격(OAuth2)상 이메일을 username이라는 이름의 form 값으로 보낸다. */
export function login(username, password) {
  return request("/auth/login", { method: "POST", form: { username, password } });
}

/** 회원가입. data: {email, password, nickname} */
export function signup(data) {
  return request("/auth/signup", { method: "POST", json: data });
}

/** 내 정보. 헤더의 닉네임 표시와 "이미 로그인했는지" 확인에 쓴다. */
// 성공하면 새 토큰을 준다. 변경 전 토큰은 서버에서 무효가 되므로 바로 바꿔 저장해야 한다.
export function changePassword(currentPassword, newPassword) {
  return request("/users/me/password", {
    method: "PUT",
    json: { current_password: currentPassword, new_password: newPassword },
  });
}

export function withdraw(password) {
  return request("/users/me/withdraw", { method: "POST", json: { password } });
}

/** 본인 확인 질문 등록·변경 (현재 비밀번호 확인). 응답: 내 정보(MeResponse) */
export function setSecurityQuestion(password, securityQuestion) {
  return request("/users/me/security-question", { method: "PUT", json: { password, security_question: securityQuestion } });
}

/** "비밀번호가 재설정됐어요" 안내를 확인했다. */
export function dismissResetNotice() {
  return request("/users/me/password-reset-notice/dismiss", { method: "POST" });
}

/** 재설정 1단계(로그인 없이): 이메일로 그 계정의 질문 받기. 응답: { question } */
export function getResetQuestion(email) {
  return request("/auth/password-reset/question", { method: "POST", json: { email } });
}

/** 재설정 2단계(로그인 없이): 답 확인 { email, answer }. 맞으면 { reset_token, expires_in } */
export function verifyResetAnswer(data) {
  return request("/auth/password-reset/verify", { method: "POST", json: data });
}

/** 재설정 3단계(로그인 없이): { reset_token, new_password }. 성공하면 204 */
export function resetPassword(data) {
  return request("/auth/password-reset", { method: "POST", json: data });
}

// ---------- 찾는 교재 알림 ----------

export function listAlerts() {
  return request("/users/me/alerts");
}

export function createAlert(data) {
  return request("/users/me/alerts", { method: "POST", json: data });
}

export function deleteAlert(alertId) {
  return request(`/users/me/alerts/${encodeURIComponent(alertId)}`, { method: "DELETE" });
}

export function listNotifications(params) {
  return request("/notifications", { query: params });
}

export function getAlertUnreadCount() {
  return request("/notifications/unread-count");
}

export function markAllNotificationsRead() {
  return request("/notifications/read-all", { method: "POST" });
}

export function getMe() {
  return request("/users/me");
}

/** 내 정보 수정. 지금은 닉네임만 바꿀 수 있다(30일에 한 번). data: { nickname } */
export function updateMe(data) {
  return request("/users/me", { method: "PATCH", json: data });
}

// ---------- 에러 변환 ----------

function toApiError(status, data) {
  const detail = data?.detail;

  // 400/401/403/404/409/413, 사진 형식 422: 서버가 보낸 한국어 메시지를 그대로 보여준다.
  if (typeof detail === "string") return new ApiError(status, detail);

  // 422: [{loc: ["query", "min_price"], msg, type, ctx}, ...]
  if (Array.isArray(detail)) {
    const fieldErrors = {};
    const general = [];
    for (const item of detail) {
      const loc = item.loc ?? [];
      // loc의 마지막 값이 필드 이름이다. ["query"]처럼 필드가 없으면 여러 필드를 함께 본 검사다.
      const field = loc.length > 1 ? String(loc[loc.length - 1]) : null;
      const message = translateValidation(item);
      if (field && !(field in fieldErrors)) fieldErrors[field] = message;
      else if (!field) general.push(message);
    }
    return new ApiError(status, general.join(" ") || "입력값을 확인해 주세요.", fieldErrors);
  }

  return new ApiError(status, "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.");
}

// Pydantic 기본 메시지는 영어라서 자주 나오는 종류만 한국어로 바꾼다.
// 서버가 직접 만든 메시지(ValueError)는 "Value error, " 앞부분만 떼고 그대로 쓴다.
function translateValidation({ type, msg, ctx = {} }) {
  switch (type) {
    case "missing":
      return "필수 항목입니다.";
    case "greater_than_equal":
      return `${ctx.ge} 이상이어야 합니다.`;
    case "less_than_equal":
      return `${ctx.le} 이하여야 합니다.`;
    case "int_parsing":
    case "int_type":
    case "int_from_float":
      return "정수로 입력해 주세요.";
    case "string_too_short":
      return ctx.min_length === 1 ? "내용을 입력해 주세요." : `${ctx.min_length}자 이상 입력해 주세요.`;
    case "string_too_long":
      return `${ctx.max_length}자 이하로 입력해 주세요.`;
    case "enum":
      return "선택할 수 없는 값입니다.";
    case "value_error":
      // 이메일 형식 검사(EmailStr)는 라이브러리의 영어 메시지가 오므로 따로 바꾼다.
      if (String(msg).startsWith("value is not a valid email address")) return "올바른 이메일 형식이 아닙니다.";
      // 수정 화면에서 가격·책 상태를 비우면 null을 보내는데, 서버 문구는 개발자용이라 화면용으로 바꾼다.
      if (String(msg).includes("null로 바꿀 수 없습니다")) return "필수 항목입니다.";
      return String(msg).replace(/^Value error, /, "");
    default:
      return "입력값을 확인해 주세요.";
  }
}
