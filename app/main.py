import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import app.models  # noqa: F401  모델을 등록해야 create_all이 테이블을 만든다.
from app.core.database import Base, engine
from app.core.exceptions import (
    AuthenticationError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.routers import auth, posts, users

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


app = FastAPI(
    title="Campus Books",
    description="캠퍼스 중고 교재 거래 게시판 API",
    lifespan=lifespan,
)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)

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
