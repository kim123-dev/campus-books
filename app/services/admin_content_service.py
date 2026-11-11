"""관리자 글·후기 목록. 신고가 없어도 관리자가 직접 찾아 조치할 수 있게 한다."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Post, PostStatus, Report, ReportStatus, ReportTargetType, Review
from app.schemas.admin import AdminPostItem, AdminReviewItem
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
