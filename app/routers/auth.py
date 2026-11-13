from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import User
from app.schemas.security_question import PasswordResetQuestionRequest, PasswordResetQuestionResponse
from app.schemas.user import LoginForm, PasswordResetRequest, TokenResponse, UserCreate, UserResponse
from app.services import auth_service, password_reset_service

router = APIRouter(prefix="/auth", tags=["auth"])


# 라우터는 요청을 받아 서비스에 넘기고 응답 형식만 정한다. (로직은 auth_service)
@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="회원가입 (본인 확인 질문과 답 함께)",
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


def _client_ip(request: Request) -> str:
    # 운영(Railway)에서는 프록시가 X-Forwarded-For를 실제 접속 주소로 덮어쓰고, uvicorn --proxy-headers가 그 값을 client로 넣는다.
    return request.client.host if request.client else "unknown"


# 재설정 1단계. 이메일이 서버 접속 기록(주소)에 남지 않게 POST 본문으로 받는다.
@router.post(
    "/password-reset/question",
    response_model=PasswordResetQuestionResponse,
    summary="비밀번호 재설정 1단계: 본인 확인 질문 받기",
    responses={429: {"description": "IP당 1시간 30회 초과 (질문 받기와 재설정 합산)"}},
)
def get_reset_question(
    data: PasswordResetQuestionRequest, request: Request, db: Annotated[Session, Depends(get_db)]
) -> PasswordResetQuestionResponse:
    question = password_reset_service.get_question(db, data.email, _client_ip(request))
    return PasswordResetQuestionResponse(question=question)


# 재설정 2단계. 성공하면 이 계정의 기존 토큰은 모두 무효가 된다.
@router.post(
    "/password-reset",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="비밀번호 재설정 2단계: 답과 새 비밀번호",
    responses={
        400: {"description": "이메일 또는 답 불일치 (가입 여부를 숨기려고 이유를 나누지 않음)"},
        429: {"description": "이메일당 24시간에 5번 틀려 잠김, IP당 1시간 30회 초과"},
    },
)
def reset_password(data: PasswordResetRequest, request: Request, db: Annotated[Session, Depends(get_db)]) -> None:
    password_reset_service.reset_with_answer(db, data, _client_ip(request))
