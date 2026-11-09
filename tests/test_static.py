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
