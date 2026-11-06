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
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(isoText);
  const date = new Date(hasZone ? isoText : `${isoText}Z`);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}.${pad(date.getMonth() + 1)}.${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
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

/** 판매글 카드 하나(li). 누르면 상세 화면으로 간다. */
export function renderPostCard(post) {
  const courseText = post.course_name ? ` · ${post.course_name}` : "";
  return el(
    "li",
    {},
    el(
      "a",
      { className: "card post-card", href: `/static/post.html?id=${encodeURIComponent(post.id)}` },
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
