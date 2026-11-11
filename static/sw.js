// 서비스 워커: 홈 화면에 추가한 앱(PWA)이 빨리 뜨고, 연결이 끊겨도 한 번 본 화면의 틀은 열리게 한다.
// - 캐시하는 것: /static/ 아래 정적 파일(HTML·CSS·JS·글꼴·아이콘)뿐이다.
// - 캐시하지 않는 것: API 응답(/posts, /conversations, /users 등)과 사진(/images). 글·쪽지·찜은 늘 최신이어야 하고,
//   로그인한 사용자의 데이터가 기기 캐시에 남지 않게 하기 위해서다. /static/ 밖의 요청은 아예 건드리지 않는다.
// - 새 버전을 배포할 때 VERSION을 바꾸면, 새 서비스 워커가 켜지면서 이전 버전 캐시를 모두 지운다.
//   (브라우저는 이 파일이 한 글자라도 바뀌면 새 서비스 워커로 보고 다시 설치한다)

const VERSION = "2026-11-11.3";
const CACHE_PREFIX = "campus-books-static-";
const CACHE_NAME = `${CACHE_PREFIX}${VERSION}`;

// 설치할 때 미리 받아 두는 앱의 기본 틀. 나머지 화면·스크립트는 처음 열 때 캐시에 담긴다.
const PRECACHE = [
  "/static/index.html",
  "/static/css/style.css",
  "/static/manifest.json",
  "/static/img/icon.svg",
  "/static/img/icon-192.png",
  "/static/img/apple-touch-icon.png",
  "/static/img/book-placeholder.svg",
];

// 글꼴·그림은 거의 바뀌지 않고 크기가 커서 캐시를 먼저 쓴다. 바뀌면 VERSION을 올려 새로 받는다.
const CACHE_FIRST = /^\/static\/(fonts|img)\//;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE))
      // 새 버전을 기다리게 하지 않고 바로 켠다. 화면 코드는 아래처럼 네트워크를 먼저 쓰므로 옛 코드와 섞이지 않는다.
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

  if (CACHE_FIRST.test(url.pathname)) {
    event.respondWith(cacheFirst(request));
  } else {
    event.respondWith(networkFirst(request, url));
  }
});

/** HTML·CSS·JS: 늘 최신 코드를 쓰도록 네트워크를 먼저 쓰고, 연결이 안 될 때만 캐시를 쓴다. */
async function networkFirst(request, url) {
  const cache = await caches.open(CACHE_NAME);
  // 화면 주소의 ?id=3 같은 값은 화면 코드가 읽는 것이라, 같은 HTML을 주소마다 따로 담지 않게 경로만 키로 쓴다.
  const key = request.mode === "navigate" ? url.pathname : request;
  try {
    const response = await fetch(request);
    if (response.ok && response.type === "basic") cache.put(key, response.clone());
    return response;
  } catch (error) {
    const cached = await cache.match(key, { ignoreSearch: true });
    if (cached) return cached;
    throw error;
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok && response.type === "basic") cache.put(request, response.clone());
  return response;
}
