"""거래 약속(만남 약속 카드) API. 제안·수락·거절·취소는 모두 쪽지 한 줄로 남고, 응답은 그 쪽지(MessageResponse)다.
화면은 일반 쪽지처럼 이 응답을 대화에 붙이고, appointment.id가 같은 카드를 다시 그린다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import ActiveUser, CurrentUser
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentReminderListResponse,
    MeetingPlaceListResponse,
    MeetingPlaceResponse,
)
from app.schemas.conversation import MessageResponse
from app.services import appointment_service

router = APIRouter(tags=["appointments"])

# 약속 메시지도 쪽지라서 보내기 규칙(참여자·탈퇴·차단·도배 제한)이 같다. 약속 규칙 위반은 모두 400이다.
SEND_RESPONSES: dict[int | str, dict] = {
    400: {"description": "탈퇴한 상대·차단 관계, 또는 약속 규칙 위반(글 상태·시각·장소·권한)"},
    401: {"description": "로그인 필요"},
    403: {"description": "대화 참여자가 아님, 이용 정지 중"},
    429: {"description": "짧은 시간에 너무 많이 보냄 (쪽지와 같은 제한)"},
}


@router.post(
    "/conversations/{conversation_id}/appointments",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="약속 제안 (진행 중인 약속이 있으면 변경 제안)",
    responses={
        **SEND_RESPONSES,
        404: {"description": "없는 대화방"},
        409: {"description": "동시에 다른 제안이 먼저 등록됨"},
    },
)
def propose_appointment(
    conversation_id: int,
    data: AppointmentCreate,
    current_user: ActiveUser,
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    return appointment_service.propose(db, conversation_id, current_user, data)


ACTION_RESPONSES: dict[int | str, dict] = {
    **SEND_RESPONSES,
    404: {"description": "없는 약속"},
    409: {"description": "약속 상태가 이미 바뀜"},
}


@router.post(
    "/appointments/{appointment_id}/accept",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="약속 수락 (받은 사람, 제안 상태·약속 시각 전)",
    responses=ACTION_RESPONSES,
)
def accept_appointment(
    appointment_id: int, current_user: ActiveUser, db: Annotated[Session, Depends(get_db)]
) -> MessageResponse:
    return appointment_service.accept(db, appointment_id, current_user)


@router.post(
    "/appointments/{appointment_id}/decline",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="약속 거절 (받은 사람, 제안 상태·약속 시각 전)",
    responses=ACTION_RESPONSES,
)
def decline_appointment(
    appointment_id: int, current_user: ActiveUser, db: Annotated[Session, Depends(get_db)]
) -> MessageResponse:
    return appointment_service.decline(db, appointment_id, current_user)


@router.post(
    "/appointments/{appointment_id}/cancel",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="약속 취소 (제안한 사람, 제안·수락 상태·약속 시각 전)",
    responses=ACTION_RESPONSES,
)
def cancel_appointment(
    appointment_id: int, current_user: ActiveUser, db: Annotated[Session, Depends(get_db)]
) -> MessageResponse:
    return appointment_service.cancel(db, appointment_id, current_user)


# 장소를 고르는 화면만 쓰므로 정지 중에도 볼 수 있다(CurrentUser). 실제 제안은 ActiveUser가 막는다.
@router.get(
    "/conversations/{conversation_id}/meeting-places",
    response_model=MeetingPlaceListResponse,
    summary="만남 장소 목록 (대화방 글의 학교 기준, 없으면 빈 목록)",
    responses={401: {"description": "로그인 필요"}, 403: {"description": "대화 참여자가 아님"}, 404: {"description": "없는 대화방"}},
)
def list_meeting_places(
    conversation_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> MeetingPlaceListResponse:
    places = appointment_service.list_places(db, conversation_id, current_user)
    return MeetingPlaceListResponse(items=[MeetingPlaceResponse.model_validate(p) for p in places])


@router.get(
    "/users/me/appointment-reminders",
    response_model=AppointmentReminderListResponse,
    summary="오늘의 약속 알림 (수락된 약속, 당일 0시~약속 1시간 뒤, 저장하지 않고 계산)",
    responses={401: {"description": "로그인 필요"}},
)
def list_appointment_reminders(
    current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> AppointmentReminderListResponse:
    items = appointment_service.list_reminders(db, current_user)
    return AppointmentReminderListResponse(items=items, total=len(items))
