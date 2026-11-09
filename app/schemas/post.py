import re
from datetime import datetime
from typing import Annotated, Any

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import BookCondition, PostStatus

MAX_PRICE = 10_000_000
MAX_PAGE_SIZE = 100
MAX_OPEN_CHAT_URL_LENGTH = 200

# 카카오 오픈채팅 주소만 허용한다. 접두사를 "/"까지 고정해 open.kakao.com.evil.com 같은 주소를 막고,
# 뒤쪽 글자도 URL에 흔히 쓰는 문자로 제한해 따옴표·꺾쇠·공백·역슬래시가 섞인 주소를 거절한다.
OPEN_CHAT_URL_PATTERN = re.compile(r"https://open\.kakao\.com/[A-Za-z0-9._~\-/?=&%]+")
OPEN_CHAT_URL_ERROR = "카카오 오픈채팅 주소(https://open.kakao.com/...)만 입력할 수 있습니다."

# 목록 API들이 같은 규칙을 쓰도록 쿼리 파라미터 정의를 한곳에 둔다.
# 범위를 벗어나면 FastAPI가 422를 돌려준다.
PageQuery = Annotated[int, Query(ge=1, description="페이지 번호 (1부터 시작)")]
SizeQuery = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="페이지당 글 수")]


# 작성과 수정이 같은 규칙으로 입력을 정리하도록 공용 함수로 둔다.
def _strip(value: Any) -> Any:
    """공백만 있는 필수 값을 막기 위해 길이 검사 전에 앞뒤 공백을 제거한다."""
    return value.strip() if isinstance(value, str) else value


def _blank_to_none(value: Any) -> Any:
    """선택 값은 빈 문자열과 '없음'을 구분할 이유가 없으므로 None으로 통일한다."""
    if isinstance(value, str):
        return value.strip() or None
    return value


def _check_open_chat_url(value: str | None) -> str | None:
    """javascript:, http:, 다른 도메인 주소가 링크로 저장되지 않게 형식을 검사한다."""
    if value is not None and not OPEN_CHAT_URL_PATTERN.fullmatch(value):
        raise ValueError(OPEN_CHAT_URL_ERROR)
    return value


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
    open_chat_url: str | None = Field(
        default=None, max_length=MAX_OPEN_CHAT_URL_LENGTH, description="카카오 오픈채팅 주소"
    )

    @field_validator("title", "book_title", mode="before")
    @classmethod
    def strip_required(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("course_name", "description", "open_chat_url", mode="before")
    @classmethod
    def clean_optional(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("open_chat_url")
    @classmethod
    def check_open_chat_url(cls, value: str | None) -> str | None:
        return _check_open_chat_url(value)


class PostUpdate(BaseModel):
    """판매글 수정 요청. 보낸 필드만 바뀐다. status는 상태 변경 API로만 바꾼다."""

    model_config = ConfigDict(extra="forbid")

    # 기본값 None은 '보내지 않음'을 뜻한다. 서비스에서 exclude_unset으로 보낸 필드만 반영한다.
    title: str | None = Field(default=None, min_length=1, max_length=100)
    book_title: str | None = Field(default=None, min_length=1, max_length=200)
    course_name: str | None = Field(default=None, max_length=100)
    condition: BookCondition | None = None
    price: int | None = Field(default=None, ge=0, le=MAX_PRICE, strict=True)
    description: str | None = Field(default=None, max_length=2000)
    open_chat_url: str | None = Field(
        default=None, max_length=MAX_OPEN_CHAT_URL_LENGTH, description="카카오 오픈채팅 주소"
    )

    @field_validator("title", "book_title", mode="before")
    @classmethod
    def strip_required(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("course_name", "description", "open_chat_url", mode="before")
    @classmethod
    def clean_optional(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("open_chat_url")
    @classmethod
    def check_open_chat_url(cls, value: str | None) -> str | None:
        return _check_open_chat_url(value)

    # 필수 컬럼에 null을 명시적으로 보내면 DB 제약 위반(500)이 되기 전에 422로 막는다.
    # (검증기는 직접 보낸 값에만 실행되므로, 생략한 필드는 여기에 걸리지 않는다)
    @field_validator("title", "book_title", "condition", "price")
    @classmethod
    def reject_null_for_required(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("필수 항목은 null로 바꿀 수 없습니다.")
        return value


class PostStatusUpdate(BaseModel):
    """판매 상태 변경 요청."""

    model_config = ConfigDict(extra="forbid")

    status: PostStatus


class PostSearchParams(BaseModel):
    """목록 검색 조건(쿼리 파라미터). 보낸 조건끼리는 모두 AND로 묶인다."""

    q: str | None = Field(
        default=None, max_length=100, description="제목·교재명·과목명 부분 일치 (대소문자 무시)"
    )
    status: PostStatus | None = Field(default=None, description="판매 상태")
    course_name: str | None = Field(
        default=None, max_length=100, description="과목명 정확히 일치 (대소문자 무시)"
    )
    min_price: int | None = Field(default=None, ge=0, le=MAX_PRICE, description="최소 가격 (포함)")
    max_price: int | None = Field(default=None, ge=0, le=MAX_PRICE, description="최대 가격 (포함)")

    # ?q= 처럼 빈 값이나 공백만 보내면 조건을 걸지 않은 것으로 본다.
    @field_validator("q", "course_name", mode="before")
    @classmethod
    def clean_text(cls, value: Any) -> Any:
        return _blank_to_none(value)

    # 두 필드를 함께 봐야 하는 검사라 모델 단위로 한다. 실패하면 FastAPI가 422로 바꾼다.
    @model_validator(mode="after")
    def check_price_range(self) -> "PostSearchParams":
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("min_price는 max_price보다 클 수 없습니다.")
        return self


# 사진은 static/이 아니라 이미지 전용 경로로만 내려준다. (app/routers/images.py)
IMAGE_URL_PREFIX = "/images/"


def _to_image_url(filename: Any) -> Any:
    """DB에 저장된 파일 이름을 브라우저가 쓸 주소로 바꾼다. 사진이 없으면 None 그대로."""
    return f"{IMAGE_URL_PREFIX}{filename}" if isinstance(filename, str) else filename


class PostImageResponse(BaseModel):
    """사진 한 장. 업로드 응답과 상세 응답의 images 목록이 같은 모양을 쓴다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    # ORM의 filename/thumb_filename을 읽어 주소로 바꿔 담는다.
    url: str = Field(validation_alias="filename")
    thumbnail_url: str = Field(validation_alias="thumb_filename")

    @field_validator("url", "thumbnail_url", mode="before")
    @classmethod
    def to_url(cls, value: Any) -> Any:
        return _to_image_url(value)


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
    # 목록 카드에 보여줄 첫 사진의 썸네일 주소. 사진이 없으면 null (화면은 기본 그림을 보여준다).
    thumbnail_url: str | None = Field(default=None, validation_alias="thumbnail_filename")
    created_at: datetime
    updated_at: datetime

    @field_validator("thumbnail_url", mode="before")
    @classmethod
    def to_thumbnail_url(cls, value: Any) -> Any:
        return _to_image_url(value)


class PostDetailResponse(PostResponse):
    """상세·작성·수정 응답. 연락 방법은 목록에는 넣지 않고 상세에서만 보여준다."""

    # 로그인하지 않은 요청에는 라우터가 null로 바꿔 돌려준다.
    open_chat_url: str | None
    # 보여주는 순서(slot)대로. 최대 3장.
    images: list[PostImageResponse]


class PostListResponse(BaseModel):
    """페이지네이션 목록 응답. total로 프론트가 전체 페이지 수를 계산할 수 있다."""

    items: list[PostResponse]
    total: int
    page: int
    size: int
