from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import ActiveUser, CurrentUser
from app.models import MAX_ALERTS_PER_USER, BookAlert
from app.schemas.alert import (
    AlertCreate,
    AlertListResponse,
    AlertResponse,
    NotificationListResponse,
    NotificationResponse,
    NotificationUnreadCountResponse,
)
from app.schemas.post import PageQuery, SizeQuery
from app.services import alert_service

router = APIRouter(tags=["alerts"])


# ---------- 찾는 교재 조건 ----------


@router.get(
    "/users/me/alerts",
    response_model=AlertListResponse,
    summary="내 찾는 교재 조건 목록",
    responses={401: {"description": "로그인 필요"}},
)
def list_my_alerts(current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> AlertListResponse:
    items = [AlertResponse.model_validate(a) for a in alert_service.list_alerts(db, current_user)]
    return AlertListResponse(items=items, max_count=MAX_ALERTS_PER_USER)


# 등록은 쓰기 요청이라 정지 중에는 막는다(ActiveUser). 목록·삭제·알림 읽기는 정지 중에도 쓸 수 있다.
@router.post(
    "/users/me/alerts",
    response_model=AlertResponse,
    status_code=status.HTTP_201_CREATED,
    summary="찾는 교재 등록",
    responses={
        400: {"description": "등록 개수 초과"},
        401: {"description": "로그인 필요"},
        403: {"description": "이용 정지 중"},
        409: {"description": "같은 키워드가 이미 있음 (대소문자 무시)"},
    },
)
def create_alert(
    data: AlertCreate, current_user: ActiveUser, db: Annotated[Session, Depends(get_db)]
) -> BookAlert:
    return alert_service.create_alert(db, current_user, data)


@router.delete(
    "/users/me/alerts/{alert_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="찾는 교재 삭제",
    responses={401: {"description": "로그인 필요"}, 404: {"description": "없거나 남의 조건"}},
)
def delete_alert(alert_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> None:
    alert_service.delete_alert(db, alert_id, current_user)


# ---------- 알림 ----------


@router.get(
    "/notifications",
    response_model=NotificationListResponse,
    summary="찾는 교재 알림 목록 (최신순)",
    responses={401: {"description": "로그인 필요"}},
)
def list_notifications(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 1,
    size: SizeQuery = 20,
) -> NotificationListResponse:
    items, total = alert_service.list_notifications(db, current_user, page, size)
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in items], total=total, page=page, size=size
    )


@router.get(
    "/notifications/unread-count",
    response_model=NotificationUnreadCountResponse,
    summary="안 읽은 알림 수 (헤더 배지용)",
    responses={401: {"description": "로그인 필요"}},
)
def count_unread(current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> NotificationUnreadCountResponse:
    return NotificationUnreadCountResponse(unread_count=alert_service.count_unread(db, current_user))


@router.post(
    "/notifications/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="알림 모두 읽음",
    responses={401: {"description": "로그인 필요"}},
)
def read_all(current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> None:
    alert_service.mark_all_read(db, current_user)
