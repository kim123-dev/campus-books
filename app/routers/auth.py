from typing import Annotated

from fastapi import APIRouter, Depends, Form, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import User
from app.schemas.user import LoginForm, TokenResponse, UserCreate, UserResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


# 라우터는 요청을 받아 서비스에 넘기고 응답 형식만 정한다. (로직은 auth_service)
@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="회원가입",
    responses={409: {"description": "이메일 또는 닉네임 중복"}},
)
def signup(data: UserCreate, db: Annotated[Session, Depends(get_db)]) -> User:
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
