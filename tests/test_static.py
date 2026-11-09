import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import STATIC_DIR

JS_FILES = sorted(STATIC_DIR.rglob("*.js"))

# HTML 문자열을 해석해 DOM을 만드는 API. 사용자 입력이 섞이면 XSS가 되므로 프론트 전체에서 금지한다.
FORBIDDEN_DOM_APIS = re.compile(r"\b(innerHTML|outerHTML|insertAdjacentHTML)\b")


# ---------- 서빙 ----------


def test_root_redirects_to_index(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/static/index.html"


def test_index_html_is_served(client: TestClient) -> None:
    response = client.get("/static/index.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>" in response.text


@pytest.mark.parametrize("page", ["login.html", "signup.html"])
def test_auth_pages_are_served(client: TestClient, page: str) -> None:
    response = client.get(f"/static/{page}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<form" in response.text


def test_post_detail_page_is_served(client: TestClient) -> None:
    response = client.get("/static/post.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "/static/js/pages/post.js" in response.text


def test_post_form_page_is_served(client: TestClient) -> None:
    response = client.get("/static/post-form.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "/static/js/pages/post-form.js" in response.text


def test_my_posts_page_is_served(client: TestClient) -> None:
    response = client.get("/static/my-posts.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "/static/js/pages/my-posts.js" in response.text


@pytest.mark.parametrize(
    ("page", "script"),
    [("conversations.html", "conversations.js"), ("chat.html", "chat.js")],
)
def test_message_pages_are_served(client: TestClient, page: str, script: str) -> None:
    response = client.get(f"/static/{page}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert f"/static/js/pages/{script}" in response.text


def test_wishlist_page_is_served(client: TestClient) -> None:
    response = client.get("/static/wishlist.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "/static/js/pages/wishlist.js" in response.text


def test_header_links_to_wishlist() -> None:
    assert '"/static/wishlist.html"' in (STATIC_DIR / "js" / "auth.js").read_text(encoding="utf-8")


def test_admin_page_is_served(client: TestClient) -> None:
    response = client.get("/static/admin.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "/static/js/pages/admin.js" in response.text


def test_header_links_to_admin_only_for_admin() -> None:
    # "관리" 링크는 role이 ADMIN일 때만 만든다. (권한 검사 자체는 서버의 /admin API가 한다)
    auth_js = (STATIC_DIR / "js" / "auth.js").read_text(encoding="utf-8")
    assert '"/static/admin.html"' in auth_js
    assert 'me.role === "ADMIN"' in auth_js


def test_chat_page_has_privacy_notice(client: TestClient) -> None:
    # 쪽지로 전화번호·계좌번호를 주고받다 생기는 피해를 줄이기 위한 안내가 빠지지 않게 한다.
    assert "개인정보" in client.get("/static/chat.html").text


def test_root_redirect_ends_at_index(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert str(response.url).endswith("/static/index.html")


@pytest.mark.parametrize(
    ("path", "expected_type"),
    [("/static/js/api.js", "javascript"), ("/static/css/style.css", "text/css")],
)
def test_assets_have_correct_mime_type(client: TestClient, path: str, expected_type: str) -> None:
    # .js가 text/plain으로 오면 브라우저가 <script type="module">을 실행하지 않는다.
    response = client.get(path)

    assert response.status_code == 200
    assert expected_type in response.headers["content-type"]


def test_missing_static_file_returns_404(client: TestClient) -> None:
    assert client.get("/static/no-such-page.html").status_code == 404


def test_root_is_not_in_api_docs(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/" not in paths
    assert not any(path.startswith("/static") for path in paths)


def test_api_routes_still_work_next_to_static(client: TestClient) -> None:
    # static mount가 API 경로를 가리지 않는지 확인한다.
    assert client.get("/posts").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}


# ---------- XSS 방지 규칙 ----------


def test_static_js_files_exist() -> None:
    # 파일을 못 찾으면 아래 검사가 아무것도 확인하지 않고 통과하므로 먼저 확인한다.
    assert JS_FILES, f"{STATIC_DIR}에서 .js 파일을 찾지 못했습니다."


@pytest.mark.parametrize("js_file", JS_FILES, ids=lambda p: p.relative_to(STATIC_DIR).as_posix())
def test_js_does_not_use_html_string_apis(js_file: Path) -> None:
    source = js_file.read_text(encoding="utf-8")

    found = [
        f"{line_no}: {line.strip()}"
        for line_no, line in enumerate(source.splitlines(), start=1)
        if FORBIDDEN_DOM_APIS.search(line)
    ]
    assert not found, "textContent/createElement를 사용하세요:\n" + "\n".join(found)


def test_open_chat_link_opens_safely() -> None:
    # 새 탭으로 여는 외부 링크는 noopener noreferrer가 없으면 열린 페이지가 window.opener로
    # 이 탭을 다른 주소로 바꿀 수 있다(reverse tabnabbing). 오픈채팅 버튼이 이 속성을 갖는지 확인한다.
    source = (STATIC_DIR / "js" / "pages" / "post.js").read_text(encoding="utf-8")
    link = re.search(r'el\("a", \{[^}]*href: url,[^}]*\}\)', source, re.S)

    assert link, "post.js에서 오픈채팅 링크(el(\"a\", { href: url, ... }))를 찾지 못했습니다."
    assert 'target: "_blank"' in link.group(0)
    assert 'rel: "noopener noreferrer"' in link.group(0)


def test_open_chat_prefix_matches_server() -> None:
    # 화면의 2차 검사 접두사가 서버 규칙과 어긋나면, 정상 링크가 화면에 안 보이게 된다.
    from app.schemas.post import OPEN_CHAT_URL_PATTERN

    source = (STATIC_DIR / "js" / "pages" / "post.js").read_text(encoding="utf-8")
    prefix = re.search(r'const OPEN_CHAT_PREFIX = "([^"]+)";', source)

    assert prefix, "post.js에서 OPEN_CHAT_PREFIX를 찾지 못했습니다."
    assert OPEN_CHAT_URL_PATTERN.pattern.startswith(re.escape(prefix.group(1)))


# ---------- 프론트와 서버의 상태 규칙 일치 ----------

POST_JS = STATIC_DIR / "js" / "pages" / "post.js"


def _read_front_transitions() -> dict[str, set[str]]:
    """post.js의 ALLOWED_TRANSITIONS 상수를 읽어 {현재 상태: 바꿀 수 있는 상태들}로 돌려준다."""
    source = POST_JS.read_text(encoding="utf-8")
    block = re.search(r"const ALLOWED_TRANSITIONS = \{(.*?)\};", source, re.S)
    # 상수 이름이나 모양이 바뀌면 비교 없이 통과하지 않도록 여기서 실패시킨다.
    assert block, "post.js에서 `const ALLOWED_TRANSITIONS = { ... };`를 찾지 못했습니다."
    rows = re.findall(r"(\w+):\s*\[(.*?)\]", block.group(1), re.S)
    assert rows, "ALLOWED_TRANSITIONS에서 상태 항목을 읽지 못했습니다."
    return {state: set(re.findall(r'"(\w+)"', targets)) for state, targets in rows}


def test_front_status_transitions_match_server() -> None:
    # 상세 화면은 이 표로 상태 변경 버튼을 고른다. 서버 규칙이 바뀌었는데 프론트를 놓치면
    # 누를 수 없는 버튼이 보이거나(400) 필요한 버튼이 사라지므로, 두 표가 같은지 확인한다.
    from app.services.post_service import ALLOWED_TRANSITIONS

    server = {
        state.value: {target.value for target in targets}
        for state, targets in ALLOWED_TRANSITIONS.items()
    }

    assert _read_front_transitions() == server


# ---------- 사진 ----------

POST_FORM_JS = STATIC_DIR / "js" / "pages" / "post-form.js"


def test_placeholder_image_is_served(client: TestClient) -> None:
    response = client.get("/static/img/book-placeholder.svg")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")


def test_post_form_has_photo_input_limited_to_allowed_types(client: TestClient) -> None:
    html = client.get("/static/post-form.html").text

    assert 'type="file"' in html
    assert 'accept="image/jpeg,image/png,image/webp"' in html


def test_front_photo_limits_match_server() -> None:
    # 화면의 미리 검사(장수·크기)가 서버 규칙과 어긋나면 화면은 통과시키고 서버가 거절하는 일이 생긴다.
    from app.models import MAX_IMAGES_PER_POST
    from app.services.image_service import MAX_IMAGE_BYTES

    source = POST_FORM_JS.read_text(encoding="utf-8")
    photos = re.search(r"const MAX_PHOTOS = (\d+);", source)
    size = re.search(r"const MAX_PHOTO_BYTES = (\d+) \* 1024 \* 1024;", source)
    assert photos and size, "post-form.js에서 MAX_PHOTOS / MAX_PHOTO_BYTES를 찾지 못했습니다."

    assert int(photos.group(1)) == MAX_IMAGES_PER_POST
    assert int(size.group(1)) * 1024 * 1024 == MAX_IMAGE_BYTES


# ---------- 신고·차단 ----------

SAFETY_JS = STATIC_DIR / "js" / "safety.js"


def test_blocks_page_is_served(client: TestClient) -> None:
    response = client.get("/static/blocks.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "/static/js/pages/blocks.js" in response.text


def test_my_posts_links_to_blocks(client: TestClient) -> None:
    # 차단 완료 안내가 "내 글 화면에서 확인·해제"라고 알려주므로 그 화면에 링크가 있어야 한다.
    assert 'href="/static/blocks.html"' in client.get("/static/my-posts.html").text


def test_front_report_rules_match_server() -> None:
    # 신고 창의 사유 목록·글자 수가 서버와 어긋나면 고를 수 있는 사유를 서버가 422로 거절한다.
    from app.models import ReportReason
    from app.schemas.report import MAX_REPORT_DESCRIPTION_LENGTH

    source = SAFETY_JS.read_text(encoding="utf-8")
    reasons = re.findall(r'\["(\w+)", "[^"]+"\]', source)
    length = re.search(r"const MAX_DESCRIPTION = (\d+);", source)
    assert reasons and length, "safety.js에서 REPORT_REASONS / MAX_DESCRIPTION을 찾지 못했습니다."

    assert reasons == [reason.value for reason in ReportReason]
    assert int(length.group(1)) == MAX_REPORT_DESCRIPTION_LENGTH


# ---------- 모바일 화면 ----------

STYLE_CSS = STATIC_DIR / "css" / "style.css"
UI_JS = STATIC_DIR / "js" / "ui.js"
HTML_FILES = sorted(STATIC_DIR.glob("*.html"))
# 화면 아래를 따로 쓰는 화면(상세의 연락 바, 대화 입력창, 긴 글쓰기 폼)과 로그인·회원가입은 탭 바를 끈다.
NO_TAB_BAR_PAGES = {"post.html", "chat.html", "post-form.html", "login.html", "signup.html"}


def test_mobile_breakpoint_matches_between_js_and_css() -> None:
    # JS(matchMedia)와 CSS가 다른 폭을 기준으로 하면, 그 사이 폭에서 화면과 동작이 어긋난다.
    css = STYLE_CSS.read_text(encoding="utf-8")
    query = re.search(r'export const MOBILE_QUERY = "\(max-width: ([\d.]+)px\)";', UI_JS.read_text(encoding="utf-8"))
    assert query, "ui.js에서 MOBILE_QUERY를 찾지 못했습니다."

    mobile_max = float(query.group(1))
    assert f"@media (max-width: {query.group(1)}px)" in css
    # PC 쪽 기준(mobile-only를 숨기는 폭)이 모바일 기준 바로 다음 픽셀이어야 빈틈·겹침이 없다.
    pc_min = re.search(r"@media \(min-width: (\d+)px\) \{\s*\.mobile-only", css)
    assert pc_min and int(pc_min.group(1)) == round(mobile_max + 0.02)


@pytest.mark.parametrize("html", HTML_FILES, ids=lambda path: path.name)
def test_pages_allow_safe_area(html: Path) -> None:
    # iPhone 아래쪽 홈 막대 영역(env(safe-area-inset-bottom))을 쓰려면 viewport-fit=cover가 필요하다.
    assert 'content="width=device-width, initial-scale=1, viewport-fit=cover' in html.read_text(encoding="utf-8")


@pytest.mark.parametrize("html", HTML_FILES, ids=lambda path: path.name)
def test_tab_bar_is_off_only_on_expected_pages(html: Path) -> None:
    has_off = 'data-tab-bar="off"' in html.read_text(encoding="utf-8")
    assert has_off == (html.name in NO_TAB_BAR_PAGES)


def test_tab_bar_links_to_main_pages() -> None:
    source = (STATIC_DIR / "js" / "auth.js").read_text(encoding="utf-8")
    tabs = re.search(r"const TABS = \[(.*?)\n\];", source, re.S)
    assert tabs, "auth.js에서 TABS를 찾지 못했습니다."

    labels = re.findall(r'label: "([^"]+)"', tabs.group(1))
    assert labels == ["홈", "찜", "글쓰기", "쪽지", "내 정보"]
    for page in ["HOME_PAGE", "WISHLIST_PAGE", "POST_FORM_PAGE", "CONVERSATIONS_PAGE", "MY_POSTS_PAGE"]:
        assert f"href: {page}" in tabs.group(1)


def test_mobile_inputs_are_at_least_16px() -> None:
    # iOS Safari는 16px보다 작은 입력칸에 포커스하면 화면을 확대한다.
    css = STYLE_CSS.read_text(encoding="utf-8")
    mobile = css.split("@media (max-width: 767.98px) {", 1)[1]
    assert re.search(r"input,\s*select,\s*textarea \{\s*font-size: max\(16px, 1em\);", mobile)


def test_js_uses_shared_mobile_query() -> None:
    # 화면별 JS가 폭을 직접 적으면 CSS 기준과 어긋날 수 있으므로, ui.js의 MOBILE_QUERY만 쓴다.
    for path in (STATIC_DIR / "js").rglob("*.js"):
        if path.name == "ui.js":
            continue
        assert "max-width" not in path.read_text(encoding="utf-8"), path.name


def test_chat_page_resizes_with_keyboard() -> None:
    # 안드로이드 Chrome이 키보드 높이만큼 화면(dvh)을 줄이게 한다. iOS는 chat.js가 visualViewport로 맞춘다.
    html = (STATIC_DIR / "chat.html").read_text(encoding="utf-8")
    assert "interactive-widget=resizes-content" in html
    source = (STATIC_DIR / "js" / "pages" / "chat.js").read_text(encoding="utf-8")
    assert "visualViewport" in source and "--chat-viewport-height" in source
    css = STYLE_CSS.read_text(encoding="utf-8").split("@media (max-width: 767.98px) {", 1)[1]
    assert "var(--chat-viewport-height, 100dvh)" in css


def test_send_button_keeps_textarea_focus() -> None:
    # 보내기 버튼이 포커스를 가져가면 모바일 키보드가 내려갔다 다시 올라온다.
    source = (STATIC_DIR / "js" / "pages" / "chat.js").read_text(encoding="utf-8")
    assert re.search(r'submitButton\.addEventListener\("pointerdown", keepTextareaFocus\)', source)
    assert re.search(r'submitButton\.addEventListener\("mousedown", keepTextareaFocus\)', source)


def test_gallery_is_swipeable_only_on_mobile() -> None:
    # PC는 작은 사진 버튼으로만 넘기고(스크롤 막음), 모바일만 손가락으로 넘긴다.
    css = STYLE_CSS.read_text(encoding="utf-8")
    base, mobile = css.split("@media (max-width: 767.98px) {", 1)
    assert re.search(r"\.gallery__track \{[^}]*overflow-x: hidden;[^}]*scroll-snap-type: x mandatory;", base)
    assert re.search(r"\.gallery__track \{\s*overflow-x: auto;", mobile)
    assert re.search(r"\.gallery__main \{[^}]*scroll-snap-align: start;", base)


# ---------- 홈 화면 앱 (PWA) ----------

MANIFEST = STATIC_DIR / "manifest.json"
SW_JS = STATIC_DIR / "sw.js"


def png_size(path: Path) -> tuple[int, int]:
    # PNG 파일 머리(IHDR)의 가로·세로. 이미지 라이브러리 없이 크기만 확인한다.
    data = path.read_bytes()[:24]
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path.name
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def test_manifest_describes_installable_app(client: TestClient) -> None:
    response = client.get("/static/manifest.json")
    assert response.status_code == 200
    manifest = response.json()

    assert manifest["name"] == "Campus Books"
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/static/index.html"
    assert manifest["start_url"].startswith(manifest["scope"])
    # 테마색은 화면의 포인트 색과 같아야 상태 표시줄과 화면 색이 어긋나지 않는다.
    primary = re.search(r"--color-primary: (#[0-9a-f]{6});", STYLE_CSS.read_text(encoding="utf-8"))
    assert primary and manifest["theme_color"] == primary.group(1)

    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes
    for icon in manifest["icons"]:
        width, height = map(int, icon["sizes"].split("x"))
        assert png_size(STATIC_DIR / icon["src"].removeprefix("/static/")) == (width, height)
        assert client.get(icon["src"]).headers["content-type"] == "image/png"


def test_apple_touch_icon_is_180px() -> None:
    assert png_size(STATIC_DIR / "img" / "apple-touch-icon.png") == (180, 180)


@pytest.mark.parametrize("html", HTML_FILES, ids=lambda path: path.name)
def test_pages_link_manifest_and_apple_meta(html: Path) -> None:
    text = html.read_text(encoding="utf-8")
    assert '<link rel="manifest" href="/static/manifest.json" />' in text
    assert '<link rel="apple-touch-icon" href="/static/img/apple-touch-icon.png" />' in text
    assert '<meta name="apple-mobile-web-app-capable" content="yes" />' in text
    assert '<meta name="apple-mobile-web-app-title" content="Campus Books" />' in text
    assert '<meta name="theme-color" content="#5b3fd6" />' in text
    # 어느 화면으로 먼저 들어와도 서비스 워커가 등록되게 모든 화면이 불러온다.
    assert '<script type="module" src="/static/js/pwa.js"></script>' in text


def test_service_worker_is_served_as_javascript(client: TestClient) -> None:
    response = client.get("/static/sw.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_service_worker_caches_only_static_files() -> None:
    source = SW_JS.read_text(encoding="utf-8")
    # /static/ 밖(API·/images)과 다른 사이트 요청은 손대지 않고 돌려보낸다.
    assert re.search(r'url\.origin !== self\.location\.origin \|\| !url\.pathname\.startsWith\("/static/"\)', source)
    assert 'request.method !== "GET"' in source
    # 미리 받는 목록도 정적 파일뿐이다.
    precache = re.search(r"const PRECACHE = \[(.*?)\];", source, re.S)
    assert precache
    paths = re.findall(r'"([^"]+)"', precache.group(1))
    assert paths and all(path.startswith("/static/") for path in paths)
    for path in paths:
        assert (STATIC_DIR / path.removeprefix("/static/")).is_file(), path


def test_service_worker_cache_has_version_key() -> None:
    # 배포 때 VERSION을 바꾸면 새 캐시를 만들고 이전 버전 캐시를 지운다.
    source = SW_JS.read_text(encoding="utf-8")
    assert re.search(r'const VERSION = "[^"]+";', source)
    assert "const CACHE_NAME = `${CACHE_PREFIX}${VERSION}`;" in source
    assert "name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME" in source


def test_install_guide_is_dismissable_and_skips_standalone() -> None:
    source = (STATIC_DIR / "js" / "pwa.js").read_text(encoding="utf-8")
    assert "if (!isIosSafari() || isStandalone() || readDismissed()) return;" in source
    assert "(display-mode: standalone)" in source and "navigator.standalone" in source
    assert 'export const INSTALL_GUIDE_KEY = "campus-books.install-guide-dismissed";' in source
