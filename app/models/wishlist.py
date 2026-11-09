from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Wishlist(Base):
    """찜(관심 목록). 사용자가 나중에 다시 보려고 표시한 판매글."""

    __tablename__ = "wishlists"
    __table_args__ = (
        # 내 찜 목록을 찜한 순서(최신순)로 보여줄 때 쓴다.
        Index("ix_wishlists_user_created", "user_id", "created_at"),
    )

    # (user_id, post_id)를 기본 키로 묶어, 같은 글을 두 번 찜하는 일을 DB에서도 막는다.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # MySQL에서는 글이 지워지면 찜도 함께 지워진다. SQLite는 FK를 실행하지 않으므로 글 삭제 서비스가 직접 지운다.
    # 글 삭제 때 post_id로 찾으므로 index를 따로 둔다. (기본 키는 user_id가 앞이라 post_id만으로는 못 쓴다)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
