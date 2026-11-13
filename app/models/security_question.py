from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SecurityQuestion(Base):
    """비밀번호를 잊었을 때 본인을 확인하는 질문과 답. 사용자당 하나.

    질문은 미리 준비한 질문(preset_key) 또는 직접 만든 질문(custom_text) 중 하나만 채운다.
    답 원문은 저장하지 않고, 정리한 답(공백 제거·소문자)을 bcrypt로 해시해 둔다.
    users 테이블에 컬럼을 더하면 운영 DB에 ALTER가 필요하므로 새 테이블로 둔다. (create_all이 만든다)
    """

    __tablename__ = "security_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    # 준비된 질문의 키(app/schemas/security_question.py PRESET_QUESTIONS). 직접 만든 질문이면 NULL.
    preset_key: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # 직접 만든 질문(5~60자). 준비된 질문이면 NULL.
    custom_text: Mapped[str | None] = mapped_column(String(60), nullable=True)
    answer_hash: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PasswordResetMethod(StrEnum):
    QUESTION = "QUESTION"  # 본인 확인 질문 (로그인하지 않은 상태에서 본인이)
    SERVER = "SERVER"  # 서버 명령 python -m app.cli reset-password (관리자 비밀번호 분실 등)


class PasswordResetNotice(Base):
    """비밀번호가 재설정되었다는 안내. 다음 로그인 때 한 번 보여주고, 확인하면 seen_at을 채운다.

    본인이 한 일이 아니면 바로 알아챌 수 있게 하기 위해서다. 질문으로 재설정한 기록은
    "7일 동안 질문 변경 금지"의 기준으로도 쓰므로 확인한 뒤에도 지우지 않는다. (탈퇴하면 지운다)
    """

    __tablename__ = "password_reset_notices"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    method: Mapped[PasswordResetMethod] = mapped_column(
        SAEnum(PasswordResetMethod, native_enum=False, length=20, validate_strings=True)
    )
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 본인이 안내를 확인한 시각. NULL이면 아직 안 봤다.
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
