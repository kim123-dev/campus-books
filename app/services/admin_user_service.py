"""관리자 사용자 관리: 사용자 목록·검색·상세, 정지·정지 해제.

이메일은 관리 화면 중 사용자 관리에서만 보여준다. 탈퇴한 계정은 이메일이 지워져(임의 값) 있으므로 null로 내보낸다.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import (
    CannotSuspendAdminError,
    UserNotFoundError,
    UserNotSuspendedError,
    UserWithdrawnError,
)
from app.models import (
    AdminAction,
    AdminActionType,
    AdminTargetType,
    Post,
    Report,
    ReportStatus,
    Review,
    User,
    UserRole,
)
from app.schemas.admin import (
    AdminReasonRequest,
    AdminSuspendRequest,
    AdminUserCounts,
    AdminUserDetail,
    AdminUserFilter,
    AdminUserItem,
)
from app.services import admin_dashboard_service, admin_log_service, user_service
from app.services.post_service import LIKE_ESCAPE, escape_like

# 상세 화면에 보여줄 정지 이력 개수. 그보다 오래된 것은 관리 기록 화면에서 본다.
SUSPENSION_HISTORY_LIMIT = 20


def list_users(
    db: Session, page: int, size: int, *, status: AdminUserFilter | None = None, q: str | None = None
) -> tuple[list[AdminUserItem], int]:
    """사용자 목록(가입 최신순). 쿼리는 사용자 수와 상관없이 2번이다. (개수 + 목록·글 수·미처리 신고 수)

    q는 닉네임·이메일의 일부, 또는 사용자 번호다. 탈퇴한 계정은 닉네임·이메일이 지워져 번호로만 찾는다.
    """
    active = User.password_hash != user_service.WITHDRAWN_PASSWORD_HASH
    conditions = []
    if status is None:
        conditions.append(active)
    elif status == AdminUserFilter.WITHDRAWN:
        conditions.append(~active)
    elif status == AdminUserFilter.ADMIN:
        conditions += [active, User.role == UserRole.ADMIN]
    elif status == AdminUserFilter.SUSPENDED:
        now_db = admin_dashboard_service.db_time(db, user_service.utc_now())
        conditions += [active, User.suspended_until > now_db]
    if q:
        conditions.append(_search_condition(q, active))

    total = db.scalar(select(func.count()).select_from(User).where(*conditions)) or 0
    rows = db.execute(
        select(User, _post_count(), _pending_report_count())
        .where(*conditions)
        .order_by(User.created_at.desc(), User.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    now = user_service.utc_now()
    return [_to_item(user, posts, pending, now) for user, posts, pending in rows], total


def get_user(db: Session, user_id: int) -> AdminUserDetail:
    """사용자 상세. 탈퇴한 계정도 번호로 볼 수 있다(관리 기록에서 이어 오기 위해). 없으면 404.
    쿼리는 3번이다. (사용자 + 개수들 + 정지 이력)
    """
    user = db.get(User, user_id)
    if user is None:
        raise UserNotFoundError()
    counts = db.execute(
        select(
            _post_count(),
            _scalar_count(Report, Report.reported_user_id == user_id),
            _pending_report_count(),
            _scalar_count(Review, Review.reviewee_id == user_id),
            _scalar_count(Review, Review.reviewee_id == user_id, Review.hidden_at.is_not(None)),
            _scalar_count(Review, Review.reviewer_id == user_id),
        ).where(User.id == user_id)
    ).one()
    history = db.scalars(
        select(AdminAction)
        .where(
            AdminAction.target_user_id == user_id,
            AdminAction.action.in_([AdminActionType.SUSPEND, AdminActionType.UNSUSPEND]),
        )
        .order_by(AdminAction.created_at.desc(), AdminAction.id.desc())
        .limit(SUSPENSION_HISTORY_LIMIT)
    ).all()
    item = _to_item(user, counts[0], counts[2], user_service.utc_now())
    return AdminUserDetail(
        **item.model_dump(),
        counts=AdminUserCounts(
            posts=counts[0],
            reports_received=counts[1],
            reports_pending=counts[2],
            reviews_received=counts[3],
            reviews_hidden=counts[4],
            reviews_written=counts[5],
        ),
        # 기록의 관리자·대상 사용자는 관계로 읽는다. 이력은 최대 20줄이라 따로 묶어 읽지 않는다.
        suspensions=[admin_log_service.to_response(entry) for entry in history],
    )


def _search_condition(q: str, active):
    pattern = f"%{escape_like(q.strip())}%"
    matches = [
        active
        & or_(User.nickname.ilike(pattern, escape=LIKE_ESCAPE), User.email.ilike(pattern, escape=LIKE_ESCAPE))
    ]
    number = q.strip().lstrip("#")
    if number.isdigit():
        matches.append(User.id == int(number))
    return or_(*matches)


def _scalar_count(model, *conditions):
    # 사용자 한 줄마다 세는 상관 서브쿼리. 목록 크기와 상관없이 쿼리 1번 안에서 끝난다.
    return select(func.count()).select_from(model).where(*conditions).scalar_subquery()


def _post_count():
    return _scalar_count(Post, Post.seller_id == User.id)


def _pending_report_count():
    return _scalar_count(Report, Report.reported_user_id == User.id, Report.status == ReportStatus.PENDING)


def _to_item(user: User, post_count: int, pending: int, now) -> AdminUserItem:
    withdrawn = user_service.is_withdrawn(user)
    return AdminUserItem(
        id=user.id,
        email=None if withdrawn else user.email,
        nickname=user_service.display_nickname(user),
        role=user.role,
        created_at=user.created_at,
        suspended_until=user_service.active_suspension_end(user, now),
        withdrawn=withdrawn,
        post_count=post_count or 0,
        pending_report_count=pending or 0,
    )


# ---------- 정지·정지 해제 ----------


def suspend(db: Session, admin: User, user_id: int, data: AdminSuspendRequest) -> datetime:
    """신고 없이 직접 정지한다. 순서: 404 없음 → 409 탈퇴 → 400 관리자(자기 자신 포함).
    이미 더 늦게 끝나는 정지가 있으면 줄이지 않는다. (신고 처리의 정지와 같은 규칙)
    """
    user = _get_target(db, user_id)
    if user.role == UserRole.ADMIN:
        raise CannotSuspendAdminError()
    now = user_service.utc_now()
    previous = user_service.active_suspension_end(user, now)
    end = max(now + timedelta(days=data.days), previous) if previous else now + timedelta(days=data.days)
    # 같은 순간 강제 탈퇴·관리자 지정과 겹쳐도 그 상태의 계정을 정지하지 않도록 조건을 걸고 바뀐 행 수를 확인한다.
    # (DB에는 시간대 없는 UTC로 저장한다. user_service.suspend와 같은 형식)
    _guarded_update(db, user, {"suspended_until": end.replace(tzinfo=None)}, User.role != UserRole.ADMIN)
    detail = {"days": data.days, "suspended_until": end.isoformat()}
    if previous is not None:
        detail["previous_until"] = previous.isoformat()
    admin_log_service.record(
        db, admin, AdminActionType.SUSPEND, AdminTargetType.USER, user.id,
        target_user_id=user.id, reason=data.reason, detail=detail,
    )
    db.commit()
    return end


def unsuspend(db: Session, admin: User, user_id: int, data: AdminReasonRequest) -> None:
    """정지를 바로 푼다. 순서: 404 없음 → 409 탈퇴 → 409 정지 중이 아님."""
    user = _get_target(db, user_id)
    now = user_service.utc_now()
    previous = user_service.active_suspension_end(user, now)
    if previous is None:
        raise UserNotSuspendedError()
    # 두 관리자가 동시에 풀어도 한쪽만 성공하고 기록도 한 줄만 남도록, "아직 정지 중인 경우에만" 바꾼다.
    _guarded_update(
        db, user, {"suspended_until": None},
        User.suspended_until > admin_dashboard_service.db_time(db, now),
        error=UserNotSuspendedError,
    )
    admin_log_service.record(
        db, admin, AdminActionType.UNSUSPEND, AdminTargetType.USER, user.id,
        target_user_id=user.id, reason=data.reason, detail={"previous_until": previous.isoformat()},
    )
    db.commit()


def _get_target(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise UserNotFoundError()
    if user_service.is_withdrawn(user):
        raise UserWithdrawnError()
    return user


def _guarded_update(db: Session, user: User, values: dict, condition, error=UserWithdrawnError) -> None:
    """탈퇴하지 않았고 condition에 맞을 때만 바꾼다. 0행이면 롤백하고 error를 낸다."""
    result = db.execute(
        update(User)
        .where(User.id == user.id, User.password_hash != user_service.WITHDRAWN_PASSWORD_HASH, condition)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise error()
    # 조건부 UPDATE는 세션의 객체를 바꾸지 않으므로, 이후 응답·기록이 새 값을 읽도록 다시 읽게 한다.
    db.expire(user, ["suspended_until"])
