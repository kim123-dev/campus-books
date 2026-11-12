// 목록 화면 <head>에서 바로 실행되는 작은 스크립트 (모듈이 아님: 화면을 그리기 전에 끝나야 한다).
// 저장된 토큰이 있으면 <html data-signed-in>을 붙여, CSS가 처음부터 배너를 얇은 한 줄 띠로 그리게 한다.
// 로그인 확인(API)을 기다렸다가 배너 모양을 바꾸면 그 사이에 목록이 덜컥 밀리기 때문이다.
// 토큰이 만료되었어도 얇은 띠로 보일 뿐이라 큰 문제가 없다. 키 이름은 token.js와 같아야 한다(tests/test_static.py가 확인).
try {
  if (localStorage.getItem("campus-books.token")) document.documentElement.setAttribute("data-signed-in", "");
} catch {
  // 사생활 보호 모드 등에서 localStorage가 막히면 로그인하지 않은 모양(큰 배너)으로 둔다.
}
