"""정적 파일(static/) 제공: 파일 내용 해시로 만든 버전, 서비스 워커 파일, Cache-Control.

서비스 워커가 정적 파일을 캐시에서 먼저 꺼내 쓰므로(stale-while-revalidate), 캐시를 언제 새로 받을지는
sw.js에 들어간 버전 하나로 정한다. 버전을 손으로 올리면 빠뜨리기 쉬워, 서버가 시작할 때 static/ 파일 내용으로
직접 계산한다. 파일이 하나라도 바뀌면 버전이 바뀌고, 바뀌지 않으면 같은 버전이 나온다.
"""

import hashlib
import json
from pathlib import Path

from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

SERVICE_WORKER = "sw.js"
VERSION_PLACEHOLDER = '"__STATIC_VERSION__"'
PRECACHE_PLACEHOLDER = '"__PRECACHE__"'

# 서비스 워커가 설치될 때 미리 받아 두는 파일 종류. (라이선스 글 같은 화면에 쓰지 않는 파일은 뺀다)
PRECACHE_SUFFIXES = {".html", ".css", ".js", ".json", ".svg", ".png", ".woff2"}

# 이름에 해시가 없는 파일은 내용이 바뀌어도 주소가 같다. 그래서 화면 코드(HTML·CSS·JS·manifest)는
# 매번 서버에 바뀌었는지 묻게 하고(no-cache, 안 바뀌었으면 304), 속도는 서비스 워커 캐시가 맡는다.
# 오래 캐시하면 새 HTML과 옛 JS가 섞일 수 있다. 글꼴·그림은 거의 바뀌지 않고 섞여도 화면이 깨지지 않아 1주일 둔다.
NO_CACHE = "no-cache"
LONG_CACHE = "public, max-age=604800"
LONG_CACHE_DIRS = ("fonts/", "img/")


def _files(directory: Path) -> list[Path]:
    # 순서가 OS마다 달라지지 않게 경로 이름순으로 정렬한다.
    return sorted((path for path in directory.rglob("*") if path.is_file()), key=lambda p: p.relative_to(directory).as_posix())


def compute_version(directory: Path) -> str:
    """static/ 아래 모든 파일의 경로와 내용으로 만든 해시(앞 16자리).
    수정 시각은 쓰지 않는다. 배포 때마다 바뀌어 내용이 같아도 버전이 달라지기 때문이다.
    """
    digest = hashlib.sha256()
    for path in _files(directory):
        digest.update(path.relative_to(directory).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def precache_paths(directory: Path) -> list[str]:
    """서비스 워커가 미리 받을 주소 목록. 화면이 쓰는 모든 정적 파일이라, 처음 연 화면이 아니어도 바로 뜬다."""
    return [
        "/static/" + path.relative_to(directory).as_posix()
        for path in _files(directory)
        if path.suffix in PRECACHE_SUFFIXES and path.name != SERVICE_WORKER
    ]


def render_service_worker(directory: Path) -> str:
    """sw.js의 자리 표시값에 버전과 미리 받을 목록을 넣는다."""
    source = (directory / SERVICE_WORKER).read_text(encoding="utf-8")
    assert VERSION_PLACEHOLDER in source and PRECACHE_PLACEHOLDER in source, "sw.js의 자리 표시값이 없습니다."
    return source.replace(VERSION_PLACEHOLDER, json.dumps(compute_version(directory))).replace(
        PRECACHE_PLACEHOLDER, json.dumps(precache_paths(directory))
    )


def cache_control_for(path: str) -> str:
    """/static/ 아래 상대 경로에 맞는 Cache-Control 값."""
    return LONG_CACHE if path.startswith(LONG_CACHE_DIRS) else NO_CACHE


class StaticAssets(StaticFiles):
    """StaticFiles에 Cache-Control을 붙이고, sw.js는 서버 시작 때 버전을 넣어 만든 내용으로 준다."""

    def __init__(self, *, directory: Path, **kwargs) -> None:
        super().__init__(directory=directory, **kwargs)
        # 서버 시작 때 한 번만 계산한다. 배포하면 서버가 새로 시작하므로 그때 새 버전이 된다.
        self.service_worker = render_service_worker(directory)

    async def get_response(self, path: str, scope: Scope) -> Response:
        # Windows에서는 경로 구분자가 \로 들어오므로 /로 맞춘다.
        path = path.replace("\\", "/")
        if path == SERVICE_WORKER:
            # 브라우저가 화면을 열 때마다 이 파일이 바뀌었는지 확인해야 새 버전을 알아챈다.
            return Response(
                self.service_worker,
                media_type="application/javascript",
                headers={"Cache-Control": NO_CACHE},
            )
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            response.headers["Cache-Control"] = cache_control_for(path)
        return response
