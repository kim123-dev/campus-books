from fastapi import APIRouter

from app.core.deps import CurrentUser
from app.models import User
from app.schemas.user import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


# 인증은 CurrentUser 의존성이 처리하고, response_model이 password_hash를 걸러낸다.
@router.get(
    "/me",
    response_model=UserResponse,
    summary="내 정보 조회",
    responses={401: {"description": "토큰 없음, 만료·변조된 토큰, 존재하지 않는 사용자"}},
)
def read_me(current_user: CurrentUser) -> User:
    return current_user
