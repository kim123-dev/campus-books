// 서버 API 호출은 모두 이 파일을 거친다.
// 화면 코드(pages/*.js)가 fetch, 토큰 헤더, 에러 형식을 직접 다루지 않게 하기 위해서다.
import { clearToken, getToken } from "./auth.js";

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
  if (!response.ok) {
    // 토큰이 만료되었거나 잘못되었으면 지워서, 다음 요청부터는 로그인하지 않은 상태로 동작하게 한다.
    if (response.status === 401) clearToken();
    throw toApiError(response.status, data);
  }
  return data;
}

// ---------- 화면에서 쓰는 API ----------

/** 판매글 목록. params: q, status, course_name, min_price, max_price, page, size */
export function listPosts(params) {
  return request("/posts", { query: params });
}

// ---------- 에러 변환 ----------

function toApiError(status, data) {
  const detail = data?.detail;

  // 400/401/403/404/409: 서버가 보낸 한국어 메시지를 그대로 보여준다.
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
      return String(msg).replace(/^Value error, /, "");
    default:
      return "입력값을 확인해 주세요.";
  }
}
