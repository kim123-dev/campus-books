from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserRole(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"  # 신고 처리 화면을 쓸 수 있다. 가입으로는 될 수 없고 CLI로만 지정한다. (app/cli.py)


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
    # Post 모델과 같이 DB 고유 ENUM 대신 문자열 + 값 검사로 저장한다. (SQLite·MySQL 공통)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, native_enum=False, length=20, validate_strings=True),
        default=UserRole.USER,
        server_default=UserRole.USER.value,
    )
    # 이용 정지가 끝나는 시각(UTC). 이 시각이 지나면 따로 풀어 주지 않아도 정지가 끝난 것으로 본다.
    # 정지 여부 판단은 user_service.active_suspension_end 한 곳에서 한다.
    suspended_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
