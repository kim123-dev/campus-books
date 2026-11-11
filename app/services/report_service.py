"""신고 접수. 저장만 하고, 읽는 화면(관리자)은 다음 단계에서 만든다.

신고당한 사람에게 가는 어떤 응답에도 신고 여부나 신고자가 드러나지 않는다.
"""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    CannotReportOwnPostError,
    CannotReportOwnReviewError,
    CannotReportSelfError,
    DuplicateReportError,
    ReportRateLimitError,
    ReviewNotFoundError,
    UserNotFoundError,
)
from app.models import Report, ReportTargetType, Review, User
from app.schemas.report import ReportCreate
from app.services import post_service, user_service


@dataclass(frozen=True)
class ReportRateLimit:
    """window_seconds초 안에 max_reports건까지 신고할 수 있다."""

    max_reports: int
    window_seconds: int


# 신고 남발(괴롭힘 목적의 무더기 신고)을 막는 기준. 이 값 하나만 바꾸면 된다.
REPORT_RATE_LIMIT = ReportRateLimit(max_reports=5, window_seconds=3600)


def report_post(db: Session, post_id: int, reporter: User, data: ReportCreate) -> Report:
    """글 신고. 순서: 404 글 없음 → 400 내 글 → 409 이미 신고 → 429 횟수 제한."""
    post = post_service.get_post(db, post_id)
    if post.seller_id == reporter.id:
        raise CannotReportOwnPostError()
    return _create(
        db,
        reporter,
        data,
        target_type=ReportTargetType.POST,
        target_id=post.id,
        reported_user_id=post.seller_id,
        # 글은 삭제하면 행이 지워지므로, 관리자가 볼 수 있게 신고 시점의 내용을 복사해 둔다.
        post_title_snapshot=post.title,
        post_content_snapshot=post.description,
    )


def report_user(db: Session, user_id: int, reporter: User, data: ReportCreate) -> Report:
    """사용자 신고. 순서: 404 없는 사용자 → 400 자기 자신 → 409 이미 신고 → 429 횟수 제한."""
    # 탈퇴한 사용자는 없는 사람으로 본다.
    if user_service.get_user_by_id(db, user_id) is None:
        raise UserNotFoundError()
    if user_id == reporter.id:
        raise CannotReportSelfError()
    return _create(
        db, reporter, data, target_type=ReportTargetType.USER, target_id=user_id, reported_user_id=user_id
    )


def report_review(db: Session, review_id: int, reporter: User, data: ReportCreate) -> Report:
    """후기 신고. 순서: 404 없거나 숨긴 후기 → 400 내가 쓴 후기 → 409 이미 신고 → 429 횟수 제한.
    피신고자는 후기를 쓴 사람이다. 작성자가 탈퇴했으면 정지할 사람이 없으므로 비워 둔다.
    후기는 작성자가 고치거나 지울 수 없어서, 글 신고와 달리 내용 사본을 따로 저장하지 않는다.
    """
    review = db.get(Review, review_id)
    # 숨긴 후기는 아무에게도 보이지 않으므로 없는 것으로 본다.
    if review is None or review.hidden_at is not None:
        raise ReviewNotFoundError()
    if review.reviewer_id == reporter.id:
        raise CannotReportOwnReviewError()
    reviewer = db.get(User, review.reviewer_id)
    reported_user_id = None if reviewer is None or user_service.is_withdrawn(reviewer) else reviewer.id
    return _create(
        db,
        reporter,
        data,
        target_type=ReportTargetType.REVIEW,
        target_id=review.id,
        reported_user_id=reported_user_id,
    )


def _create(
    db: Session,
    reporter: User,
    data: ReportCreate,
    *,
    target_type: ReportTargetType,
    target_id: int,
    reported_user_id: int | None,
    post_title_snapshot: str | None = None,
    post_content_snapshot: str | None = None,
) -> Report:
    if _already_reported(db, reporter.id, target_type, target_id):
        raise DuplicateReportError()
    _check_rate_limit(db, reporter)

    report = Report(
        reporter_id=reporter.id,
        target_type=target_type,
        target_id=target_id,
        reported_user_id=reported_user_id,
        reason=data.reason,
        description=data.description,
        post_title_snapshot=post_title_snapshot,
        post_content_snapshot=post_content_snapshot,
    )
    db.add(report)
    try:
        db.commit()
    except IntegrityError:
        # 같은 신고 두 개가 동시에 들어와 다른 요청이 먼저 저장했다. (unique 제약)
        db.rollback()
        raise DuplicateReportError() from None
    db.refresh(report)
    return report


def _already_reported(db: Session, reporter_id: int, target_type: ReportTargetType, target_id: int) -> bool:
    return (
        db.scalar(
            select(Report.id).where(
                Report.reporter_id == reporter_id,
                Report.target_type == target_type,
                Report.target_id == target_id,
            )
        )
        is not None
    )


def _check_rate_limit(db: Session, reporter: User) -> None:
    # 쪽지 도배 제한과 같은 방식: 저장된 created_at과 같은 기준인 DB 시간으로 최근 신고 수를 센다.
    db_now = db.scalar(select(func.now()))
    since = db_now - timedelta(seconds=REPORT_RATE_LIMIT.window_seconds)
    recent = db.scalar(
        select(func.count())
        .select_from(Report)
        .where(Report.reporter_id == reporter.id, Report.created_at > since)
    )
    if (recent or 0) >= REPORT_RATE_LIMIT.max_reports:
        raise ReportRateLimitError(retry_after=REPORT_RATE_LIMIT.window_seconds)
