"""관리자 글·후기 관리: 목록과 조치(글 삭제, 후기 숨김 해제). 신고가 없어도 관리자가 직접 찾아 조치할 수 있게 한다."""

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.exc import StaleDataError

from app.core.exceptions import PostNotFoundError, ReviewNotFoundError, ReviewNotHiddenError
from app.models import (
    AdminActionType,
    AdminTargetType,
    Post,
    PostStatus,
    Report,
    ReportAction,
    ReportStatus,
    ReportTargetType,
    Review,
    User,
)
from app.schemas.admin import AdminPostItem, AdminReasonRequest, AdminReviewItem
from app.services import admin_log_service, image_storage, post_service, user_service
from app.services.admin_log_service import user_ref
from app.services.post_service import LIKE_ESCAPE, escape_like


def list_posts(
    db: Session,
    page: int,
    size: int,
    *,
    q: str | None = None,
    status: PostStatus | None = None,
    seller_id: int | None = None,
) -> tuple[list[AdminPostItem], int]:
    """글 목록(최신순). 쿼리는 글 수와 상관없이 2번이다. (개수 + 목록·판매자 JOIN·미처리 신고 수)
    q는 제목·교재명의 일부다. 일반 목록과 달리 차단·정지와 상관없이 모든 글을 보여준다.
    """
    conditions = []
    if q:
        pattern = f"%{escape_like(q.strip())}%"
        conditions.append(or_(Post.title.ilike(pattern, escape=LIKE_ESCAPE), Post.book_title.ilike(pattern, escape=LIKE_ESCAPE)))
    if status is not None:
        conditions.append(Post.status == status)
    if seller_id is not None:
        conditions.append(Post.seller_id == seller_id)

    total = db.scalar(select(func.count()).select_from(Post).where(*conditions)) or 0
    pending = (
        select(func.count())
        .select_from(Report)
        .where(
            Report.target_type == ReportTargetType.POST,
            Report.target_id == Post.id,
            Report.status == ReportStatus.PENDING,
        )
        .scalar_subquery()
    )
    rows = db.execute(
        select(Post, pending)
        .options(joinedload(Post.seller))
        .where(*conditions)
        .order_by(Post.created_at.desc(), Post.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    items = [
        AdminPostItem(
            id=post.id,
            title=post.title,
            book_title=post.book_title,
            price=post.price,
            status=post.status,
            created_at=post.created_at,
            seller=user_ref(post.seller),
            pending_report_count=count or 0,
        )
        for post, count in rows
    ]
    return items, total


def list_reviews(
    db: Session,
    page: int,
    size: int,
    *,
    hidden: bool | None = None,
    reviewee_id: int | None = None,
    reviewer_id: int | None = None,
) -> tuple[list[AdminReviewItem], int]:
    """후기 목록(최신순). 숨긴 후기도 보여준다. 쿼리는 2번이다. (개수 + 목록·작성자·받은 사람·거래 JOIN)"""
    conditions = []
    if hidden is not None:
        conditions.append(Review.hidden_at.is_not(None) if hidden else Review.hidden_at.is_(None))
    if reviewee_id is not None:
        conditions.append(Review.reviewee_id == reviewee_id)
    if reviewer_id is not None:
        conditions.append(Review.reviewer_id == reviewer_id)

    total = db.scalar(select(func.count()).select_from(Review).where(*conditions)) or 0
    rows = db.scalars(
        select(Review)
        .options(joinedload(Review.reviewer), joinedload(Review.reviewee), joinedload(Review.trade))
        .where(*conditions)
        .order_by(Review.created_at.desc(), Review.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    items = [
        AdminReviewItem(
            id=review.id,
            rating=review.rating,
            content=review.content,
            book_title=review.trade.book_title_snapshot,
            reviewer=user_ref(review.reviewer),
            reviewee=user_ref(review.reviewee),
            created_at=review.created_at,
            hidden_at=review.hidden_at,
        )
        for review in rows
    ]
    return items, total


def unhide_review(db: Session, admin: User, review_id: int, data: AdminReasonRequest) -> None:
    """숨긴 후기를 다시 보이게 한다. 순서: 404 없음 → 409 숨긴 후기가 아님.
    다시 보이면 받은 사람의 후기 목록과 매너 점수에 바로 다시 들어간다. (숨김 여부만 보고 세기 때문)
    """
    review = db.get(Review, review_id)
    if review is None:
        raise ReviewNotFoundError()
    if review.hidden_at is None:
        raise ReviewNotHiddenError()
    hidden_at = review.hidden_at
    # 두 관리자가 동시에 풀어도 한쪽만 성공하고 기록도 한 줄만 남도록 "아직 숨겨진 경우에만" 바꾼다.
    result = db.execute(
        update(Review)
        .where(Review.id == review.id, Review.hidden_at.is_not(None))
        .values(hidden_at=None)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise ReviewNotHiddenError()
    # 숨김과 같이 대상 사용자는 후기를 쓴 사람이다. (조치가 그 사람의 글에 대한 것이므로)
    admin_log_service.record(
        db, admin, AdminActionType.UNHIDE_REVIEW, AdminTargetType.REVIEW, review.id,
        target_user_id=review.reviewer_id, reason=data.reason,
        detail={"book_title": review.trade.book_title_snapshot, "hidden_at": user_service.as_utc(hidden_at).isoformat()},
    )
    db.commit()


def delete_post(db: Session, admin: User, post_id: int, data: AdminReasonRequest) -> list[int]:
    """신고 없이 글을 지운다. 없으면 404. 지운 글에 대한 미처리 신고는 같은 사유로 함께 처리하고 그 번호를 돌려준다.

    지우는 규칙(대화방은 남기고 연결만 끊기, 찜·알림·사진 삭제)은 작성자 삭제·신고 처리와 같다. (post_service.delete_post_rows)
    """
    post = db.get(Post, post_id)
    if post is None:
        raise PostNotFoundError()
    # 글은 지워지므로 무엇을 지웠는지 기록에 사본을 남긴다.
    detail: dict = {"post_title": post.title, "book_title": post.book_title}
    resolved_ids = list(
        db.scalars(
            select(Report.id)
            .where(Report.target_type == ReportTargetType.POST, Report.target_id == post.id, Report.status == ReportStatus.PENDING)
            .order_by(Report.id)
        )
    )
    if resolved_ids:
        # 글이 없어지면 더 판단할 내용이 없으므로, 신고 처리에서 글을 지울 때와 같이 함께 처리한다.
        db.execute(
            update(Report)
            .where(Report.id.in_(resolved_ids), Report.status == ReportStatus.PENDING)
            .values(
                status=ReportStatus.RESOLVED,
                action=ReportAction.DELETE_POST,
                resolution_note=data.reason,
                resolved_by_id=admin.id,
                resolved_at=func.now(),
            )
            .execution_options(synchronize_session=False)
        )
        detail["resolved_ids"] = resolved_ids
    admin_log_service.record(
        db, admin, AdminActionType.DELETE_POST, AdminTargetType.POST, post.id,
        target_user_id=post.seller_id, reason=data.reason, detail=detail,
    )
    image_names = post_service.delete_post_rows(db, post)
    try:
        db.commit()
    except StaleDataError:
        # 같은 순간 작성자나 다른 관리자가 먼저 지웠다. 이 요청의 기록·신고 처리도 함께 취소된다.
        db.rollback()
        raise PostNotFoundError() from None
    # 사진 파일은 커밋이 성공한 뒤에 지운다. (작성자 삭제와 같은 순서)
    image_storage.remove_files(image_names)
    return resolved_ids
