from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.trade import Trade
from app.models.user import User


class ReviewRating(StrEnum):
    """거래 후기 평가. 학교 안 거래는 후기 수가 적어 5점제보다 두 가지로 나누는 편이 구분이 잘 된다."""

    GOOD = "GOOD"  # 좋아요
    BAD = "BAD"  # 아쉬워요


class Review(Base):
    """거래 후기. 거래한 두 사람이 서로 한 번씩 남긴다. 작성자는 수정·삭제할 수 없고, 관리자만 숨길 수 있다."""

    __tablename__ = "reviews"
    __table_args__ = (
        # 한 거래에 한 사람이 한 번만. 동시에 두 번 보내도 DB가 막는다.
        UniqueConstraint("trade_id", "reviewer_id", name="uq_review_trade_reviewer"),
        # 프로필에서 받은 후기를 최신순으로 읽는다.
        Index("ix_reviews_reviewee_created", "reviewee_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id"))
    # 사용자는 탈퇴해도 행이 남으므로(익명화) 작성자·대상자 FK는 그대로 둔다.
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reviewee_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # DB 고유 ENUM 대신 문자열 + 값 검사로 저장한다. 나중에 단계를 늘려도 ALTER가 필요 없다.
    rating: Mapped[ReviewRating] = mapped_column(
        SAEnum(ReviewRating, native_enum=False, length=20, validate_strings=True)
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # 관리자가 신고를 처리하며 숨긴 시각. 숨긴 후기는 목록과 매너 학점에서 빠진다.
    # 신고 처리 기능보다 먼저 배포돼도 ALTER가 필요 없도록 처음부터 둔다.
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    trade: Mapped[Trade] = relationship()
    reviewer: Mapped[User] = relationship(foreign_keys=[reviewer_id])
    reviewee: Mapped[User] = relationship(foreign_keys=[reviewee_id])
