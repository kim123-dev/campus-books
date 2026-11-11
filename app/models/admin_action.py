from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.user import User


class AdminActionType(StrEnum):
    """관리 기록에 남는 조치. 관리자 쓰기 요청 한 번이 기록 한 줄이다."""

    DISMISS_REPORT = "DISMISS_REPORT"  # 신고 기각
    DELETE_POST = "DELETE_POST"  # 글 삭제 (신고 처리 또는 직접)
    SUSPEND = "SUSPEND"  # 기간 정지 (신고 처리 또는 직접)
    UNSUSPEND = "UNSUSPEND"  # 정지 해제
    HIDE_REVIEW = "HIDE_REVIEW"  # 후기 숨김 (신고 처리)
    UNHIDE_REVIEW = "UNHIDE_REVIEW"  # 후기 숨김 해제
    WITHDRAW_USER = "WITHDRAW_USER"  # 강제 탈퇴 (이메일 재가입 차단 포함)
    UNBAN_EMAIL = "UNBAN_EMAIL"  # 재가입 차단 해제


class AdminTargetType(StrEnum):
    REPORT = "REPORT"
    POST = "POST"
    USER = "USER"
    REVIEW = "REVIEW"
    EMAIL_BAN = "EMAIL_BAN"  # 재가입 차단 행. 이메일 원문은 어디에도 남기지 않는다.


def _enum_column(enum_cls: type[StrEnum]) -> SAEnum:
    # 다른 모델과 같이 DB 고유 ENUM 대신 문자열 + 값 검사로 저장한다. 조치를 늘려도 ALTER가 필요 없다.
    return SAEnum(enum_cls, native_enum=False, length=30, validate_strings=True)


class AdminAction(Base):
    """관리 기록(감사 로그): 누가·언제·누구에게·무엇을·왜.

    조치와 같은 트랜잭션에 저장해, 조치가 실패하면 기록도 남지 않는다. 고치거나 지우는 API는 두지 않는다.
    새 테이블이라 운영 DB에도 배포 후 시작할 때 자동으로 만들어진다. (ALTER 불필요)
    """

    __tablename__ = "admin_actions"
    __table_args__ = (
        Index("ix_admin_actions_created", "created_at"),
        # 사용자 상세의 정지 이력과 "이 사용자에 대한 기록"을 최신순으로 읽는다.
        Index("ix_admin_actions_target_user_created", "target_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # 조치한 관리자. 관리자는 탈퇴할 수 없지만, 계정 행이 지워지는 경우에도 기록은 남긴다(SET NULL).
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[AdminActionType] = mapped_column(_enum_column(AdminActionType))
    target_type: Mapped[AdminTargetType] = mapped_column(_enum_column(AdminTargetType))
    # 글·후기·신고·차단 행 번호. 글처럼 지워질 수 있는 대상도 있어 FK를 걸지 않는다.
    target_id: Mapped[int]
    # 조치와 관련된 사용자(정지·탈퇴 대상, 지운 글의 작성자, 숨긴 후기의 작성자). 사용자별로 기록을 모아 본다.
    # 사용자 행은 탈퇴해도 지우지 않으므로(익명화) FK를 그대로 둔다.
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # 사유. 강제 조치는 필수이고, 신고 기각만 비워 둘 수 있다. (요청 스키마가 검사)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 조치별 추가 정보 (신고 번호, 정지 일수·종료 시각, 지운 글 제목 등). 이메일은 넣지 않는다.
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    admin: Mapped[User | None] = relationship(foreign_keys=[admin_id])
    target_user: Mapped[User | None] = relationship(foreign_keys=[target_user_id])
