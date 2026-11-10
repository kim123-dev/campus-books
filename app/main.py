import mimetypes
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

import app.models  # noqa: F401  모델을 등록해야 create_all이 테이블을 만든다.
from app.core.config import get_settings
from app.core.database import Base, engine
from app.core.exceptions import (
    AuthenticationError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    ImageTooLargeError,
    NotFoundError,
    PayloadTooLargeError,
    TooManyRequestsError,
    UnprocessableError,
)
from app.routers import (
    admin,
    alerts,
    auth,
    blocks,
    conversations,
    images,
    posts,
    reports,
    users,
    wishlist,
)
from app.services.image_service import MAX_IMAGE_BYTES

# 실행 위치와 상관없이 프로젝트 루트의 static/ 폴더를 가리키도록 이 파일 기준으로 잡는다.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Windows는 레지스트리 설정에 따라 .js를 text/plain으로 알려주는 경우가 있다.
# 그러면 브라우저가 ES 모듈 실행을 거부하므로 MIME 타입을 직접 지정한다.
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")


# MVP에서는 마이그레이션 도구 없이 서버 시작 시 없는 테이블만 생성한다.
@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    yield


def api_docs_urls(is_production: bool) -> dict[str, str | None]:
    """운영에서는 API 문서(/docs, /redoc, /openapi.json)를 끈다. 누구나 전체 API 구조를 훑어보지 못하게 하기 위해서다."""
    if is_production:
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}


app = FastAPI(
    title="Campus Books",
    description="캠퍼스 중고 교재 거래 게시판 API",
    lifespan=lifespan,
    **api_docs_urls(get_settings().is_production),
)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)
app.include_router(conversations.router)
app.include_router(images.router)
app.include_router(wishlist.router)
app.include_router(blocks.router)
app.include_router(reports.router)
app.include_router(admin.router)
app.include_router(alerts.router)

# multipart 본문에는 파일 말고도 경계 문자열·헤더가 붙으므로 그만큼 여유를 둔다.
MAX_UPLOAD_REQUEST_BYTES = MAX_IMAGE_BYTES + 64 * 1024


# 사진 크기 제한(5MB)은 서비스가 읽으면서 다시 확인한다. 여기서는 Content-Length만 보고
# 너무 큰 요청을 본문을 받기 전에 바로 413으로 돌려보낸다. (임시 파일에 수십 MB를 쓰지 않도록)
@app.middleware("http")
async def reject_large_upload(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if request.method == "POST" and request.url.path.endswith("/images"):
        length = request.headers.get("content-length")
        if length is not None and length.isdigit() and int(length) > MAX_UPLOAD_REQUEST_BYTES:
            return JSONResponse(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                content={"detail": ImageTooLargeError().message},
            )
    return await call_next(request)

# 프론트 화면은 API와 같은 서버(같은 출처)에서 제공해 CORS 설정 없이 API를 호출한다.
# API 경로와 섞이지 않도록 /static 아래에만 둔다.
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")


# 주소창에 서버 주소만 입력해도 목록 화면이 열리게 한다. API 문서에는 노출하지 않는다.
@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/static/index.html")


# 서비스의 업무 예외를 HTTP 응답으로 바꾸는 곳을 한 군데로 모은다.
# 응답 형식은 FastAPI 기본 에러와 같은 {"detail": ...}로 맞춘다.
@app.exception_handler(ConflictError)
async def conflict_error_handler(_: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": exc.message})


@app.exception_handler(NotFoundError)
async def not_found_error_handler(_: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": exc.message})


@app.exception_handler(ForbiddenError)
async def forbidden_error_handler(_: Request, exc: ForbiddenError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": exc.message})


@app.exception_handler(BadRequestError)
async def bad_request_error_handler(_: Request, exc: BadRequestError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": exc.message})


@app.exception_handler(PayloadTooLargeError)
async def payload_too_large_error_handler(_: Request, exc: PayloadTooLargeError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_413_CONTENT_TOO_LARGE, content={"detail": exc.message})


# Pydantic 검증 실패(422)와 같은 상태 코드지만, 사람이 읽을 메시지 하나만 담는다.
@app.exception_handler(UnprocessableError)
async def unprocessable_error_handler(_: Request, exc: UnprocessableError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": exc.message}
    )


# 429 응답에는 언제 다시 시도하면 되는지 알려주는 Retry-After 헤더(초)를 함께 보낸다.
@app.exception_handler(TooManyRequestsError)
async def too_many_requests_error_handler(_: Request, exc: TooManyRequestsError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": exc.message},
        headers={"Retry-After": str(exc.retry_after)},
    )


# 401 응답에는 어떤 방식으로 인증해야 하는지 알려주는 WWW-Authenticate 헤더가 표준이다.
@app.exception_handler(AuthenticationError)
async def authentication_error_handler(_: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": exc.message},
        headers={"WWW-Authenticate": "Bearer"},
    )


# 배포/모니터링 시 서버가 살아있는지 DB 없이 빠르게 확인하기 위한 엔드포인트
@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
