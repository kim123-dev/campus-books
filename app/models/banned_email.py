from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BannedEmail(Base):
    """강제 탈퇴로 재가입을 막은 이메일. 이메일 원문은 저장하지 않고 HMAC 해시만 둔다.

    해시만 있으면 관리자도 목록에서 어떤 이메일인지 알 수 없다. 차단을 풀 때는 관리자가 이메일을 직접 입력하고,
    같은 키로 해시를 만들어 찾는다. (app/services/email_ban_service.py)
    """

    __tablename__ = "banned_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    # HMAC-SHA256 16진수 64자. 가입할 때마다 찾으므로 unique 인덱스를 둔다.
    email_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 차단한 관리자. 관리자 계정이 지워져도 차단은 남긴다(SET NULL).
    banned_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
