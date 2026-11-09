from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.models import User
from app.schemas.post import PageQuery, PostListResponse, SizeQuery
from app.schemas.user import UserResponse
from app.services import post_service, wishlist_service

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


# 내 글 관리 화면용. 판매 완료된 글도 보여야 하므로 상태로 거르지 않는다.
@router.get(
    "/me/posts",
    response_model=PostListResponse,
    summary="내 판매글 목록 (최신순)",
    responses={401: {"description": "로그인 필요"}},
)
def read_my_posts(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 1,
    size: SizeQuery = 20,
) -> PostListResponse:
    posts, total = post_service.list_posts_by_seller(db, current_user.id, page, size)
    return PostListResponse(items=posts, total=total, page=page, size=size)


# 찜 목록 화면용. 찜해 둔 뒤 판매 완료된 글도 보여준다. (카드에 판매 완료 배지가 붙는다)
@router.get(
    "/me/wishlist",
    response_model=PostListResponse,
    summary="내 찜 목록 (찜한 순서 최신순)",
    responses={401: {"description": "로그인 필요"}},
)
def read_my_wishlist(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 1,
    size: SizeQuery = 20,
) -> PostListResponse:
    items, total = wishlist_service.list_wishlist(db, current_user, page, size)
    return PostListResponse(items=items, total=total, page=page, size=size)
