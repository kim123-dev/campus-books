from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import PostStatus

MAX_MESSAGE_LENGTH = 1000
DEFAULT_MESSAGE_LIMIT = 50
MAX_MESSAGE_LIMIT = 100


class ConversationRole(StrEnum):
    """대화방에서 내 역할. 화면이 "문의한 글"과 "받은 문의"를 나눠 보여줄 수 있게 한다."""

    BUYER = "BUYER"
    SELLER = "SELLER"


# ---------- 요청 ----------


class MessageCreate(BaseModel):
    """메시지 전송 요청."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)

    # 공백만 있는 메시지를 길이 검사(min_length=1)에서 걸러내기 위해 먼저 앞뒤 공백을 지운다.
    # 문장 사이 줄바꿈은 그대로 둔다.
    @field_validator("content", mode="before")
    @classmethod
    def strip_content(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class MessageListParams(BaseModel):
    """메시지 목록 커서(쿼리 파라미터).

    쪽지는 새 메시지가 계속 추가되므로, 페이지 번호 방식이면 페이지 경계가 밀려 중복·누락이 생긴다.
    그래서 메시지 id를 기준으로 그 이후(after_id)나 이전(before_id)을 가져온다.
    """

    after_id: int | None = Field(default=None, ge=1, description="이 id보다 새 메시지 (새 메시지 확인용)")
    before_id: int | None = Field(default=None, ge=1, description="이 id보다 오래된 메시지 (이전 대화 보기용)")
    limit: int = Field(default=DEFAULT_MESSAGE_LIMIT, ge=1, le=MAX_MESSAGE_LIMIT, description="최대 개수")

    @model_validator(mode="after")
    def check_single_cursor(self) -> "MessageListParams":
        if self.after_id is not None and self.before_id is not None:
            raise ValueError("after_id와 before_id는 함께 보낼 수 없습니다.")
        return self


# ---------- 응답 ----------


class PartnerResponse(BaseModel):
    """대화 상대. 이메일 등 개인정보는 넣지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nickname: str
    # 탈퇴했으면 true. 화면은 신고·차단 버튼을 숨긴다. (nickname은 "탈퇴한 사용자")
    withdrawn: bool = False


class ConversationPostResponse(BaseModel):
    """대화방이 어떤 글에 대한 것인지. 글이 삭제되면 대화방 응답에서 null이 된다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: PostStatus


class LastMessageResponse(BaseModel):
    content: str
    is_mine: bool
    created_at: datetime


class ConversationResponse(BaseModel):
    """대화방 요약. 목록과 대화방 정보 API가 같은 형식을 쓴다."""

    id: int
    post: ConversationPostResponse | None
    partner: PartnerResponse
    my_role: ConversationRole
    last_message: LastMessageResponse | None
    unread_count: int
    created_at: datetime
    last_message_at: datetime


class ConversationDetailResponse(ConversationResponse):
    """대화방 하나(대화 화면용). 목록에는 넣지 않아, 목록 요청의 쿼리 수를 늘리지 않는다."""

    # 둘 중 한 명이라도 상대를 차단했으면 false. 대화 화면은 입력창을 잠근다.
    can_send: bool
    # 내가 상대를 차단했는지. true면 화면에 "차단 해제"를 보여준다.
    # 상대가 나를 차단했는지는 따로 알려주지 않는다. (can_send만 false)
    blocked_by_me: bool


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int
    page: int
    size: int


class UnreadCountResponse(BaseModel):
    """헤더 배지용. 내가 참여한 모든 대화방에서 상대가 보낸 안 읽은 메시지 수."""

    unread_count: int


class MessageResponse(BaseModel):
    id: int
    sender_id: int
    # 화면이 내 말풍선과 상대 말풍선을 나눌 때 내 id를 따로 알 필요가 없게 한다.
    is_mine: bool
    content: str
    created_at: datetime
    # 받는 사람이 읽은 시각. 내가 보낸 메시지에서는 "읽음" 표시에 쓴다.
    read_at: datetime | None


class MessageListResponse(BaseModel):
    """메시지 목록. items는 오래된 것부터 정렬된다."""

    items: list[MessageResponse]
    # 같은 방향으로 더 가져올 메시지가 있는지. (after_id면 더 새 것, 그 밖에는 더 오래된 것)
    has_more: bool
