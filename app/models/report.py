from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ReportTargetType(StrEnum):
    POST = "POST"
    USER = "USER"
    REVIEW = "REVIEW"  # 거래 후기. 피신고자는 후기를 쓴 사람이다.
    MESSAGE = "MESSAGE"  # 쪽지 한 건. 피신고자는 보낸 사람이다. 내용 사본은 message_report_snapshots에 둔다.


class ReportReason(StrEnum):
    SPAM = "SPAM"  # 광고·도배
    FRAUD = "FRAUD"  # 사기 의심
    ABUSE = "ABUSE"  # 욕설·괴롭힘
    INAPPROPRIATE = "INAPPROPRIATE"  # 부적절한 글·물품
    OTHER = "OTHER"  # 기타 (설명 필수)


class ReportStatus(StrEnum):
    PENDING = "PENDING"  # 접수됨. 관리자가 아직 보지 않았다.
    RESOLVED = "RESOLVED"  # 관리자가 처리했다. 어떤 조치였는지는 action에 남는다.


class ReportAction(StrEnum):
    DISMISS = "DISMISS"  # 기각 (조치 없음)
    DELETE_POST = "DELETE_POST"  # 신고된 글 삭제
    SUSPEND = "SUSPEND"  # 신고당한 사용자 기간 정지
    HIDE_REVIEW = "HIDE_REVIEW"  # 신고된 후기 숨김 (목록·매너 학점에서 빠진다)


def _enum_column(enum_cls: type[StrEnum]) -> SAEnum:
    # Post 모델과 같이 DB 고유 ENUM 대신 문자열 + 값 검사로 저장한다. (SQLite·MySQL 공통)
    return SAEnum(enum_cls, native_enum=False, length=20, validate_strings=True)


class Report(Base):
    """신고. 관리자가 관리 화면에서 처리하고, 처리 기록(누가·언제·어떤 조치·메모)을 같은 행에 남긴다.

    신고자는 신고당한 사람에게 어떤 응답으로도 드러나지 않는다.
    """

    __tablename__ = "reports"
    __table_args__ = (
        # 같은 사람이 같은 대상을 두 번 신고하지 못하게 DB에서도 막는다.
        UniqueConstraint("reporter_id", "target_type", "target_id", name="uq_report_target"),
        # 신고 횟수 제한에서 한 사람의 최근 신고를 센다.
        Index("ix_reports_reporter_created", "reporter_id", "created_at"),
        # 관리 화면은 미처리 신고를 먼저, 최신순으로 보여준다.
        Index("ix_reports_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # 신고한 사람이 탈퇴해도 신고 기록은 관리자 확인을 위해 남긴다(SET NULL).
    reporter_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    target_type: Mapped[ReportTargetType] = mapped_column(_enum_column(ReportTargetType))
    # 글·사용자·후기 번호. 글은 삭제되면 행이 지워지지만 신고는 남겨야 하므로 FK를 걸지 않는다.
    # 대상 종류와 조치는 CHECK 제약 없는 문자열 컬럼이라, 종류를 늘려도 운영 DB에 ALTER가 필요 없다.
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

    # ---------- 처리 기록 (처리 전에는 모두 NULL) ----------
    action: Mapped[ReportAction | None] = mapped_column(_enum_column(ReportAction), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 처리한 관리자. 관리자 계정이 지워져도 처리 기록은 남긴다(SET NULL).
    resolved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 다른 신고를 처리하면서 함께 처리된 경우 그 신고 번호. 직접 처리한 신고는 NULL.
    resolved_with_report_id: Mapped[int | None] = mapped_column(nullable=True)

    # 관리 화면에서 닉네임을 보여주기 위한 관계. 목록에서는 joinedload로 한 번에 읽는다.
    reporter: Mapped["User | None"] = relationship(foreign_keys=[reporter_id])
    reported_user: Mapped["User | None"] = relationship(foreign_keys=[reported_user_id])
    resolved_by: Mapped["User | None"] = relationship(foreign_keys=[resolved_by_id])


class MessageReportSnapshot(Base):
    """쪽지 신고 시점의 메시지 사본. 신고 한 건에 한 줄이다.

    쪽지는 지우지 않지만, 보낸 사람이 탈퇴하거나 대화 상대가 나가도 관리자가 신고된 그 메시지만 정확히 볼 수 있게
    내용·보낸 사람·보낸 시각을 그대로 복사해 둔다. 관리자는 대화 전체가 아니라 이 사본만 본다.
    reports 테이블에 컬럼을 더하면 ALTER가 필요하므로 새 테이블로 둔다.
    """

    __tablename__ = "message_report_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), unique=True)
    # 원본 메시지 번호. 메시지는 지우지 않지만, 사본만으로 판단할 수 있게 FK 없이 번호만 남긴다.
    message_id: Mapped[int]
    conversation_id: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # 사진 메시지면 그 사진 파일 이름(서버가 만든 이름). 관리자 사진 API가 이 값으로 파일을 찾는다.
    image_filename: Mapped[str | None] = mapped_column(String(64), nullable=True)
