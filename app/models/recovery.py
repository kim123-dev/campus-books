from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# 예전 복구 코드 기능의 recovery_codes 테이블은 본인 확인 질문으로 바꾸면서 쓰지 않는다. 운영 DB에는 남겨 두었고
# (지우지 않기로 함), 모델을 지웠으므로 새 DB에는 만들어지지 않는다. (README 데이터 모델 참고)


class PasswordResetAttempt(Base):
    """비밀번호 재설정 시도 기록. 이메일당 24시간 실패 횟수와 IP당 1시간 요청 수를 세어 답을 맞혀 보는 공격을 막는다.

    이메일 원문 대신 재가입 차단과 같은 HMAC 해시(email_ban_service.hash_email)만 남긴다.
    없는 이메일도 똑같이 기록해, 시도 횟수 제한으로 가입 여부를 알아낼 수 없게 한다.
    질문 받기(재설정 1단계)는 email_hash를 빈 문자열로 남겨 IP 횟수에만 들어가게 한다.
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
