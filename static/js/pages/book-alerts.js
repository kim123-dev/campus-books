// 찾는 교재 화면: 조건(키워드·최대 가격)을 등록·삭제한다. 로그인이 필요하다. ("찾는 교재 n/10")
// 조건에 맞는 판매 중인 새 글이 올라오면 알림 화면(alerts.html)에 쌓이고 헤더 종 배지에 더해진다.
import { createAlert, deleteAlert, listAlerts } from "../api.js";
import { redirectToLogin, renderHeader } from "../auth.js";
import { t } from "../i18n.js";
import { getToken } from "../token.js";
import { clearFormErrors, el, formatPrice, showFormErrors, withContextMessage } from "../ui.js";

const alertForm = document.getElementById("alert-form");
const alertFormError = document.getElementById("alert-form-error");
const alertList = document.getElementById("alert-list");
const alertCount = document.getElementById("alert-count");

init();

async function init() {
  if (!getToken()) {
    redirectToLogin();
    return;
  }
  const me = await renderHeader(document.getElementById("site-header"));
  if (me === null) {
    if (!getToken()) redirectToLogin();
    else showFormErrors(alertForm, alertFormError, { message: t("err.network") });
    return;
  }
  alertForm.addEventListener("submit", onSubmitAlert);
  loadAlerts();
}

// 401(토큰 만료)이면 로그인 화면으로 보낸다. 처리했으면 true.
function handleAuthError(error) {
  if (error.status !== 401) return false;
  redirectToLogin();
  return true;
}

async function loadAlerts() {
  let data;
  try {
    data = await listAlerts();
  } catch (error) {
    if (handleAuthError(error)) return;
    showFormErrors(alertForm, alertFormError, error);
    return;
  }
  renderAlerts(data);
}

function renderAlerts({ items, max_count: maxCount }) {
  alertCount.textContent = `${items.length}/${maxCount}`;
  alertList.replaceChildren(...items.map(renderAlertItem));
}

function renderAlertItem(alert) {
  const priceText = alert.max_price === null ? t("alerts.price_any") : t("alerts.price_max", { price: formatPrice(alert.max_price) });
  // 등록하기 전에 이미 올라온 글은 알림이 오지 않으므로, 같은 조건의 검색 결과로 바로 볼 수 있게 한다.
  const query = new URLSearchParams({ q: alert.keyword });
  if (alert.max_price !== null) query.set("max_price", String(alert.max_price));

  const removeButton = el("button", { type: "button", className: "link-button link-button--danger", text: t("common.delete") });
  removeButton.addEventListener("click", () => onDeleteAlert(alert, removeButton));
  return el(
    "li",
    { className: "alert-list__item" },
    el(
      "div",
      { className: "alert-list__text" },
      el("span", { className: "alert-list__keyword", text: alert.keyword }),
      " ",
      el("span", { className: "alert-list__price", text: priceText }),
    ),
    el(
      "div",
      { className: "alert-list__actions" },
      el("a", { className: "link-button", href: `/static/index.html?${query}`, text: t("alerts.search_now") }),
      removeButton,
    ),
  );
}

async function onSubmitAlert(event) {
  event.preventDefault();
  clearFormErrors(alertForm, alertFormError);
  const { keyword, max_price: maxPrice } = alertForm.elements;
  const data = { keyword: keyword.value };
  if (maxPrice.value !== "") {
    const price = Number(maxPrice.value);
    if (!Number.isInteger(price) || price < 0) {
      showFormErrors(alertForm, alertFormError, { fieldErrors: { max_price: t("alerts.price_integer") } });
      return;
    }
    data.max_price = price;
  }

  const submit = alertForm.querySelector("[type=submit]");
  submit.disabled = true;
  try {
    await createAlert(data);
    alertForm.reset();
    keyword.focus();
  } catch (error) {
    if (handleAuthError(error)) return;
    // 409(같은 키워드)는 키워드 칸 아래에, 400(개수 초과)·403(정지)은 공통 영역에 보여준다.
    if (error.status === 409) {
      const { message, original } = withContextMessage(error, "alerts.duplicate");
      showFormErrors(alertForm, alertFormError, { fieldErrors: { keyword: message }, fieldOriginals: { keyword: original } });
    }
    else showFormErrors(alertForm, alertFormError, error);
    return;
  } finally {
    submit.disabled = false;
  }
  loadAlerts();
}

async function onDeleteAlert(alert, button) {
  button.disabled = true;
  try {
    await deleteAlert(alert.id);
  } catch (error) {
    if (handleAuthError(error)) return;
    // 이미 지워진 조건(404)이면 목록만 새로 맞춘다.
    if (error.status !== 404) {
      button.disabled = false;
      showFormErrors(alertForm, alertFormError, error);
      return;
    }
  }
  loadAlerts();
}
