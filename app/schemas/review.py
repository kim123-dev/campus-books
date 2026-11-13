from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.review import ReviewRating

# 후기 글자 수 제한. 화면(static/js/trade.js)과 같은 값이어야 한다.
MAX_REVIEW_LENGTH = 200


class ReviewCreate(BaseModel):
    """후기 작성 요청. 글은 선택이다."""

    model_config = ConfigDict(extra="forbid")

    rating: ReviewRating
    content: str | None = Field(default=None, max_length=MAX_REVIEW_LENGTH)

    # 앞뒤 공백을 지우고, 비어 있으면 글 없는 후기로 저장한다.
    @field_validator("content", mode="before")
    @classmethod
    def strip_content(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class RevieweeRole(StrEnum):
    """후기를 받은 사람이 그 거래에서 무엇이었는지. 프로필의 "판매자로서 / 구매자로서" 배지."""

    SELLER = "SELLER"
    BUYER = "BUYER"


class ReviewResponse(BaseModel):
    """받은 후기 한 건. 작성자는 닉네임만 보여준다(탈퇴했으면 "탈퇴한 사용자")."""

    id: int
    rating: ReviewRating
    content: str | None
    reviewer_nickname: str
    reviewee_role: RevieweeRole
    # 거래한 교재명. 글이 지워져도 거래 기록의 사본으로 보여준다.
    book_title: str
    created_at: datetime
    # 로그인한 사용자가 쓴 후기인지(신고 버튼을 숨긴다). 로그인하지 않았으면 null.
    is_mine: bool | None = None


class ReviewListResponse(BaseModel):
    items: list[ReviewResponse]
    total: int
    page: int
    size: int


class TradeReviewState(BaseModel):
    """쪽지 화면용: 이 대화방에 거래가 기록되어 있으면 후기 상태를 알려준다."""

    trade_id: int
    # 내가 이 거래에 후기를 남겼는지
    written: bool
    # 지금 후기를 남길 수 있는지 (아직 안 썼고, 기간 안이고, 상대가 탈퇴하지 않음)
    can_write: bool
    # 후기를 남길 수 있는 마지막 시각(UTC)
    deadline: datetime


class MannerSummary(BaseModel):
    """매너 학점 요약. 숨긴 후기는 빼고 센다."""

    good: int
    bad: int
    total: int
    # 좋아요 비율(%). 후기가 적으면(MIN_REVIEWS_FOR_RATIO 미만) 1~2개로 100%·0%가 뜨는 착시를 막으려고 null.
    good_ratio: int | None
    # 매너 학점(0.0~4.5, 0.1 단위)과 등급(A+~F). 후기가 없으면 기본 학점 3.5(B+)다. 계산은 review_service.
    gpa: float
    grade: str


class ProfileResponse(BaseModel):
    """판매자 프로필. 이메일·권한·정지 여부는 넣지 않는다."""

    id: int
    nickname: str
    manner: MannerSummary

