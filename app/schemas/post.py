from datetime import datetime
from typing import Annotated, Any

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import BookCondition, PostStatus

MAX_PRICE = 10_000_000
MAX_PAGE_SIZE = 100

# 목록 API들이 같은 규칙을 쓰도록 쿼리 파라미터 정의를 한곳에 둔다.
# 범위를 벗어나면 FastAPI가 422를 돌려준다.
PageQuery = Annotated[int, Query(ge=1, description="페이지 번호 (1부터 시작)")]
SizeQuery = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="페이지당 글 수")]


class PostCreate(BaseModel):
    """판매글 작성 요청. status는 서버가 정하므로 받지 않는다."""

    # 모르는 필드(status 등)를 조용히 무시하지 않고 422로 알려준다.
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=100)
    book_title: str = Field(min_length=1, max_length=200, description="교재명")
    course_name: str | None = Field(default=None, max_length=100, description="과목명")
    condition: BookCondition = Field(description="책 상태 (GOOD/FAIR/POOR)")
    # strict: "1000" 같은 문자열이나 1000.5 같은 실수를 정수로 바꾸지 않고 거절한다.
    price: int = Field(ge=0, le=MAX_PRICE, strict=True, description="가격 (원)")
    description: str | None = Field(default=None, max_length=2000)

    # 공백만 있는 필수 값을 막기 위해 길이 검사 전에 앞뒤 공백을 제거한다.
    @field_validator("title", "book_title", mode="before")
    @classmethod
    def strip_required(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    # 선택 값은 빈 문자열과 '없음'을 구분할 이유가 없으므로 None으로 통일한다.
    @field_validator("course_name", "description", mode="before")
    @classmethod
    def blank_to_none(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class SellerResponse(BaseModel):
    """글에 함께 보여줄 판매자 정보. 이메일은 노출하지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nickname: str


class PostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    book_title: str
    course_name: str | None
    condition: BookCondition
    price: int
    description: str | None
    status: PostStatus
    seller: SellerResponse
    created_at: datetime
    updated_at: datetime


class PostListResponse(BaseModel):
    """페이지네이션 목록 응답. total로 프론트가 전체 페이지 수를 계산할 수 있다."""

    items: list[PostResponse]
    total: int
    page: int
    size: int
