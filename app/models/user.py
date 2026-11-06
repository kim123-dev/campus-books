from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    """회원. 비밀번호는 원문 대신 bcrypt 해시만 저장한다."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 로그인 ID로 쓰이므로 unique + index (로그인 조회가 빈번함)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # 게시글에 표시되는 이름이라 다른 사람과 겹치지 않게 한다.
    nickname: Mapped[str] = mapped_column(String(30), unique=True)
    # 앱 서버 시간 대신 DB 시간을 써서 서버가 여러 대여도 기준을 맞춘다.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
