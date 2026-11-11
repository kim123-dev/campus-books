// 서비스 워커: 정적 파일을 캐시에서 먼저 꺼내 화면을 바로 띄우고, 새 버전은 뒤에서 받아 다음 화면부터 쓴다.
// - 캐시하는 것: /static/ 아래 정적 파일(HTML·CSS·JS·글꼴·아이콘)뿐이다.
// - 캐시하지 않는 것: API 응답(/posts, /conversations, /users 등)과 사진(/images). 글·쪽지·찜은 늘 최신이어야 하고,
//   로그인한 사용자의 데이터가 기기 캐시에 남지 않게 하기 위해서다. /static/ 밖의 요청은 아예 건드리지 않는다.
//   정적 파일은 누가 보든 같은 내용이라(사용자 정보는 화면이 API로 받아 그린다) 계정을 바꿔도 남의 화면이 나오지 않는다.
// - 버전: 서버가 시작할 때 static/ 파일 내용으로 만든 해시를 아래 VERSION 자리에 넣어 보낸다(app/core/static_assets.py).
//   파일이 하나라도 바뀌면 이 파일 내용도 바뀌므로, 브라우저가 화면을 열 때마다 하는 sw.js 확인에서 새 버전을 알아챈다.
// - 갱신 순서 (stale-while-revalidate를 버전 단위로): 배포 뒤 첫 방문은 옛 캐시로 바로 뜨고, 그동안 새 서비스 워커가
//   모든 파일을 새 캐시에 한꺼번에 받는다. 다 받으면 바로 켜져 옛 캐시를 지우고, 다음 화면부터 새 버전이 나온다.
//   파일마다 따로 갱신하지 않는 이유: 새 HTML과 옛 JS가 섞이지 않게 하기 위해서다.

const VERSION = "__STATIC_VERSION__";
const CACHE_PREFIX = "campus-books-static-";
const CACHE_NAME = `${CACHE_PREFIX}${VERSION}`;

// 설치할 때 미리 받아 두는 파일. 서버가 static/의 화면용 파일 전체로 채운다.
const PRECACHE = "__PRECACHE__";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      // 브라우저 HTTP 캐시에 남은 옛 파일을 담지 않도록 서버에 꼭 확인하고 받는다(바뀌지 않았으면 304라 가볍다).
      // 하나라도 실패하면 설치가 취소되고 옛 버전을 계속 쓰다가, 다음 화면을 열 때 다시 시도한다.
      .then((cache) => cache.addAll(PRECACHE.map((path) => new Request(path, { cache: "no-cache" }))))
      // 기다리지 않고 바로 켠다. 모든 파일을 이미 새 캐시에 받아 둔 뒤라 다음 화면은 처음부터 끝까지 새 버전이다.
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names.filter((name) => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME).map((name) => caches.delete(name)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  // 다른 사이트, API, /images, 서비스 워커 파일 자신은 브라우저 기본 동작(네트워크) 그대로 둔다.
  if (url.origin !== self.location.origin || !url.pathname.startsWith("/static/") || url.pathname === "/static/sw.js") {
    return;
  }
  event.respondWith(cacheFirst(request, url));
});

/** 캐시에 있으면 바로 돌려주고, 없으면(목록에 없는 파일) 네트워크에서 받아 담는다. */
async function cacheFirst(request, url) {
  const cache = await caches.open(CACHE_NAME);
  // 화면 주소의 ?id=3 같은 값은 화면 코드가 읽는 것이라, 같은 HTML을 주소마다 따로 담지 않게 경로만 키로 쓴다.
  const key = url.pathname;
  const cached = await cache.match(key);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok && response.type === "basic" && !response.redirected) cache.put(key, response.clone());
  return response;
}
