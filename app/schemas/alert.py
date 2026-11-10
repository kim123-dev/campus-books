from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import PostStatus
from app.schemas.post import MAX_PRICE, _to_image_url

# 1글자 키워드는 너무 많은 글에 걸려 알림이 쏟아지므로 2글자부터 받는다.
MIN_KEYWORD_LENGTH = 2
# 검색어(q)와 같은 최대 길이
MAX_KEYWORD_LENGTH = 100


class AlertCreate(BaseModel):
    """찾는 교재 등록 요청."""

    model_config = ConfigDict(extra="forbid")

    keyword: str = Field(
        min_length=MIN_KEYWORD_LENGTH,
        max_length=MAX_KEYWORD_LENGTH,
        description="교재명·과목명 부분 일치 (대소문자 무시, 글 제목은 보지 않는다)",
    )
    max_price: int | None = Field(default=None, ge=0, le=MAX_PRICE, strict=True, description="최대 가격 (포함)")

    # 공백만 넣은 키워드를 길이 검사에서 걸러내기 위해 먼저 앞뒤 공백을 지운다.
    @field_validator("keyword", mode="before")
    @classmethod
    def strip_keyword(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    keyword: str
    max_price: int | None
    created_at: datetime


class AlertListResponse(BaseModel):
    """내 조건 목록. 최대 개수가 작아 페이지를 나누지 않는다. 화면은 max_count로 "3/10"을 보여준다."""

    items: list[AlertResponse]
    max_count: int


class NotificationPostResponse(BaseModel):
    """알림 카드에 보여줄 글 요약. 판매 상태는 지금 상태다. (알림 뒤 예약·판매 완료될 수 있다)"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    book_title: str
    course_name: str | None
    price: int
    status: PostStatus
    thumbnail_url: str | None = Field(default=None, validation_alias="thumbnail_filename")

    @field_validator("thumbnail_url", mode="before")
    @classmethod
    def to_thumbnail_url(cls, value: Any) -> Any:
        return _to_image_url(value)


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    keyword: str
    post: NotificationPostResponse
    created_at: datetime
    read_at: datetime | None


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    page: int
    size: int


class NotificationUnreadCountResponse(BaseModel):
    unread_count: int
