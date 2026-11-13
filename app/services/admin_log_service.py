"""관리 기록(감사 로그). 관리자 쓰기 요청 한 번은 기록 한 줄이고, 조치와 같은 트랜잭션에 저장한다.

기록 함수는 커밋하지 않는다. 조치를 처리하는 쪽이 조치와 기록을 함께 커밋해야, 조치가 실패하거나
롤백되면 기록도 남지 않고, 기록 저장이 실패하면 조치도 반영되지 않는다.
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import AdminAction, AdminActionType, AdminTargetType, User
from app.schemas.admin import AdminActionResponse, AdminUserRef
from app.services import user_service


def record(
    db: Session,
    admin: User | None,
    action: AdminActionType,
    target_type: AdminTargetType,
    target_id: int,
    *,
    target_user_id: int | None = None,
    reason: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AdminAction:
    """기록 한 줄을 세션에 넣는다(커밋은 호출한 쪽). detail에는 이메일 같은 개인정보를 넣지 않는다.
    admin이 None이면 관리자가 한 일이 아닌 기록이다(본인 확인 질문·서버 명령으로 비밀번호 재설정).
    """
    entry = AdminAction(
        admin_id=admin.id if admin is not None else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_user_id=target_user_id,
        reason=reason,
        detail=detail or None,
    )
    db.add(entry)
    return entry


def list_actions(
    db: Session,
    page: int,
    size: int,
    *,
    action: AdminActionType | None = None,
    admin_id: int | None = None,
    target_user_id: int | None = None,
) -> tuple[list[AdminActionResponse], int]:
    """기록 목록(최신순). 쿼리는 기록 수와 상관없이 2번이다. (개수 + 목록·관리자·대상 사용자 JOIN)"""
    conditions = []
    if action is not None:
        conditions.append(AdminAction.action == action)
    if admin_id is not None:
        conditions.append(AdminAction.admin_id == admin_id)
    if target_user_id is not None:
        conditions.append(AdminAction.target_user_id == target_user_id)

    total = db.scalar(select(func.count()).select_from(AdminAction).where(*conditions)) or 0
    rows = db.scalars(
        select(AdminAction)
        .options(joinedload(AdminAction.admin), joinedload(AdminAction.target_user))
        .where(*conditions)
        .order_by(AdminAction.created_at.desc(), AdminAction.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return [to_response(entry) for entry in rows], total


def to_response(entry: AdminAction) -> AdminActionResponse:
    return AdminActionResponse(
        id=entry.id,
        action=entry.action,
        admin=user_ref(entry.admin) if entry.admin else None,
        target_type=entry.target_type,
        target_id=entry.target_id,
        target_user=user_ref(entry.target_user) if entry.target_user else None,
        reason=entry.reason,
        detail=entry.detail or {},
        created_at=entry.created_at,
    )


def user_ref(user: User) -> AdminUserRef:
    """관리 화면의 사용자 표시. 탈퇴한 사용자도 번호는 보여주고 이름은 "탈퇴한 사용자"로 바꾼다."""
    return AdminUserRef(id=user.id, nickname=user_service.display_nickname(user), withdrawn=user_service.is_withdrawn(user))
