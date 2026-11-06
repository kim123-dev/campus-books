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
