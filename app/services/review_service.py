"""거래 후기: 작성, 쪽지 화면용 후기 상태, 받은 후기 목록, 매너 학점."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import (
    DuplicateReviewError,
    NotTradePartyError,
    ReviewPeriodOverError,
    TradeNotFoundError,
    WithdrawnRevieweeError,
)
from app.models import Conversation, Review, ReviewRating, Trade, User
from app.schemas.review import (
    MannerSummary,
    ReviewCreate,
    RevieweeRole,
    ReviewResponse,
    TradeReviewState,
)
from app.services import trade_service, user_service

# 좋아요 비율을 보여주기 시작하는 후기 수. 1~2개로 100%·0%가 뜨면 실제보다 강하게 보이기 때문이다.
MIN_REVIEWS_FOR_RATIO = 3

# 매너 학점: 대학 성적처럼 0.0~4.5로 보여주는 거래 매너 점수. 받은 후기에서 그때그때 계산하고 저장하지 않는다.
# (숨긴 후기를 빼거나 되살리면 학점도 바로 따라가고, 기존 테이블에 컬럼을 더하지 않아도 된다)
# 소수 계산 오차(0.1을 여러 번 더하면 3.5999…)를 피하려고 0.1 단위 정수로 계산한다. 예: 35 = 3.5
MANNER_GPA_START = 35  # 후기가 없을 때의 기본 학점 B+. 누구나 중간보다 조금 위에서 시작한다.
MANNER_GPA_PER_GOOD = 1  # 좋아요 하나에 +0.1
MANNER_GPA_PER_BAD = 3  # 아쉬워요 하나에 -0.3. 나쁜 거래 한 번을 좋은 거래 세 번만큼 무겁게 본다.
MANNER_GPA_MAX = 45  # 만점 4.5 (A+)
# 학점 → 등급. 위에서부터 처음으로 넘는 칸의 등급을 쓴다. (대학의 4.5 만점 표와 같다)
MANNER_GRADES = [(45, "A+"), (40, "A0"), (35, "B+"), (30, "B0"), (25, "C+"), (20, "C0"), (15, "D+"), (10, "D0"), (0, "F")]


def create_review(db: Session, trade_id: int, user: User, data: ReviewCreate) -> ReviewResponse:
    """후기 작성. 순서: 404 거래 없음 → 403 당사자 아님 → 404 상대 탈퇴 → 400 기간 지남 → 409 이미 작성.
    정지된 사용자는 라우터의 ActiveUser가 먼저 403으로 막는다.
    차단 관계여도 쓸 수 있다. 막으면 "나쁜 거래 뒤 상대를 차단해 후기를 막는" 악용이 가능하기 때문이다.
    """
    trade = db.scalar(
        select(Trade).options(joinedload(Trade.seller), joinedload(Trade.buyer)).where(Trade.id == trade_id)
    )
    if trade is None:
        raise TradeNotFoundError()
    if user.id not in (trade.seller_id, trade.buyer_id):
        raise NotTradePartyError()
    reviewee = trade.buyer if user.id == trade.seller_id else trade.seller
    if user_service.is_withdrawn(reviewee):
        raise WithdrawnRevieweeError()
    if user_service.utc_now() > deadline(trade):
        raise ReviewPeriodOverError(f"후기는 거래 후 {trade_service.REVIEW_PERIOD.days}일 안에만 남길 수 있습니다.")
    if _written(db, trade.id, user.id):
        raise DuplicateReviewError()

    review = Review(
        trade_id=trade.id, reviewer_id=user.id, reviewee_id=reviewee.id, rating=data.rating, content=data.content
    )
    db.add(review)
    try:
        db.commit()
    except IntegrityError:
        # 같은 후기가 동시에 두 번 들어와 다른 요청이 먼저 저장했다. (unique 제약)
        db.rollback()
        raise DuplicateReviewError() from None
    db.refresh(review)
    return _to_response(review, trade, user)


def deadline(trade: Trade) -> datetime:
    """후기를 남길 수 있는 마지막 시각(UTC)."""
    return user_service.as_utc(trade.created_at) + trade_service.REVIEW_PERIOD


def state_for_conversation(db: Session, conversation: Conversation, viewer: User) -> TradeReviewState | None:
    """쪽지 화면용 후기 상태. 이 대화방에 거래가 기록되지 않았으면 None."""
    trade = db.scalar(select(Trade).where(Trade.conversation_id == conversation.id))
    if trade is None:
        return None
    written = _written(db, trade.id, viewer.id)
    partner = conversation.seller if viewer.id == conversation.buyer_id else conversation.buyer
    end = deadline(trade)
    return TradeReviewState(
        trade_id=trade.id,
        written=written,
        can_write=not written and user_service.utc_now() <= end and not user_service.is_withdrawn(partner),
        deadline=end,
    )


def list_received(
    db: Session, user_id: int, page: int, size: int, viewer: User | None = None
) -> tuple[list[ReviewResponse], int]:
    """받은 후기(최신순). 숨긴 후기는 뺀다. viewer가 있으면 후기마다 내가 쓴 것인지 표시한다."""
    conditions = (Review.reviewee_id == user_id, Review.hidden_at.is_(None))
    total = db.scalar(select(func.count()).select_from(Review).where(*conditions)) or 0
    reviews = db.scalars(
        select(Review)
        # 작성자 닉네임과 거래(교재명, 역할)를 JOIN으로 함께 읽어 후기마다 추가 조회가 나가지 않게 한다.
        .options(joinedload(Review.reviewer), joinedload(Review.trade))
        .where(*conditions)
        .order_by(Review.created_at.desc(), Review.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    items = [
        _to_response(review, review.trade, review.reviewer).model_copy(
            update={"is_mine": None if viewer is None else review.reviewer_id == viewer.id}
        )
        for review in reviews
    ]
    return items, total


def manner_summary(db: Session, user_id: int) -> MannerSummary:
    """받은 후기의 좋아요·아쉬워요 수. 쿼리 한 번으로 센다."""
    rows = db.execute(
        select(Review.rating, func.count())
        .where(Review.reviewee_id == user_id, Review.hidden_at.is_(None))
        .group_by(Review.rating)
    ).all()
    counts = {rating: count for rating, count in rows}
    good = counts.get(ReviewRating.GOOD, 0)
    bad = counts.get(ReviewRating.BAD, 0)
    total = good + bad
    ratio = round(good * 100 / total) if total >= MIN_REVIEWS_FOR_RATIO else None
    tenths = manner_gpa_tenths(good, bad)
    return MannerSummary(
        good=good, bad=bad, total=total, good_ratio=ratio, gpa=tenths / 10, grade=manner_grade(tenths)
    )


def manner_gpa_tenths(good: int, bad: int) -> int:
    """매너 학점(0.1 단위 정수). 먼저 다 더한 뒤 0.0~4.5로 자른다.

    그래서 좋아요가 많이 쌓인 사람은 아쉬워요 하나로 바로 떨어지지 않는다. (좋아요 20·아쉬워요 1 = 4.5)
    """
    raw = MANNER_GPA_START + good * MANNER_GPA_PER_GOOD - bad * MANNER_GPA_PER_BAD
    return max(0, min(MANNER_GPA_MAX, raw))


def manner_grade(tenths: int) -> str:
    return next(grade for floor, grade in MANNER_GRADES if tenths >= floor)


def _written(db: Session, trade_id: int, reviewer_id: int) -> bool:
    return (
        db.scalar(select(Review.id).where(Review.trade_id == trade_id, Review.reviewer_id == reviewer_id))
        is not None
    )


def _to_response(review: Review, trade: Trade, reviewer: User) -> ReviewResponse:
    return ReviewResponse(
        id=review.id,
        rating=review.rating,
        content=review.content,
        reviewer_nickname=user_service.display_nickname(reviewer),
        reviewee_role=RevieweeRole.SELLER if review.reviewee_id == trade.seller_id else RevieweeRole.BUYER,
        book_title=trade.book_title_snapshot,
        created_at=review.created_at,
    )
