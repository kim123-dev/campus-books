"""거래 약속(만남 약속 카드)과 학교별 만남 장소.

기존 테이블(messages 등)에 컬럼을 더하지 않으려고 모두 새 테이블로 둔다. (운영 DB는 create_all만 쓴다)
약속 카드와 수락·거절·취소는 모두 messages에 한 줄씩 남기고(쪽지 사진과 같은 방식),
어떤 메시지가 어떤 약속의 무슨 일인지는 appointment_messages가 잇는다.
그래서 순서·폴링·읽음·나가기 숨김·신고가 일반 쪽지와 같은 규칙으로 동작한다.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func, true
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AppointmentStatus(StrEnum):
    """저장하는 약속 상태. "지남"은 저장하지 않고 약속 시각으로 계산한다(응답의 is_past)."""

    PROPOSED = "PROPOSED"  # 제안됨(상대의 수락·거절을 기다림)
    ACCEPTED = "ACCEPTED"  # 수락됨
    DECLINED = "DECLINED"  # 거절됨
    REPLACED = "REPLACED"  # 새 제안으로 바뀜(변경됨)
    CANCELED = "CANCELED"  # 제안자가 취소함


# 진행 중(대화방에 하나만 있을 수 있음)인 상태
ACTIVE_STATUSES = (AppointmentStatus.PROPOSED, AppointmentStatus.ACCEPTED)


class AppointmentEvent(StrEnum):
    """약속 메시지가 알리는 일. 화면은 이 메시지를 받으면 해당 약속 카드를 다시 그린다."""

    PROPOSE = "PROPOSE"
    ACCEPT = "ACCEPT"
    DECLINE = "DECLINE"
    CANCEL = "CANCEL"


# MySQL과 SQLite에서 똑같이 동작하도록 DB 고유 ENUM 대신 문자열 컬럼 + 값 검사로 저장한다. (다른 모델과 같은 규칙)
def _enum_column(enum_cls: type[StrEnum]) -> SAEnum:
    return SAEnum(enum_cls, native_enum=False, length=20, validate_strings=True)


class MeetingPlace(Base):
    """학교별 만남 장소. 관리자가 추가하고, 지우지 않고 비활성으로 둔다(지난 약속이 가리키므로).
    목록이 비어 있어도 약속은 직접 입력한 장소로 잡을 수 있다.
    """

    __tablename__ = "meeting_places"
    __table_args__ = (UniqueConstraint("school_id", "name", name="uq_meeting_place_school_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    # 목록 순서. 작은 값이 먼저, 같으면 먼저 추가한 것.
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Appointment(Base):
    """대화방 안의 만남 약속 하나."""

    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    proposer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # 약속 시각(UTC). 화면 입력은 한국 시간으로 받아 바꿔 저장한다.
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # 장소 이름. 목록에서 골랐어도 그때 이름을 그대로 남긴다(관리자가 나중에 이름을 바꿔도 약속 내용은 그대로).
    place_name: Mapped[str] = mapped_column(String(100))
    meeting_place_id: Mapped[int | None] = mapped_column(ForeignKey("meeting_places.id"), nullable=True)
    status: Mapped[AppointmentStatus] = mapped_column(_enum_column(AppointmentStatus))
    # 이 제안이 바꾼 이전 약속(변경). 화면이 이전 카드를 "변경됨"으로 다시 그리는 데 쓴다.
    replaces_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 진행 중(제안·수락)인 동안만 conversation_id, 끝나면 NULL. unique라 한 대화방에 진행 중인 약속이 둘 생기지 않는다.
    # 두 사람이 동시에 제안해도 DB가 하나만 받아 준다. (NULL끼리는 겹쳐도 된다: SQLite·MySQL 공통)
    active_conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AppointmentMessage(Base):
    """약속 메시지(제안·수락·거절·취소)와 약속을 잇는다. 메시지 하나에 한 줄."""

    __tablename__ = "appointment_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), unique=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), index=True)
    event: Mapped[AppointmentEvent] = mapped_column(_enum_column(AppointmentEvent))
