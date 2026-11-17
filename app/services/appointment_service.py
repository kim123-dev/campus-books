"""거래 약속(만남 약속 카드).

- 제안·수락·거절·취소는 모두 쪽지 한 줄(messages)로 남긴다. content에는 서버가 만든 한국어 요약을 넣어
  쪽지함 미리보기·신고 증거·옛 화면에서도 무슨 일인지 보이게 하고, 화면은 응답의 appointment로 카드를 그린다.
- 보내기 검사(없는 방·참여자 아님·탈퇴한 상대·차단·도배 제한)는 일반 쪽지와 같은 함수를 쓴다.
- 한 대화방에 진행 중(제안·수락)인 약속은 하나뿐이다. 새로 제안하면 이전 약속은 "변경됨"이 된다.
  두 사람이 동시에 제안하면 appointments.active_conversation_id(unique)가 하나만 받아 주고 나머지는 409.
- 상태는 조건부 UPDATE로 바꾼다. 수락과 취소가 동시에 와도 먼저 바꾼 쪽만 성공하고 나머지는 409.
- "지남"은 저장하지 않고 약속 시각으로 계산한다.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.core.exceptions import (
    AppointmentAlreadyStartedError,
    AppointmentConflictError,
    AppointmentNotFoundError,
    AppointmentStateChangedError,
    AppointmentTimeInPastError,
    AppointmentTooFarError,
    CannotRespondOwnAppointmentError,
    InvalidMeetingPlaceError,
    NotAppointmentProposerError,
    PostNotProposableError,
)
from app.models import (
    Appointment,
    AppointmentEvent,
    AppointmentMessage,
    AppointmentStatus,
    Conversation,
    ConversationUserState,
    MeetingPlace,
    Message,
    Post,
    PostSchool,
    PostStatus,
    User,
)
from app.models.appointment import ACTIVE_STATUSES
from app.schemas.appointment import AppointmentCreate, AppointmentReminderResponse
from app.schemas.conversation import MessageResponse
from app.services import admin_dashboard_service, conversation_service, user_service

# 너무 먼 약속은 잊히기 쉬워 막는다. 이 값 하나만 바꾸면 된다. (오류 문구의 "60일"도 함께)
MAX_DAYS_AHEAD = 60
# 종 알림은 약속 시각이 지나도 이만큼은 더 보여준다. (조금 늦게 만나는 경우)
REMINDER_GRACE = timedelta(hours=1)

WEEKDAYS = "월화수목금토일"
EVENT_LABELS = {
    AppointmentEvent.ACCEPT: "약속 수락",
    AppointmentEvent.DECLINE: "약속 거절",
    AppointmentEvent.CANCEL: "약속 취소",
}


# ---------- 제안 ----------


def propose(
    db: Session, conversation_id: int, user: User, data: AppointmentCreate, now: datetime | None = None
) -> MessageResponse:
    """약속 제안(또는 변경 제안). 순서: 보내기 공통 검사(404·403·400·429) → 400 글 상태 → 400 시각 → 400 장소."""
    now = now or user_service.utc_now()
    conversation = conversation_service.check_can_send(db, conversation_id, user)
    post = conversation.post
    # 판매 완료·삭제된 글에서는 새 약속을 잡지 않는다. (이미 잡힌 약속은 그대로 보이고 수락·취소할 수 있다)
    if post is None or post.status == PostStatus.SOLD:
        raise PostNotProposableError()
    starts_at = to_utc(data.date, data.time)
    if starts_at <= now:
        raise AppointmentTimeInPastError()
    if starts_at > now + timedelta(days=MAX_DAYS_AHEAD):
        raise AppointmentTooFarError()
    place_id, place_name = _resolve_place(db, post, data)

    previous = _active(db, conversation.id)
    replaces_id = None
    if previous is not None:
        if user_service.as_utc(previous.starts_at) > now:
            # 아직 오지 않은 약속을 바꾸는 것이므로 "변경됨"으로 남긴다.
            previous.status = AppointmentStatus.REPLACED
            replaces_id = previous.id
        # 이미 지난 약속은 상태를 그대로 두고(수락됨·지남) 진행 중 자리만 비운다.
        previous.active_conversation_id = None
        db.flush()

    appointment = Appointment(
        conversation_id=conversation.id,
        proposer_id=user.id,
        starts_at=starts_at,
        place_name=place_name,
        meeting_place_id=place_id,
        status=AppointmentStatus.PROPOSED,
        replaces_id=replaces_id,
        active_conversation_id=conversation.id,
    )
    label = "약속 변경" if replaces_id is not None else "약속 제안"
    try:
        db.add(appointment)
        db.flush()  # 여기서 unique 충돌(동시 제안)이 드러난다.
        message = _append_event(db, conversation, user, appointment, AppointmentEvent.PROPOSE, label, now)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppointmentConflictError() from None
    return _event_response(db, message, user, appointment, AppointmentEvent.PROPOSE, now)


def to_utc(day, at) -> datetime:
    """한국 시간 날짜·시각 → UTC. 초 이하는 버린다(화면은 분 단위로만 고른다)."""
    local = datetime(day.year, day.month, day.day, at.hour, at.minute, tzinfo=user_service.KST)
    return local.astimezone(UTC)


def _resolve_place(db: Session, post: Post, data: AppointmentCreate) -> tuple[int | None, str]:
    """(장소 id, 장소 이름). 목록 장소는 글의 학교에 등록된 활성 장소여야 한다."""
    if data.meeting_place_id is None:
        return None, data.place_name  # type: ignore[return-value]  (스키마가 둘 중 하나를 보장)
    place = db.get(MeetingPlace, data.meeting_place_id)
    school_id = _post_school_id(db, post.id)
    if place is None or not place.is_active or school_id is None or place.school_id != school_id:
        raise InvalidMeetingPlaceError()
    return place.id, place.name


# ---------- 수락·거절·취소 ----------


def accept(db: Session, appointment_id: int, user: User, now: datetime | None = None) -> MessageResponse:
    return _respond(db, appointment_id, user, AppointmentEvent.ACCEPT, now)


def decline(db: Session, appointment_id: int, user: User, now: datetime | None = None) -> MessageResponse:
    return _respond(db, appointment_id, user, AppointmentEvent.DECLINE, now)


def _respond(
    db: Session, appointment_id: int, user: User, event: AppointmentEvent, now: datetime | None
) -> MessageResponse:
    """받은 사람의 수락·거절. 제안 상태이고 약속 시각 전일 때만."""
    now = now or user_service.utc_now()
    appointment, conversation = _load_for_action(db, appointment_id, user)
    if appointment.proposer_id == user.id:
        raise CannotRespondOwnAppointmentError()
    _check_not_started(appointment, now)
    if event == AppointmentEvent.ACCEPT:
        values = {"status": AppointmentStatus.ACCEPTED}
    else:
        values = {"status": AppointmentStatus.DECLINED, "active_conversation_id": None}
    _change_status(db, appointment, (AppointmentStatus.PROPOSED,), {**values, "responded_at": now})
    message = _append_event(db, conversation, user, appointment, event, EVENT_LABELS[event], now)
    db.commit()
    return _event_response(db, message, user, appointment, event, now)


def cancel(db: Session, appointment_id: int, user: User, now: datetime | None = None) -> MessageResponse:
    """제안자의 취소. 제안·수락 상태이고 약속 시각 전일 때만."""
    now = now or user_service.utc_now()
    appointment, conversation = _load_for_action(db, appointment_id, user)
    if appointment.proposer_id != user.id:
        raise NotAppointmentProposerError()
    _check_not_started(appointment, now)
    _change_status(
        db,
        appointment,
        ACTIVE_STATUSES,
        {"status": AppointmentStatus.CANCELED, "active_conversation_id": None, "responded_at": now},
    )
    message = _append_event(db, conversation, user, appointment, AppointmentEvent.CANCEL, EVENT_LABELS[AppointmentEvent.CANCEL], now)
    db.commit()
    return _event_response(db, message, user, appointment, AppointmentEvent.CANCEL, now)


def _load_for_action(db: Session, appointment_id: int, user: User) -> tuple[Appointment, Conversation]:
    """404 없는 약속 → 보내기 공통 검사(403 참여자 아님·400 탈퇴·차단·429 도배). 결과도 쪽지로 남기기 때문이다."""
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise AppointmentNotFoundError()
    conversation = conversation_service.check_can_send(db, appointment.conversation_id, user)
    return appointment, conversation


def _check_not_started(appointment: Appointment, now: datetime) -> None:
    if user_service.as_utc(appointment.starts_at) <= now:
        raise AppointmentAlreadyStartedError()


def _change_status(db: Session, appointment: Appointment, expected: tuple[AppointmentStatus, ...], values: dict) -> None:
    """지금 상태가 expected 중 하나일 때만 바꾼다. 그사이 다른 요청이 먼저 바꿨으면 409.
    읽은 값으로 판단하고 쓰면 수락과 취소가 동시에 와도 둘 다 성공해 버리므로, 조건을 UPDATE에 함께 건다.
    """
    result = db.execute(
        update(Appointment)
        .where(Appointment.id == appointment.id, Appointment.status.in_(expected))
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise AppointmentStateChangedError()
    db.refresh(appointment)


# ---------- 메시지 ----------


def summary(appointment: Appointment, label: str, now: datetime) -> str:
    """'[약속 제안] 11월 20일(목) 15:00 · 학생회관 앞'. 해가 다르면 연도도 붙인다. (한국어로 저장)"""
    local = user_service.as_utc(appointment.starts_at).astimezone(user_service.KST)
    year = f"{local.year}년 " if local.year != now.astimezone(user_service.KST).year else ""
    when = f"{year}{local.month}월 {local.day}일({WEEKDAYS[local.weekday()]}) {local:%H:%M}"
    return f"[{label}] {when} · {appointment.place_name}"


def _append_event(
    db: Session,
    conversation: Conversation,
    sender: User,
    appointment: Appointment,
    event: AppointmentEvent,
    label: str,
    now: datetime,
) -> Message:
    message = conversation_service.append_message(db, conversation, sender, summary(appointment, label, now))
    db.add(AppointmentMessage(message_id=message.id, appointment_id=appointment.id, event=event))
    return message


def _event_response(
    db: Session, message: Message, viewer: User, appointment: Appointment, event: AppointmentEvent, now: datetime
) -> MessageResponse:
    db.refresh(message)  # created_at은 DB가 채운다.
    db.refresh(appointment)
    info = conversation_service.to_appointment_response(appointment, event, viewer, now)
    return conversation_service.to_message_response(message, viewer, has_image=False, appointment=info)


# ---------- 만남 장소 ----------


def list_places(db: Session, conversation_id: int, user: User) -> list[MeetingPlace]:
    """대화방 글의 학교에 등록된 활성 장소. 글이 없거나(삭제) 학교가 없으면 빈 목록(직접 입력만)."""
    conversation = conversation_service.get_participating_conversation(db, conversation_id, user)
    if conversation.post_id is None:
        return []
    school_id = _post_school_id(db, conversation.post_id)
    if school_id is None:
        return []
    return list(
        db.scalars(
            select(MeetingPlace)
            .where(MeetingPlace.school_id == school_id, MeetingPlace.is_active.is_(True))
            .order_by(MeetingPlace.sort_order, MeetingPlace.id)
        )
    )


def _post_school_id(db: Session, post_id: int) -> int | None:
    return db.scalar(select(PostSchool.school_id).where(PostSchool.post_id == post_id))


# ---------- 종 알림 ----------


def list_reminders(db: Session, user: User, now: datetime | None = None) -> list[AppointmentReminderResponse]:
    """수락된 약속 알림: 약속 당일 한국 시간 0시부터 약속 1시간 뒤까지(약속 시각순).

    저장하지 않고 그때그때 계산한다(읽음 없음). 취소·변경되거나 시간이 지나면 저절로 빠진다.
    대화방을 나간 사람, 상대가 탈퇴한 약속은 뺀다.
    """
    now = now or user_service.utc_now()
    # "당일 0시부터" = 약속 시각이 오늘(한국 시간) 자정 전. "1시간 뒤까지" = 약속 시각이 now - 1시간 이후.
    today = now.astimezone(user_service.KST).date()
    next_midnight = datetime(today.year, today.month, today.day, tzinfo=user_service.KST) + timedelta(days=1)
    partner = aliased(User)
    partner_id = _partner_id_column(user)
    rows = db.execute(
        select(Appointment, Conversation, partner, Post.title)
        .join(Conversation, Conversation.id == Appointment.conversation_id)
        .join(partner, partner.id == partner_id)
        .outerjoin(Post, Post.id == Conversation.post_id)
        .outerjoin(
            ConversationUserState,
            (ConversationUserState.conversation_id == Conversation.id) & (ConversationUserState.user_id == user.id),
        )
        .where(
            (Conversation.buyer_id == user.id) | (Conversation.seller_id == user.id),
            Appointment.status == AppointmentStatus.ACCEPTED,
            Appointment.starts_at >= admin_dashboard_service.db_time(db, now - REMINDER_GRACE),
            Appointment.starts_at < admin_dashboard_service.db_time(db, next_midnight),
            ConversationUserState.left.is_not(True),
            partner.password_hash != user_service.WITHDRAWN_PASSWORD_HASH,
        )
        .order_by(Appointment.starts_at, Appointment.id)
    ).all()
    return [
        AppointmentReminderResponse(
            appointment_id=appointment.id,
            conversation_id=conversation.id,
            partner_nickname=other.nickname,
            post_title=post_title,
            starts_at=user_service.as_utc(appointment.starts_at),
            place_name=appointment.place_name,
        )
        for appointment, conversation, other, post_title in rows
    ]


def _partner_id_column(user: User):
    return case((Conversation.seller_id == user.id, Conversation.buyer_id), else_=Conversation.seller_id)


def _active(db: Session, conversation_id: int) -> Appointment | None:
    return db.scalar(select(Appointment).where(Appointment.active_conversation_id == conversation_id))
