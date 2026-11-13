"""관리자 신고 처리. 신고 목록과 처리(기각·글 삭제·기간 정지·후기 숨김)를 맡는다.

권한 검사(관리자만)는 라우터 전체에 걸린 의존성(require_admin)이 한다.
"""

from datetime import datetime

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import (
    CannotDeletePostForMessageReportError,
    CannotDeletePostForReviewReportError,
    CannotDeletePostForUserReportError,
    CannotHideReviewForOtherReportError,
    CannotSuspendAdminError,
    ImageNotFoundError,
    ReportAlreadyResolvedError,
    ReportedPostAlreadyDeletedError,
    ReportedUserNotFoundError,
    ReportNotFoundError,
    ReviewNotFoundError,
)
from app.models import (
    AdminActionType,
    AdminTargetType,
    MessageReportSnapshot,
    Post,
    Report,
    ReportAction,
    ReportStatus,
    ReportTargetType,
    Review,
    User,
    UserRole,
)
from app.schemas.admin import (
    AdminMessageBrief,
    AdminReportResponse,
    AdminReviewBrief,
    AdminUserBrief,
    ReportedUserBrief,
    ReportResolution,
    ReportResolveRequest,
)
from app.services import admin_log_service, image_storage, post_service, user_service


# ---------- 목록 ----------


def list_reports(
    db: Session, page: int, size: int, status: ReportStatus | None = None, reported_user_id: int | None = None
) -> tuple[list[AdminReportResponse], int]:
    """신고 목록. 미처리 먼저, 그 안에서 최신순. 쿼리 수는 신고 수와 상관없이 6번 이하다.
    (개수 + 목록·사용자 JOIN + 남아 있는 글 + 신고된 후기 + 쪽지 사본 + 피신고자별 미처리 수)
    """
    conditions = [Report.status == status] if status is not None else []
    if reported_user_id is not None:
        conditions.append(Report.reported_user_id == reported_user_id)
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
    reviews = _reported_reviews(db, reports)
    messages = _reported_messages(db, reports)
    pending_counts = _pending_counts(db, reports)
    now = user_service.utc_now()
    items = [_to_response(report, existing_posts, reviews, messages, pending_counts, now) for report in reports]
    return items, total


def _existing_post_ids(db: Session, reports: list[Report]) -> set[int]:
    post_ids = {r.target_id for r in reports if r.target_type == ReportTargetType.POST}
    if not post_ids:
        return set()
    return set(db.scalars(select(Post.id).where(Post.id.in_(post_ids))))


def _reported_reviews(db: Session, reports: list[Report]) -> dict[int, AdminReviewBrief]:
    """후기 신고의 대상 후기들을 한 번에 읽는다. 받은 사람·거래(교재명)도 JOIN으로 함께 가져온다."""
    review_ids = {r.target_id for r in reports if r.target_type == ReportTargetType.REVIEW}
    if not review_ids:
        return {}
    rows = db.scalars(
        select(Review)
        .options(joinedload(Review.reviewee), joinedload(Review.trade))
        .where(Review.id.in_(review_ids))
    )
    return {
        review.id: AdminReviewBrief(
            rating=review.rating,
            content=review.content,
            book_title=review.trade.book_title_snapshot,
            reviewee=None
            if user_service.is_withdrawn(review.reviewee)
            else AdminUserBrief.model_validate(review.reviewee),
            hidden=review.hidden_at is not None,
        )
        for review in rows
    }


def _reported_messages(db: Session, reports: list[Report]) -> dict[int, AdminMessageBrief]:
    """쪽지 신고의 사본을 신고 번호별로 한 번에 읽는다."""
    report_ids = [r.id for r in reports if r.target_type == ReportTargetType.MESSAGE]
    if not report_ids:
        return {}
    rows = db.scalars(select(MessageReportSnapshot).where(MessageReportSnapshot.report_id.in_(report_ids)))
    return {
        row.report_id: AdminMessageBrief(
            content=row.content,
            sent_at=row.sent_at,
            conversation_id=row.conversation_id,
            has_image=row.image_filename is not None,
        )
        for row in rows
    }


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
    report: Report,
    existing_posts: set[int],
    reviews: dict[int, AdminReviewBrief],
    messages: dict[int, AdminMessageBrief],
    pending_counts: dict[int, int],
    now: datetime,
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
        review=reviews.get(report.target_id) if report.target_type == ReportTargetType.REVIEW else None,
        message=messages.get(report.id),
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
    순서: 404 없는 신고 → 409 이미 처리 → 400 조치 규칙 위반. 처리 기록·관리 기록·조치는 한 트랜잭션으로 저장한다.
    글 삭제는 글 신고에만, 후기 숨김은 후기 신고에만 쓸 수 있다. 정지는 모든 신고에 쓸 수 있다(후기는 작성자 정지).
    """
    report = db.get(Report, report_id)
    if report is None:
        raise ReportNotFoundError()
    if report.status != ReportStatus.PENDING:
        raise ReportAlreadyResolvedError()

    post: Post | None = None
    target_user: User | None = None
    review: Review | None = None
    if data.action == ReportAction.HIDE_REVIEW:
        if report.target_type != ReportTargetType.REVIEW:
            raise CannotHideReviewForOtherReportError()
        review = db.get(Review, report.target_id)
        if review is None:
            raise ReviewNotFoundError()
    elif data.action == ReportAction.DELETE_POST:
        if report.target_type == ReportTargetType.REVIEW:
            raise CannotDeletePostForReviewReportError()
        if report.target_type == ReportTargetType.MESSAGE:
            raise CannotDeletePostForMessageReportError()
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

    together_ids = list(
        db.scalars(
            select(Report.id).where(Report.resolved_with_report_id == report.id).order_by(Report.id)
        )
    )
    resolved_ids = [report.id, *together_ids]
    detail: dict = {"report_id": report.id}
    if together_ids:
        detail["resolved_ids"] = resolved_ids

    image_names: list[str] = []
    suspended_until = None
    if post is not None:
        # 글은 지워지므로 무엇을 지웠는지 기록에 사본을 남긴다.
        detail |= {"post_title": post.title, "book_title": post.book_title}
        admin_log_service.record(
            db, admin, AdminActionType.DELETE_POST, AdminTargetType.POST, post.id,
            target_user_id=post.seller_id, reason=data.note, detail=detail,
        )
        image_names = post_service.delete_post_rows(db, post)
    elif target_user is not None and data.suspend_days is not None:
        suspended_until = user_service.suspend(target_user, data.suspend_days)
        detail |= {"days": data.suspend_days, "suspended_until": suspended_until.isoformat()}
        admin_log_service.record(
            db, admin, AdminActionType.SUSPEND, AdminTargetType.USER, target_user.id,
            target_user_id=target_user.id, reason=data.note, detail=detail,
        )
    elif review is not None:
        # 행은 지우지 않고 숨긴 시각만 남긴다. 신고 기록이 가리키는 원문을 관리자가 계속 볼 수 있게 하기 위해서다.
        if review.hidden_at is None:
            review.hidden_at = user_service.utc_now()
        admin_log_service.record(
            db, admin, AdminActionType.HIDE_REVIEW, AdminTargetType.REVIEW, review.id,
            target_user_id=review.reviewer_id, reason=data.note, detail=detail,
        )
    else:
        admin_log_service.record(
            db, admin, AdminActionType.DISMISS_REPORT, AdminTargetType.REPORT, report.id,
            target_user_id=report.reported_user_id, reason=data.note, detail=detail,
        )
    db.commit()
    # 사진 파일은 커밋이 성공한 뒤에 지운다. (작성자 삭제와 같은 순서)
    image_storage.remove_files(image_names)
    return resolved_ids, suspended_until


def _reports_to_resolve_together(report: Report, data: ReportResolveRequest):
    """함께 처리할 다른 미처리 신고의 조건. 없으면 None."""
    # 글을 지우면 같은 글에 대한 다른 신고는 더 판단할 내용이 없으므로 자동으로 함께 처리한다.
    if data.action == ReportAction.DELETE_POST:
        return (Report.target_type == ReportTargetType.POST) & (Report.target_id == report.target_id)
    # 후기를 숨기면 같은 후기에 대한 다른 신고도 더 판단할 내용이 없다.
    if data.action == ReportAction.HIDE_REVIEW:
        return (Report.target_type == ReportTargetType.REVIEW) & (Report.target_id == report.target_id)
    # 기각·정지는 관리자가 고른 경우에만 같은 피신고자의 미처리 신고를 함께 처리한다.
    if data.include_same_user and report.reported_user_id is not None:
        return Report.reported_user_id == report.reported_user_id
    return None


def reported_message_image(db: Session, report_id: int) -> str:
    """쪽지 신고 사본에 남은 사진 파일 이름. 쪽지 신고가 아니거나 사진이 없으면 404."""
    filename = db.scalar(
        select(MessageReportSnapshot.image_filename).where(MessageReportSnapshot.report_id == report_id)
    )
    if filename is None:
        raise ImageNotFoundError()
    return filename
