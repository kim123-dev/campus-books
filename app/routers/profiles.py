from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import OptionalCurrentUser
from app.schemas.post import PageQuery, PostListResponse, SizeQuery
from app.schemas.review import ProfileResponse, ReviewListResponse
from app.services import profile_service, wishlist_service

# 판매자 프로필. 로그인 없이도 볼 수 있다. 없거나 탈퇴한 사용자는 모두 404.
# 경로가 /users/me/... 와 겹치지만 user_id가 정수라 "me"는 여기로 오지 않는다. (users 라우터가 먼저 등록됨)
router = APIRouter(prefix="/users", tags=["profiles"])

NOT_FOUND = {404: {"description": "없거나 탈퇴한 사용자"}}


@router.get("/{user_id}/profile", response_model=ProfileResponse, summary="프로필 (닉네임, 매너 점수)", responses=NOT_FOUND)
def read_profile(user_id: int, db: Annotated[Session, Depends(get_db)]) -> ProfileResponse:
    return profile_service.get_profile(db, user_id)


@router.get(
    "/{user_id}/posts",
    response_model=PostListResponse,
    summary="판매 중·예약 중인 글 (최신순)",
    responses=NOT_FOUND,
)
def read_profile_posts(
    user_id: int,
    current_user: OptionalCurrentUser,
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 1,
    size: SizeQuery = 20,
) -> PostListResponse:
    posts, total = profile_service.list_selling_posts(db, user_id, page, size)
    items = wishlist_service.with_wishlist_flags(db, posts, current_user)
    return PostListResponse(items=items, total=total, page=page, size=size)


@router.get(
    "/{user_id}/reviews",
    response_model=ReviewListResponse,
    summary="받은 후기 (최신순, 숨긴 후기 제외)",
    responses=NOT_FOUND,
)
def read_profile_reviews(
    user_id: int,
    current_user: OptionalCurrentUser,
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 1,
    size: SizeQuery = 20,
) -> ReviewListResponse:
    items, total = profile_service.list_reviews(db, user_id, page, size, current_user)
    return ReviewListResponse(items=items, total=total, page=page, size=size)
