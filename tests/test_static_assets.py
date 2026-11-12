"""정적 파일 버전(내용 해시), 서비스 워커 파일, Cache-Control."""

import json
import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.static_assets import (
    LONG_CACHE,
    NO_CACHE,
    compute_version,
    precache_paths,
    render_service_worker,
)
from app.main import STATIC_DIR


@pytest.fixture
def static_copy(tmp_path: Path) -> Path:
    """실제 static/을 복사한 폴더. 파일을 바꿔 보며 버전을 확인한다."""
    target = tmp_path / "static"
    shutil.copytree(STATIC_DIR, target)
    return target


# ---------- 버전 ----------


def test_version_is_stable_when_nothing_changes(static_copy: Path) -> None:
    first = compute_version(static_copy)

    assert compute_version(static_copy) == first
    # 다른 폴더라도 내용이 같으면 같은 버전이다. (배포할 때마다 바뀌는 수정 시각은 쓰지 않음)
    assert compute_version(STATIC_DIR) == first
    js = static_copy / "js" / "api.js"
    js.touch()
    assert compute_version(static_copy) == first


@pytest.mark.parametrize(
    "change",
    [
        lambda root: (root / "js" / "api.js").write_text("// 바뀜\n" + (root / "js" / "api.js").read_text(encoding="utf-8"), encoding="utf-8"),
        lambda root: (root / "css" / "style.css").write_bytes((root / "css" / "style.css").read_bytes() + b"\n"),
        lambda root: (root / "img" / "new.svg").write_text("<svg/>", encoding="utf-8"),
        lambda root: (root / "blocks.html").unlink(),
        lambda root: (root / "blocks.html").rename(root / "blocks2.html"),
        lambda root: (root / "sw.js").write_text((root / "sw.js").read_text(encoding="utf-8") + "\n", encoding="utf-8"),
    ],
    ids=["edit-js", "edit-css", "add-file", "delete-file", "rename-file", "edit-sw"],
)
def test_version_changes_when_any_file_changes(static_copy: Path, change) -> None:
    before = compute_version(static_copy)
    change(static_copy)
    assert compute_version(static_copy) != before


# ---------- sw.js ----------


def test_rendered_service_worker_has_version_and_precache(static_copy: Path) -> None:
    source = render_service_worker(static_copy)

    assert "__STATIC_VERSION__" not in source and "__PRECACHE__" not in source
    assert f"const VERSION = {json.dumps(compute_version(static_copy))};" in source
    precache = json.loads(re.search(r"const PRECACHE = (\[.*?\]);", source).group(1))
    assert precache == precache_paths(static_copy)


def test_precache_covers_every_page_and_script() -> None:
    paths = set(precache_paths(STATIC_DIR))

    expected = {f"/static/{p.relative_to(STATIC_DIR).as_posix()}" for p in STATIC_DIR.rglob("*") if p.suffix in {".html", ".js", ".css"}}
    assert expected - {"/static/sw.js"} <= paths
    # 서비스 워커 자신과 화면에 쓰지 않는 파일(라이선스 글)은 미리 받지 않는다.
    assert "/static/sw.js" not in paths
    # 빈 화면 그림(webp)도 미리 받아 두어, 오프라인이나 첫 화면에서도 그림이 바로 뜬다.
    for name in ("empty-posts", "empty-wishlist", "empty-messages", "empty-search", "empty-alerts", "hero"):
        assert f"/static/img/{name}.webp" in paths
    assert not any(path.endswith(".txt") for path in paths)
    assert all(path.startswith("/static/") and (STATIC_DIR / path.removeprefix("/static/")).is_file() for path in paths)


def test_served_service_worker_matches_current_files(client: TestClient) -> None:
    response = client.get("/static/sw.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert response.headers["cache-control"] == NO_CACHE
    assert f"const VERSION = {json.dumps(compute_version(STATIC_DIR))};" in response.text


# ---------- Cache-Control ----------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/static/index.html", NO_CACHE),
        ("/static/post.html", NO_CACHE),
        ("/static/", NO_CACHE),
        ("/static/js/api.js", NO_CACHE),
        ("/static/js/pages/index.js", NO_CACHE),
        ("/static/css/style.css", NO_CACHE),
        ("/static/manifest.json", NO_CACHE),
        ("/static/fonts/Pretendard-Regular.subset.woff2", LONG_CACHE),
        ("/static/img/icon-192.png", LONG_CACHE),
    ],
)
def test_static_cache_control(client: TestClient, path: str, expected: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["cache-control"] == expected
    # 다시 물어봤을 때(304)도 같은 규칙을 알려준다.
    again = client.get(path, headers={"If-None-Match": response.headers["etag"]})
    assert again.status_code == 304
    assert again.headers["cache-control"] == expected


def test_api_and_missing_files_have_no_static_cache_rule(client: TestClient) -> None:
    # API 응답에는 정적 파일 규칙을 붙이지 않는다. (서비스 워커도 API는 캐시하지 않음)
    assert "cache-control" not in client.get("/posts").headers
    assert "cache-control" not in client.get("/health").headers
    assert "cache-control" not in client.get("/static/nothing.js").headers
