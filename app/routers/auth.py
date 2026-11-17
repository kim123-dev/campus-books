from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response, status
from sqlalchemy.orm import Session

from app.core.client_ip import client_ip
from app.core.database import get_db
from app.models import User
from app.schemas.security_question import (
    PRESET_QUESTIONS,
    PasswordResetQuestionRequest,
    PasswordResetQuestionResponse,
    PasswordResetVerifyResponse,
    SecurityQuestionItem,
    SecurityQuestionListResponse,
)
from app.schemas.user import (
    AppLoginForm,
    LoginForm,
    PasswordResetRequest,
    PasswordResetVerifyRequest,
    RefreshRequest,
    TokenPairResponse,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from app.services import auth_service, password_reset_service, token_service

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
    responses={
        401: {"description": "이메일 또는 비밀번호 불일치"},
        429: {"description": "이메일당 10분 실패 10번 또는 IP당 10분 100번 초과 (앱 로그인과 합산)"},
    },
)
def login(
    data: Annotated[LoginForm, Form()], request: Request, db: Annotated[Session, Depends(get_db)]
) -> TokenResponse:
    return TokenResponse(access_token=auth_service.login(db, data, client_ip(request)))


# ---------- 앱(안드로이드) 로그인 유지 ----------
# 웹은 위의 /auth/login만 쓴다. 앱은 액세스 토큰(60분)이 만료되면 갱신 토큰으로 새로 받는다.
# 로그인 실패 횟수 제한(이메일당 10분 10번, IP당 10분 100번)은 /auth/login과 함께 센다. (login_rate_limit)


@router.post(
    "/token",
    response_model=TokenPairResponse,
    summary="앱 로그인 (액세스 토큰 + 갱신 토큰)",
    responses={
        401: {"description": "이메일 또는 비밀번호 불일치"},
        403: {"description": "이용 정지 중"},
        429: {"description": "이메일당 10분 실패 10번 또는 IP당 10분 100번 초과 (웹 로그인과 합산)"},
    },
)
def app_login(
    data: Annotated[AppLoginForm, Form()], request: Request, db: Annotated[Session, Depends(get_db)]
) -> TokenPairResponse:
    return token_service.login(db, data, client_ip(request))


@router.post(
    "/refresh",
    response_model=TokenPairResponse,
    summary="토큰 갱신 (갱신 토큰은 쓸 때마다 새 값으로 바뀜)",
    responses={
        401: {
            "description": "없는·만료·폐기된 갱신 토큰, 재사용(그 사용자의 갱신 토큰 모두 폐기), "
            "비밀번호 변경·탈퇴, 이용 정지 중"
        }
    },
)
def refresh_token(data: RefreshRequest, db: Annotated[Session, Depends(get_db)]) -> TokenPairResponse:
    return token_service.refresh(db, data.refresh_token)


# 갱신 토큰 자체가 자격 증명이라 액세스 토큰 없이 부른다. (액세스 토큰이 만료된 뒤에도 로그아웃할 수 있게)
@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="앱 로그아웃 (이 기기의 갱신 토큰 폐기, 여러 번 불러도 204)",
)
def app_logout(data: RefreshRequest, db: Annotated[Session, Depends(get_db)]) -> Response:
    token_service.logout(db, data.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# 가입 화면의 질문 목록. 웹은 화면에 같은 목록을 갖고 있고, 앱은 이 API로 받는다. (질문 문구는 한국어 원문)
@router.get(
    "/security-questions",
    response_model=SecurityQuestionListResponse,
    summary="본인 확인 질문 목록 (가입용, 로그인 불필요)",
)
def list_security_questions() -> SecurityQuestionListResponse:
    return SecurityQuestionListResponse(
        items=[SecurityQuestionItem(key=key, text=text) for key, text in PRESET_QUESTIONS.items()]
    )


def _client_ip(request: Request) -> str:
    # 프록시 뒤에서 요청한 사람이 지어낼 수 없는 주소를 고른다. (자세한 이유는 app/core/client_ip.py)
    return client_ip(request)


# 재설정 1단계. 이메일이 서버 접속 기록(주소)에 남지 않게 POST 본문으로 받는다.
@router.post(
    "/password-reset/question",
    response_model=PasswordResetQuestionResponse,
    summary="비밀번호 재설정 1단계: 본인 확인 질문 받기",
    responses={429: {"description": "IP당 1시간 300회 초과 (질문 받기와 재설정 합산)"}},
)
def get_reset_question(
    data: PasswordResetQuestionRequest, request: Request, db: Annotated[Session, Depends(get_db)]
) -> PasswordResetQuestionResponse:
    question = password_reset_service.get_question(db, data.email, _client_ip(request))
    return PasswordResetQuestionResponse(question=question)


# 재설정 2단계. 새 비밀번호를 정하기 전에 답이 맞는지 알려준다. 요청마다 시도 횟수에 들어간다.
@router.post(
    "/password-reset/verify",
    response_model=PasswordResetVerifyResponse,
    summary="비밀번호 재설정 2단계: 답 확인 (맞으면 10분짜리 일회용 확인증)",
    responses={
        400: {"description": "이메일 또는 답 불일치 + 남은 시도 횟수 (가입 여부를 숨기려고 이유를 나누지 않음)"},
        429: {"description": "이메일당 24시간에 5번 틀려 잠김(남은 시간), IP당 1시간 300회 초과"},
    },
)
def verify_reset_answer(
    data: PasswordResetVerifyRequest, request: Request, db: Annotated[Session, Depends(get_db)]
) -> PasswordResetVerifyResponse:
    return password_reset_service.verify_answer(db, data, _client_ip(request))


# 재설정 3단계. 성공하면 이 계정의 기존 토큰과 확인증은 모두 쓸 수 없게 된다.
@router.post(
    "/password-reset",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="비밀번호 재설정 3단계: 확인증 + 새 비밀번호",
    responses={400: {"description": "확인증 없음·만료(10분)·이미 사용·위조"}},
)
def reset_password(data: PasswordResetRequest, db: Annotated[Session, Depends(get_db)]) -> None:
    password_reset_service.reset_with_token(db, data)
