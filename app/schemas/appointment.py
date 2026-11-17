"""거래 약속(만남 약속 카드) 요청·응답."""

import datetime as dt
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.appointment import AppointmentEvent, AppointmentStatus

MAX_PLACE_LENGTH = 100


class AppointmentCreate(BaseModel):
    """약속 제안. 날짜·시각은 한국 시간(KST)으로 받는다. 장소는 목록에서 고르거나(meeting_place_id) 직접 입력(place_name) 중 하나."""

    model_config = ConfigDict(extra="forbid")

    date: dt.date = Field(description="약속 날짜 (한국 시간, YYYY-MM-DD)")
    time: dt.time = Field(description="약속 시각 (한국 시간, HH:MM). 초는 버린다.")
    meeting_place_id: int | None = Field(default=None, ge=1, description="만남 장소 목록에서 고른 장소")
    place_name: str | None = Field(default=None, max_length=MAX_PLACE_LENGTH, description="직접 입력한 장소")

    # 공백만 보낸 장소는 입력하지 않은 것으로 본다.
    @field_validator("place_name", mode="before")
    @classmethod
    def strip_place(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    # 장소는 둘 중 정확히 하나. 둘 다 오면 어느 쪽을 믿을지 애매하므로 422로 돌려보낸다.
    @model_validator(mode="after")
    def check_one_place(self) -> "AppointmentCreate":
        if (self.meeting_place_id is None) == (self.place_name is None):
            raise ValueError("장소는 목록에서 고르거나 직접 입력하는 것 중 하나만 보내 주세요.")
        return self


class MessageAppointmentResponse(BaseModel):
    """약속 메시지에 붙는 정보. event는 이 메시지가 알리는 일, 나머지는 약속의 지금 상태다.
    화면은 같은 id의 카드를 이 값으로 다시 그린다. (수락 메시지를 받으면 앞의 제안 카드도 "수락됨"으로)
    """

    event: AppointmentEvent
    id: int
    status: AppointmentStatus
    starts_at: datetime
    place_name: str
    meeting_place_id: int | None
    proposer_id: int
    # 내가 제안했는지. 받은 쪽에만 수락·거절 버튼을 보여준다.
    is_mine: bool
    # 약속 시각이 지났는지("지남"). 저장하지 않고 응답할 때 계산한다.
    is_past: bool
    # 이 제안이 바꾼 이전 약속. 화면이 이전 카드를 "변경됨"으로 다시 그린다.
    replaces_id: int | None


class MeetingPlaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class MeetingPlaceListResponse(BaseModel):
    """대화방 글의 학교에 등록된 만남 장소(활성만). 글에 학교가 없거나 목록이 비면 빈 배열."""

    items: list[MeetingPlaceResponse]


class AppointmentReminderResponse(BaseModel):
    """종 알림 판의 약속 항목. 저장하지 않고 그때그때 계산한다."""

    appointment_id: int
    conversation_id: int
    partner_nickname: str
    # 글이 삭제되었으면 null
    post_title: str | None
    starts_at: datetime
    place_name: str


class AppointmentReminderListResponse(BaseModel):
    items: list[AppointmentReminderResponse]
    total: int
