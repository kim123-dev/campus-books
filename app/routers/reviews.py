from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import ActiveUser, CurrentUser
from app.schemas.review import ReviewCreate, ReviewReminderListResponse, ReviewResponse
from app.services import review_service

router = APIRouter(tags=["reviews"])


# 정지 중에는 쓸 수 없도록 ActiveUser를 쓴다. 작성한 후기는 수정·삭제할 수 없다(신고 → 관리자 숨김만).
@router.post(
    "/trades/{trade_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="거래 후기 작성 (거래한 두 사람이 한 번씩)",
    responses={
        400: {"description": "작성 기간이 지남"},
        401: {"description": "로그인 필요"},
        403: {"description": "거래 당사자가 아님, 이용 정지 중"},
        404: {"description": "없는 거래, 상대가 탈퇴함"},
        409: {"description": "이미 작성함"},
        422: {"description": "평가 없음, 글 200자 초과"},
    },
)
def create_review(
    trade_id: int, data: ReviewCreate, current_user: ActiveUser, db: Annotated[Session, Depends(get_db)]
) -> ReviewResponse:
    return review_service.create_review(db, trade_id, current_user, data)


# 읽기 전용이라 정지 중에도 부를 수 있다(CurrentUser). 정지 중에는 후기를 쓸 수 없으므로 서비스가 빈 목록을 돌려준다.
@router.get(
    "/notifications/reviews",
    response_model=ReviewReminderListResponse,
    summary="안 쓴 후기 알림 (저장하지 않고 계산, 최신 거래순)",
    responses={401: {"description": "로그인 필요"}},
)
def list_review_reminders(
    current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> ReviewReminderListResponse:
    items = review_service.list_reminders(db, current_user)
    return ReviewReminderListResponse(items=items, total=len(items))
