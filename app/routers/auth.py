from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.user import (
    LoginForm,
    PasswordResetRequest,
    PasswordResetResponse,
    SignupResponse,
    TokenResponse,
    UserCreate,
)
from app.services import auth_service, recovery_service

router = APIRouter(prefix="/auth", tags=["auth"])


# 라우터는 요청을 받아 서비스에 넘기고 응답 형식만 정한다. (로직은 auth_service)
@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="회원가입 (복구 코드를 한 번만 보여줌)",
    responses={409: {"description": "이메일 또는 닉네임 중복"}},
)
def signup(data: UserCreate, db: Annotated[Session, Depends(get_db)]) -> SignupResponse:
    return auth_service.signup(db, data)


# Swagger Authorize 버튼과 호환되도록 OAuth2 규격대로 form으로 받는다.
@router.post(
    "/login",
    response_model=TokenResponse,
    summary="로그인 (액세스 토큰 발급)",
    responses={401: {"description": "이메일 또는 비밀번호 불일치"}},
)
def login(
    data: Annotated[LoginForm, Form()], db: Annotated[Session, Depends(get_db)]
) -> TokenResponse:
    return TokenResponse(access_token=auth_service.login(db, data))


# 로그인하지 않은 상태에서 쓴다. 이메일만으로는 바꿀 수 없고 가입 때 받은 복구 코드가 있어야 한다.
@router.post(
    "/password-reset",
    response_model=PasswordResetResponse,
    summary="복구 코드로 비밀번호 재설정 (새 복구 코드 발급)",
    responses={
        400: {"description": "이메일 또는 복구 코드 불일치 (가입 여부를 숨기려고 이유를 나누지 않음)"},
        429: {"description": "이메일당 1시간 5회, IP당 1시간 30회 초과"},
    },
)
def reset_password(
    data: PasswordResetRequest, request: Request, db: Annotated[Session, Depends(get_db)]
) -> PasswordResetResponse:
    # 운영(Railway)에서는 프록시가 X-Forwarded-For를 실제 접속 주소로 덮어쓰고, uvicorn --proxy-headers가 그 값을 client로 넣는다.
    ip = request.client.host if request.client else "unknown"
    return PasswordResetResponse(recovery_code=recovery_service.reset_password(db, data, ip))
