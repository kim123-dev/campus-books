from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.post import Post

# 한 사람이 등록할 수 있는 찾는 교재 조건 수. 서비스 검사와 화면("3/10")이 함께 쓴다.
MAX_ALERTS_PER_USER = 10


class BookAlert(Base):
    """찾는 교재 조건. 조건에 맞는 판매 중인 새 글이 올라오면 알림(AlertNotification)을 만든다."""

    __tablename__ = "book_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    # MySQL·PostgreSQL에서는 탈퇴 때 함께 지워지지만, 탈퇴는 사용자 행을 남기므로 서비스에서 직접 지운다.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # 교재명·과목명에 부분 일치(대소문자 무시)로 비교한다. 등록한 그대로(앞뒤 공백만 제거) 저장한다.
    keyword: Mapped[str] = mapped_column(String(100))
    # NULL이면 가격과 상관없이 알린다. 값이 있으면 이 가격 이하(포함)인 글만.
    max_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AlertNotification(Base):
    """찾는 교재 알림 한 건. 같은 사람에게 같은 글로는 한 번만 만든다."""

    __tablename__ = "alert_notifications"
    __table_args__ = (
        # 조건 여러 개가 한 글에 맞거나, 글 수정으로 다시 매칭해도 알림이 하나만 생기게 DB에서도 막는다.
        UniqueConstraint("user_id", "post_id", name="uq_alert_notification_user_post"),
        # 내 알림 목록(최신순)과 안 읽은 수를 센다.
        Index("ix_alert_notifications_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # 글이 지워지면 알림도 의미가 없으므로 함께 지운다. (SQLite는 FK를 실행하지 않아 글 삭제 서비스가 직접 지운다)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    # 알림을 만든 키워드 사본. 조건을 지운 뒤에도 "어떤 키워드로 온 알림인지" 보여줄 수 있게 한다.
    keyword: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # NULL이면 아직 안 읽었다.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    post: Mapped[Post] = relationship()
