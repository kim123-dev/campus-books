"""관리자 신고 처리. 신고 목록과 처리(기각·글 삭제·기간 정지)를 맡는다.

권한 검사(관리자만)는 라우터 전체에 걸린 의존성(require_admin)이 한다.
"""

from datetime import datetime

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import (
    CannotDeletePostForUserReportError,
    CannotSuspendAdminError,
    ReportAlreadyResolvedError,
    ReportedPostAlreadyDeletedError,
    ReportedUserNotFoundError,
    ReportNotFoundError,
)
from app.models import Post, Report, ReportAction, ReportStatus, ReportTargetType, User, UserRole
from app.schemas.admin import (
    AdminReportResponse,
    AdminUserBrief,
    ReportedUserBrief,
    ReportResolution,
    ReportResolveRequest,
)
from app.services import image_storage, post_service, user_service


# ---------- 목록 ----------


def list_reports(
    db: Session, page: int, size: int, status: ReportStatus | None = None
) -> tuple[list[AdminReportResponse], int]:
    """신고 목록. 미처리 먼저, 그 안에서 최신순. 쿼리 수는 신고 수와 상관없이 4번이다.
    (개수 + 목록·사용자 JOIN + 남아 있는 글 + 피신고자별 미처리 수)
    """
    conditions = [Report.status == status] if status is not None else []
    total = db.scalar(select(func.count()).select_from(Report).where(*conditions)) or 0

    pending_first = case((Report.status == ReportStatus.PENDING, 0), else_=1)
    reports = list(
        db.scalars(
            select(Report)
            .options(
                joinedload(Report.reporter),
                joinedload(Report.reported_user),
                joinedload(Report.resolved_by),
            )
            .where(*conditions)
            .order_by(pending_first, Report.created_at.desc(), Report.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
    )
    existing_posts = _existing_post_ids(db, reports)
    pending_counts = _pending_counts(db, reports)
    now = user_service.utc_now()
    items = [_to_response(report, existing_posts, pending_counts, now) for report in reports]
    return items, total


def _existing_post_ids(db: Session, reports: list[Report]) -> set[int]:
    post_ids = {r.target_id for r in reports if r.target_type == ReportTargetType.POST}
    if not post_ids:
        return set()
    return set(db.scalars(select(Post.id).where(Post.id.in_(post_ids))))


def _pending_counts(db: Session, reports: list[Report]) -> dict[int, int]:
    user_ids = {r.reported_user_id for r in reports if r.reported_user_id is not None}
    if not user_ids:
        return {}
    rows = db.execute(
        select(Report.reported_user_id, func.count())
        .where(Report.reported_user_id.in_(user_ids), Report.status == ReportStatus.PENDING)
        .group_by(Report.reported_user_id)
    )
    return {user_id: count for user_id, count in rows}


def _to_response(
    report: Report, existing_posts: set[int], pending_counts: dict[int, int], now: datetime
) -> AdminReportResponse:
    is_post = report.target_type == ReportTargetType.POST
    pending_for_user = pending_counts.get(report.reported_user_id, 0) if report.reported_user_id else 0
    # 이 신고가 미처리면 자기 자신은 빼고 센다.
    other_pending = pending_for_user - (1 if report.status == ReportStatus.PENDING else 0)

    reported = report.reported_user
    resolution = None
    if report.status == ReportStatus.RESOLVED and report.action is not None and report.resolved_at is not None:
        resolution = ReportResolution(
            action=report.action,
            note=report.resolution_note,
            resolved_by=AdminUserBrief.model_validate(report.resolved_by) if report.resolved_by else None,
            resolved_at=report.resolved_at,
            resolved_with_report_id=report.resolved_with_report_id,
        )
    return AdminReportResponse(
        id=report.id,
        target_type=report.target_type,
        target_id=report.target_id,
        reason=report.reason,
        description=report.description,
        post_title_snapshot=report.post_title_snapshot,
        post_content_snapshot=report.post_content_snapshot,
        post_exists=(report.target_id in existing_posts) if is_post else None,
        reporter=AdminUserBrief.model_validate(report.reporter) if report.reporter else None,
        reported_user=(
            ReportedUserBrief(
                id=reported.id,
                nickname=reported.nickname,
                suspended_until=user_service.active_suspension_end(reported, now),
            )
            if reported
            else None
        ),
        status=report.status,
        created_at=report.created_at,
        resolution=resolution,
        other_pending_count=max(other_pending, 0),
    )


# ---------- 처리 ----------


def resolve_report(
    db: Session, report_id: int, admin: User, data: ReportResolveRequest
) -> tuple[list[int], datetime | None]:
    """신고를 처리하고 (처리된 신고 번호들, 정지 종료 시각)을 돌려준다.
    순서: 404 없는 신고 → 409 이미 처리 → 400 조치 규칙 위반. 처리 기록과 조치는 한 트랜잭션으로 저장한다.
    """
    report = db.get(Report, report_id)
    if report is None:
        raise ReportNotFoundError()
    if report.status != ReportStatus.PENDING:
        raise ReportAlreadyResolvedError()

    post: Post | None = None
    target_user: User | None = None
    if data.action == ReportAction.DELETE_POST:
        if report.target_type != ReportTargetType.POST:
            raise CannotDeletePostForUserReportError()
        post = db.get(Post, report.target_id)
        if post is None:
            raise ReportedPostAlreadyDeletedError()
    elif data.action == ReportAction.SUSPEND:
        target_user = db.get(User, report.reported_user_id) if report.reported_user_id else None
        if target_user is None:
            raise ReportedUserNotFoundError()
        if target_user.role == UserRole.ADMIN:
            raise CannotSuspendAdminError()

    # 두 관리자가 동시에 처리해도 한쪽만 성공하도록, "아직 미처리인 경우에만" 바꾸고 바뀐 행 수를 확인한다.
    record = {
        "status": ReportStatus.RESOLVED,
        "action": data.action,
        "resolution_note": data.note,
        "resolved_by_id": admin.id,
        "resolved_at": func.now(),
    }
    result = db.execute(
        update(Report)
        .where(Report.id == report.id, Report.status == ReportStatus.PENDING)
        .values(**record)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise ReportAlreadyResolvedError()

    together = _reports_to_resolve_together(report, data)
    if together is not None:
        db.execute(
            update(Report)
            .where(together, Report.id != report.id, Report.status == ReportStatus.PENDING)
            .values(**record, resolved_with_report_id=report.id)
            .execution_options(synchronize_session=False)
        )

    image_names: list[str] = []
    suspended_until = None
    if post is not None:
        image_names = post_service.delete_post_rows(db, post)
    if target_user is not None and data.suspend_days is not None:
        suspended_until = user_service.suspend(target_user, data.suspend_days)
    db.commit()
    # 사진 파일은 커밋이 성공한 뒤에 지운다. (작성자 삭제와 같은 순서)
    image_storage.remove_files(image_names)

    together_ids = list(
        db.scalars(
            select(Report.id).where(Report.resolved_with_report_id == report.id).order_by(Report.id)
        )
    )
    return [report.id, *together_ids], suspended_until


def _reports_to_resolve_together(report: Report, data: ReportResolveRequest):
    """함께 처리할 다른 미처리 신고의 조건. 없으면 None."""
    # 글을 지우면 같은 글에 대한 다른 신고는 더 판단할 내용이 없으므로 자동으로 함께 처리한다.
    if data.action == ReportAction.DELETE_POST:
        return (Report.target_type == ReportTargetType.POST) & (Report.target_id == report.target_id)
    # 기각·정지는 관리자가 고른 경우에만 같은 피신고자의 미처리 신고를 함께 처리한다.
    if data.include_same_user and report.reported_user_id is not None:
        return Report.reported_user_id == report.reported_user_id
    return None
