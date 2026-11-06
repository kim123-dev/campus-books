from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.models import Post
from app.schemas.post import (
    PageQuery,
    PostCreate,
    PostListResponse,
    PostResponse,
    PostStatusUpdate,
    PostUpdate,
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


# 수정·삭제 API의 공통 에러 응답. Swagger 문서에 보이도록 정리해 둔다.
OWNER_ONLY_RESPONSES: dict[int | str, dict] = {
    401: {"description": "로그인 필요"},
    403: {"description": "작성자가 아님"},
    404: {"description": "없는 글"},
}


@router.patch(
    "/{post_id}",
    response_model=PostResponse,
    summary="판매글 수정 (보낸 필드만)",
    responses={**OWNER_ONLY_RESPONSES, 400: {"description": "판매 완료된 글"}},
)
def update_post(
    post_id: int,
    data: PostUpdate,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Post:
    return post_service.update_post(db, post_id, current_user, data)


@router.patch(
    "/{post_id}/status",
    response_model=PostResponse,
    summary="판매 상태 변경",
    responses={**OWNER_ONLY_RESPONSES, 400: {"description": "판매 완료된 글의 상태 변경"}},
)
def change_post_status(
    post_id: int,
    data: PostStatusUpdate,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Post:
    return post_service.change_status(db, post_id, current_user, data.status)


# 삭제 성공 시 돌려줄 내용이 없으므로 본문 없는 204를 쓴다.
@router.delete(
    "/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="판매글 삭제",
    responses=OWNER_ONLY_RESPONSES,
)
def delete_post(
    post_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> None:
    post_service.delete_post(db, post_id, current_user)
