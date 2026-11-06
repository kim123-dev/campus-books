from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import User
from app.schemas.user import UserCreate, UserResponse
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
