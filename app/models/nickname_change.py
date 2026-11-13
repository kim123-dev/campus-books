from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NicknameChange(Base):
    """닉네임 변경 기록. 30일에 한 번만 바꿀 수 있게 마지막 변경 시각을 여기서 찾는다.

    users 테이블에 "마지막 변경 시각" 컬럼을 더하면 운영 DB(PostgreSQL)에 ALTER가 필요하다.
    create_all은 기존 테이블에 컬럼을 더하지 않으므로, 새 테이블에 기록을 쌓는 쪽을 골랐다.
    바뀌기 전 닉네임도 남겨 두면 신고를 처리할 때 "예전 이름"으로 찾을 수 있다. 탈퇴하면 함께 지운다.
    """

    __tablename__ = "nickname_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 사용자마다 마지막 기록을 찾으므로 인덱스를 둔다.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    old_nickname: Mapped[str] = mapped_column(String(30))
    new_nickname: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
