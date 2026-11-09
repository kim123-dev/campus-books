from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserBlock(Base):
    """차단. blocker가 blocked를 차단했다. 둘 사이에는 쪽지를 주고받을 수 없다."""

    __tablename__ = "user_blocks"
    __table_args__ = (
        # 서비스 검사와 함께 DB에서도 자기 자신 차단을 막는다.
        CheckConstraint("blocker_id <> blocked_id", name="ck_user_block_not_self"),
    )

    # (blocker_id, blocked_id)를 기본 키로 묶어 같은 사람을 두 번 차단하지 않게 한다.
    # 사용자가 탈퇴하면 차단 기록도 의미가 없으므로 함께 지운다. (SQLite는 FK를 실행하지 않으므로
    # 탈퇴 기능을 만들 때 서비스에서 직접 지워야 한다 — README 참고)
    blocker_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # "상대가 나를 차단했는지"를 찾을 때 blocked_id로 찾으므로 index를 따로 둔다.
    blocked_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
