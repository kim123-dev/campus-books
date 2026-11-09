from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReportTargetType(StrEnum):
    POST = "POST"
    USER = "USER"


class ReportReason(StrEnum):
    SPAM = "SPAM"  # 광고·도배
    FRAUD = "FRAUD"  # 사기 의심
    ABUSE = "ABUSE"  # 욕설·괴롭힘
    INAPPROPRIATE = "INAPPROPRIATE"  # 부적절한 글·물품
    OTHER = "OTHER"  # 기타 (설명 필수)


class ReportStatus(StrEnum):
    PENDING = "PENDING"  # 접수됨. 관리자 처리 상태는 다음 단계에서 늘린다.


def _enum_column(enum_cls: type[StrEnum]) -> SAEnum:
    # Post 모델과 같이 DB 고유 ENUM 대신 문자열 + 값 검사로 저장한다. (SQLite·MySQL 공통)
    return SAEnum(enum_cls, native_enum=False, length=20, validate_strings=True)


class Report(Base):
    """신고. 저장만 하고, 읽는 화면(관리자)은 다음 단계에서 만든다.

    신고자는 신고당한 사람에게 어떤 응답으로도 드러나지 않는다.
    """

    __tablename__ = "reports"
    __table_args__ = (
        # 같은 사람이 같은 대상을 두 번 신고하지 못하게 DB에서도 막는다.
        UniqueConstraint("reporter_id", "target_type", "target_id", name="uq_report_target"),
        # 신고 횟수 제한에서 한 사람의 최근 신고를 센다.
        Index("ix_reports_reporter_created", "reporter_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # 신고한 사람이 탈퇴해도 신고 기록은 관리자 확인을 위해 남긴다(SET NULL).
    reporter_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    target_type: Mapped[ReportTargetType] = mapped_column(_enum_column(ReportTargetType))
    # 글 번호 또는 사용자 번호. 글은 삭제되면 행이 지워지지만 신고는 남겨야 하므로 FK를 걸지 않는다.
    target_id: Mapped[int]
    # 신고당한 사람. 글 신고면 그 글의 작성자. 사람별 신고 수를 셀 때 쓴다.
    reported_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reason: Mapped[ReportReason] = mapped_column(_enum_column(ReportReason))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 글 신고 시점의 제목·설명 사본. 신고당한 사람이 글을 지워도 관리자가 내용을 확인할 수 있게 한다.
    post_title_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    post_content_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ReportStatus] = mapped_column(
        _enum_column(ReportStatus),
        default=ReportStatus.PENDING,
        server_default=ReportStatus.PENDING.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
