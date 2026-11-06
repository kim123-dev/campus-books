from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.models import Post
from app.schemas.post import (
    PageQuery,
    PostCreate,
    PostListResponse,
    PostResponse,
    SizeQuery,
)
from app.services import post_service

router = APIRouter(prefix="/posts", tags=["posts"])


@router.post(
    "",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
    summary="판매글 작성",
    responses={401: {"description": "로그인 필요"}},
)
def create_post(
    data: PostCreate, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> Post:
    return post_service.create_post(db, current_user, data)


# 목록은 로그인 없이도 볼 수 있다. (구매자가 둘러보는 화면)
@router.get("", response_model=PostListResponse, summary="판매글 목록 (최신순)")
def list_posts(
    db: Annotated[Session, Depends(get_db)], page: PageQuery = 1, size: SizeQuery = 20
) -> PostListResponse:
    posts, total = post_service.list_posts(db, page, size)
    return PostListResponse(items=posts, total=total, page=page, size=size)


@router.get(
    "/{post_id}",
    response_model=PostResponse,
    summary="판매글 상세",
    responses={404: {"description": "없는 글"}},
)
def read_post(post_id: int, db: Annotated[Session, Depends(get_db)]) -> Post:
    return post_service.get_post(db, post_id)
