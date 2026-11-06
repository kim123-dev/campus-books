from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

import app.models  # noqa: F401  모델을 등록해야 create_all이 테이블을 만든다.
from app.core.database import Base, engine
from app.core.exceptions import AuthenticationError, ConflictError
from app.routers import auth


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


# 서비스의 업무 예외를 HTTP 응답으로 바꾸는 곳을 한 군데로 모은다.
# 응답 형식은 FastAPI 기본 에러와 같은 {"detail": ...}로 맞춘다.
@app.exception_handler(ConflictError)
async def conflict_error_handler(_: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": exc.message})


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
