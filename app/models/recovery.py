from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RecoveryCode(Base):
    """비밀번호를 잊었을 때 본인을 확인하는 복구 코드. 사용자당 하나이고, 코드 원문은 저장하지 않는다.

    이메일을 보낼 수단이 없어서, 가입할 때 한 번 보여준 코드를 가진 사람만 비밀번호를 재설정할 수 있게 한다.
    users 테이블에 컬럼을 더하면 운영 DB에 ALTER가 필요하므로 새 테이블로 둔다. (create_all이 만든다)
    """

    __tablename__ = "recovery_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 사용자당 한 줄. 재발급하면 같은 줄의 해시를 바꿔 이전 코드는 바로 쓸 수 없게 된다.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    # 코드의 SHA-256(16진수 64자). 코드가 약 79비트 무작위라 bcrypt 같은 느린 해시 없이도 대입할 수 없다.
    code_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PasswordResetAttempt(Base):
    """비밀번호 재설정 시도 기록. 이메일·IP마다 1시간 시도 횟수를 세어 코드를 맞혀 보는 공격을 막는다.

    이메일 원문 대신 재가입 차단과 같은 HMAC 해시(email_ban_service.hash_email)만 남긴다.
    없는 이메일도 똑같이 기록해, 시도 횟수 제한으로 가입 여부를 알아낼 수 없게 한다.
    """

    __tablename__ = "password_reset_attempts"
    __table_args__ = (
        Index("ix_password_reset_attempts_email_created", "email_hash", "created_at"),
        Index("ix_password_reset_attempts_ip_created", "ip", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email_hash: Mapped[str] = mapped_column(String(64))
    # IPv6 최대 길이 45자. 프록시 뒤라면 uvicorn --proxy-headers가 넣어 준 실제 접속 주소다.
    ip: Mapped[str] = mapped_column(String(45))
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
