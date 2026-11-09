from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser, OptionalCurrentUser
from app.models import Post
from app.schemas.post import (
    PageQuery,
    PostCreate,
    PostDetailResponse,
    PostListResponse,
    PostSearchParams,
    PostStatusUpdate,
    PostUpdate,
    SizeQuery,
)
from app.services import post_service, wishlist_service

router = APIRouter(prefix="/posts", tags=["posts"])


@router.post(
    "",
    response_model=PostDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="판매글 작성",
    responses={401: {"description": "로그인 필요"}},
)
def create_post(
    data: PostCreate, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> Post:
    return post_service.create_post(db, current_user, data)


# 목록은 로그인 없이도 볼 수 있다. (구매자가 둘러보는 화면)
# 로그인했으면 글마다 찜 여부(is_wishlisted)를 채우고, 아니면 null로 둔다.
@router.get("", response_model=PostListResponse, summary="판매글 목록 (검색·필터, 최신순)")
def list_posts(
    db: Annotated[Session, Depends(get_db)],
    current_user: OptionalCurrentUser,
    search: Annotated[PostSearchParams, Query()],
    page: PageQuery = 1,
    size: SizeQuery = 20,
) -> PostListResponse:
    posts, total = post_service.list_posts(db, page, size, search)
    items = wishlist_service.with_wishlist_flags(db, posts, current_user)
    return PostListResponse(items=items, total=total, page=page, size=size)


# 상세는 로그인 없이도 볼 수 있지만, 연락 방법(오픈채팅 링크)은 로그인한 사용자에게만 준다.
# 토큰이 없거나 잘못·만료되었어도 401이 아니라 링크만 null로 비운 글을 돌려준다.
@router.get(
    "/{post_id}",
    response_model=PostDetailResponse,
    summary="판매글 상세 (오픈채팅 링크는 로그인 시에만)",
    responses={404: {"description": "없는 글"}},
)
def read_post(
    post_id: int, current_user: OptionalCurrentUser, db: Annotated[Session, Depends(get_db)]
) -> PostDetailResponse:
    post = post_service.get_post(db, post_id)
    return post_service.to_detail_response(
        post,
        show_contact=current_user is not None,
        is_wishlisted=wishlist_service.is_wishlisted(db, post.id, current_user),
    )


# 수정·삭제 API의 공통 에러 응답. Swagger 문서에 보이도록 정리해 둔다.
OWNER_ONLY_RESPONSES: dict[int | str, dict] = {
    401: {"description": "로그인 필요"},
    403: {"description": "작성자가 아님"},
    404: {"description": "없는 글"},
}


@router.patch(
    "/{post_id}",
    response_model=PostDetailResponse,
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
    response_model=PostDetailResponse,
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
