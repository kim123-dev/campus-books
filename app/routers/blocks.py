from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.schemas.block import BlockListResponse, BlockStatusResponse
from app.schemas.post import PageQuery, SizeQuery
from app.services import block_service

router = APIRouter(tags=["blocks"])


# 이미 차단한 사람이면 새로 만들지 않고 200을 돌려준다. (버튼을 여러 번 눌러도 안전)
@router.post(
    "/users/{user_id}/block",
    response_model=BlockStatusResponse,
    status_code=status.HTTP_201_CREATED,
    summary="사용자 차단 (이미 차단했으면 200)",
    responses={
        200: {"description": "이미 차단한 사용자"},
        400: {"description": "자기 자신"},
        401: {"description": "로그인 필요"},
        404: {"description": "없는 사용자"},
    },
)
def block_user(
    user_id: int,
    response: Response,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> BlockStatusResponse:
    created = block_service.block(db, user_id, current_user)
    if not created:
        response.status_code = status.HTTP_200_OK
    return BlockStatusResponse(user_id=user_id, is_blocked=True)


# 차단하지 않은 사람을 해제해도 204. 결과("차단 안 한 상태")가 같으므로 실패로 보지 않는다.
@router.delete(
    "/users/{user_id}/block",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="차단 해제",
    responses={401: {"description": "로그인 필요"}, 404: {"description": "없는 사용자"}},
)
def unblock_user(
    user_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> None:
    block_service.unblock(db, user_id, current_user)


# 내가 차단한 사람만 보여준다. 누가 나를 차단했는지 알려주는 API는 두지 않는다.
@router.get(
    "/users/me/blocks",
    response_model=BlockListResponse,
    summary="내 차단 목록 (차단한 순서 최신순)",
    responses={401: {"description": "로그인 필요"}},
)
def list_my_blocks(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 1,
    size: SizeQuery = 20,
) -> BlockListResponse:
    items, total = block_service.list_blocks(db, current_user, page, size)
    return BlockListResponse(items=items, total=total, page=page, size=size)
