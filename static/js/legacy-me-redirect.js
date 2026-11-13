// 예전 "내 글"(my-posts.html)·"찜"(wishlist.html) 주소로 들어온 사람을 내 정보 화면의 해당 탭으로 보낸다.
// 즐겨찾기나 홈 화면 앱, 서비스 워커에 남은 옛 링크가 깨지지 않도록 파일을 지우지 않고 이동용으로 남겼다.
// 모듈이 아닌 일반 스크립트라 <head>에서 화면을 그리기 전에 바로 옮긴다. ?page= 값은 그대로 넘긴다.
(() => {
  const tab = document.currentScript?.dataset.tab === "wishlist" ? "wishlist" : "posts";
  const params = new URLSearchParams({ tab });
  const page = new URLSearchParams(window.location.search).get("page");
  if (page !== null) params.set("page", page);
  // replace: 뒤로 가기를 눌렀을 때 이동용 화면으로 돌아와 다시 튕기지 않게 한다.
  window.location.replace(`/static/me.html?${params}`);
})();
