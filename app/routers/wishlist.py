from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.schemas.post import WishlistStatusResponse
from app.services import wishlist_service

router = APIRouter(tags=["wishlist"])


# 이미 찜한 글이면 새로 만들지 않고 200을 돌려준다. (버튼을 여러 번 눌러도 안전)
@router.post(
    "/posts/{post_id}/wishlist",
    response_model=WishlistStatusResponse,
    status_code=status.HTTP_201_CREATED,
    summary="찜하기 (이미 찜했으면 200)",
    responses={
        200: {"description": "이미 찜한 글"},
        400: {"description": "본인 글, 판매 완료된 글에 새 찜"},
        401: {"description": "로그인 필요"},
        404: {"description": "없는 글"},
    },
)
def add_wishlist(
    post_id: int,
    response: Response,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> WishlistStatusResponse:
    created = wishlist_service.add(db, post_id, current_user)
    if not created:
        response.status_code = status.HTTP_200_OK
    return WishlistStatusResponse(post_id=post_id, is_wishlisted=True)


# 찜하지 않은 글을 해제해도 204. 결과("찜 안 한 상태")가 같으므로 실패로 보지 않는다.
@router.delete(
    "/posts/{post_id}/wishlist",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="찜 해제",
    responses={401: {"description": "로그인 필요"}, 404: {"description": "없는 글"}},
)
def remove_wishlist(
    post_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> None:
    wishlist_service.remove(db, post_id, current_user)
