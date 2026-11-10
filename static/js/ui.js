// 화면 요소를 만드는 공통 함수와 표시 형식.
// HTML 문자열을 해석해 요소를 만드는 API는 쓰지 않고, 값은 항상 textContent로 넣는다.
// 글 제목처럼 사용자가 입력한 값에 <script>가 들어 있어도 글자로만 보이고 실행되지 않기 때문이다.
// (tests/test_static.py가 이 규칙을 검사한다)

/**
 * DOM 요소를 만든다.
 * - props.text: textContent로 넣는다.
 * - props.attrs: setAttribute로 넣는다.
 * - 그 밖의 props(className, href, type, disabled 등): 요소의 속성으로 넣는다.
 * - children: Node 또는 문자열. 문자열은 append가 텍스트 노드로 만든다.
 */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  const { text, attrs, ...rest } = props;
  Object.assign(node, rest);
  if (attrs) {
    for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
  }
  if (text !== undefined && text !== null) node.textContent = String(text);
  node.append(...children.filter((child) => child !== null && child !== undefined && child !== false));
  return node;
}

// 모바일 화면 기준. style.css의 @media (max-width: 767.98px)와 같은 값이어야 한다. (tests/test_static.py가 확인)
export const MOBILE_QUERY = "(max-width: 767.98px)";

const SVG_NS = "http://www.w3.org/2000/svg";
// 하단 탭 바, 검색·필터 버튼, 설치 안내의 아이콘 (24×24 선 아이콘)
const ICON_PATHS = {
  home: "M3.5 10.5 12 3.5l8.5 7V20a1 1 0 0 1-1 1H15v-6H9v6H4.5a1 1 0 0 1-1-1z",
  heart: "M12 20.5s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.6a4.3 4.3 0 0 1 7.5 2.7c0 5.6-7.5 10.2-7.5 10.2z",
  plus: "M12 5v14M5 12h14",
  chat: "M4 5.5h16v11H9l-5 4z",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4.5 20.5c0-3.6 3.4-5.5 7.5-5.5s7.5 1.9 7.5 5.5",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4",
  bell: "M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15zM10 20.5a2 2 0 0 0 4 0",
  filter: "M4 7h16M7 12h10M10 17h4",
  share: "M12 3.5v11M8 7.5l4-4 4 4M8 10.5H6v10h12v-10h-2", // iOS Safari의 공유 버튼 모양 (설치 안내)
};

/** 선 아이콘(svg). HTML 문자열 없이 createElementNS로 만든다. 꾸밈용이라 화면 낭독기에서는 숨긴다. */
export function icon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.setAttribute("class", `icon icon--${name}`);
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", ICON_PATHS[name]);
  svg.append(path);
  return svg;
}

export const STATUS_LABELS = {
  ON_SALE: "판매 중",
  RESERVED: "예약 중",
  SOLD: "판매 완료",
};

export const CONDITION_LABELS = {
  GOOD: "상",
  FAIR: "중",
  POOR: "하",
};

export function formatPrice(price) {
  return price === 0 ? "무료 나눔" : `${price.toLocaleString("ko-KR")}원`;
}

// 서버(SQLite)는 UTC 시간을 시간대 표시 없이 돌려준다.
// 그대로 Date에 넣으면 브라우저가 현지 시간으로 오해하므로, 시간대가 없으면 UTC(Z)로 본다.
export function formatDate(isoText) {
  const date = parseServerDate(isoText);
  if (date === null) return "";
  return `${date.getFullYear()}.${pad2(date.getMonth() + 1)}.${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

/**
 * 쪽지처럼 시각이 자주 보이는 곳에 쓰는 짧은 형식.
 * 오늘이면 "14:20", 올해면 "11.08 14:20", 그 밖에는 formatDate와 같다.
 */
export function formatShortDate(isoText) {
  const date = parseServerDate(isoText);
  if (date === null) return "";
  const now = new Date();
  const time = `${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
  if (date.toDateString() === now.toDateString()) return time;
  if (date.getFullYear() === now.getFullYear()) return `${pad2(date.getMonth() + 1)}.${pad2(date.getDate())} ${time}`;
  return formatDate(isoText);
}

/** 정지 안내처럼 "언제까지"를 알려줄 때 쓰는 형식. "11월 16일 14:00" (해가 다르면 연도도) */
export function formatMonthDayTime(isoText) {
  const date = parseServerDate(isoText);
  if (date === null) return "";
  const year = date.getFullYear() !== new Date().getFullYear() ? `${date.getFullYear()}년 ` : "";
  return `${year}${date.getMonth() + 1}월 ${date.getDate()}일 ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function parseServerDate(isoText) {
  if (typeof isoText !== "string") return null;
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(isoText);
  const date = new Date(hasZone ? isoText : `${isoText}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

export function statusBadge(status) {
  return el("span", {
    className: `badge badge--${status.toLowerCase()}`,
    text: STATUS_LABELS[status] ?? status,
  });
}

/** 폼 안의 모든 필드 에러와 공통 에러를 지운다. */
export function clearFormErrors(form, generalErrorEl) {
  for (const node of form.querySelectorAll("[data-error-for]")) {
    node.textContent = "";
    node.hidden = true;
  }
  for (const input of form.querySelectorAll("[aria-invalid]")) input.removeAttribute("aria-invalid");
  if (generalErrorEl) {
    generalErrorEl.textContent = "";
    generalErrorEl.hidden = true;
  }
}

/**
 * ApiError를 폼에 표시한다.
 * 해당 입력칸이 있는 필드 에러는 칸 아래에, 나머지는 공통 에러 영역에 보여준다.
 */
export function showFormErrors(form, generalErrorEl, error) {
  const leftover = [];
  for (const [field, message] of Object.entries(error.fieldErrors ?? {})) {
    const slot = form.querySelector(`[data-error-for="${CSS.escape(field)}"]`);
    if (slot) {
      slot.textContent = message;
      slot.hidden = false;
      form.elements.namedItem(field)?.setAttribute("aria-invalid", "true");
    } else {
      leftover.push(message);
    }
  }
  const hasFieldErrors = Object.keys(error.fieldErrors ?? {}).length > 0;
  const general = leftover.length > 0 ? leftover.join(" ") : hasFieldErrors ? "" : error.message;
  if (generalErrorEl && general) {
    generalErrorEl.textContent = general;
    generalErrorEl.hidden = false;
  }
}

/**
 * 주소의 ?id= 값을 글 번호로 읽는다. 1 이상의 정수가 아니면 null.
 * 숫자가 아닌 id로 요청하면 서버는 "정수로 입력해 주세요."(422)를 주는데, 화면에서는 뜻이 통하지 않아
 * 상세·수정 화면이 요청 전에 같은 규칙으로 걸러낸다.
 */
export function readPostIdFromUrl() {
  const raw = new URLSearchParams(window.location.search).get("id");
  return raw !== null && /^[1-9]\d*$/.test(raw) ? raw : null;
}

// ---------- 판매글 카드와 페이지 이동 (목록 화면과 내 글 화면이 함께 쓴다) ----------

/** 사진이 없는 글에 보여줄 기본 그림 */
export const PLACEHOLDER_IMAGE = "/static/img/book-placeholder.svg";

/**
 * 서버가 준 사진 주소가 이미지 전용 경로(/images/...)일 때만 쓴다. 그 밖의 값이면 기본 그림.
 * 서버가 만든 주소만 오지만, 화면도 img의 src에 엉뚱한 주소가 들어가지 않게 한 번 더 막는다.
 */
export function safeImageUrl(url) {
  return typeof url === "string" && /^\/images\/[0-9a-f]{32}(_thumb)?\.webp$/.test(url) ? url : PLACEHOLDER_IMAGE;
}

/**
 * 판매글 카드 하나(li). 누르면 상세 화면으로 간다.
 * @param {{action?: Node|null}} options action: 카드 위에 겹쳐 놓을 버튼(찜 하트).
 *   카드 전체가 링크라 그 안에 버튼을 넣을 수 없으므로(HTML 규칙), 링크 옆에 두고 CSS로 사진 위에 겹친다.
 */
export function renderPostCard(post, { action = null } = {}) {
  const courseText = post.course_name ? ` · ${post.course_name}` : "";
  // 카드 안의 제목이 링크 이름이 되므로, 사진은 꾸밈 요소로 두어(alt="") 화면 낭독기가 두 번 읽지 않게 한다.
  const thumbnail = el("img", {
    className: "post-card__thumb",
    src: safeImageUrl(post.thumbnail_url),
    alt: "",
    loading: "lazy",
    decoding: "async",
    width: 400,
    height: 300,
  });
  return el(
    "li",
    { className: "post-list__item" },
    el(
      "a",
      { className: "card post-card", href: `/static/post.html?id=${encodeURIComponent(post.id)}` },
      thumbnail,
      // 글자 묶음. 모바일에서는 사진 오른쪽에 두는 가로형 카드가 된다. (PC는 사진 아래에 그대로)
      el(
        "div",
        { className: "post-card__body" },
        el(
          "div",
          { className: "post-card__top" },
          statusBadge(post.status),
          el("span", { className: "post-card__condition", text: `책 상태 ${CONDITION_LABELS[post.condition] ?? post.condition}` }),
        ),
        el("h2", { className: "post-card__title", text: post.title }),
        el("p", { className: "post-card__book", text: `${post.book_title}${courseText}` }),
        el("p", { className: "post-card__price", text: formatPrice(post.price) }),
        el("p", { className: "post-card__meta", text: `${post.seller.nickname} · ${formatDate(post.created_at)}` }),
      ),
    ),
    action,
  );
}

/**
 * "이전 / 2 / 5 페이지 / 다음" 버튼을 그린다. 한 페이지뿐이면 아무것도 그리지 않는다.
 * 범위를 넘은 페이지(?page=99)에서 "이전"을 누르면 마지막 페이지로 가게 해, 빈 화면에서 빠져나올 수 있게 한다.
 * @param {(page: number) => void} onPageChange 버튼을 눌렀을 때 이동할 페이지 번호를 받는다.
 */
export function renderPagination(container, page, totalPages, onPageChange) {
  if (totalPages <= 1 && page === 1) {
    container.replaceChildren();
    return;
  }

  const prev = el("button", { type: "button", className: "button", text: "이전", disabled: page <= 1 });
  const next = el("button", { type: "button", className: "button", text: "다음", disabled: page >= totalPages });
  prev.addEventListener("click", () => onPageChange(Math.min(page - 1, totalPages)));
  next.addEventListener("click", () => onPageChange(page + 1));

  container.replaceChildren(
    prev,
    el("span", { className: "pagination__info", text: `${page} / ${totalPages} 페이지` }),
    next,
  );
}
