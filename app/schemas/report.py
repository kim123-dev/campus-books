from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import ReportReason

MAX_REPORT_DESCRIPTION_LENGTH = 500


class ReportCreate(BaseModel):
    """신고 요청. 대상(글·사용자)은 주소로 정한다."""

    model_config = ConfigDict(extra="forbid")

    reason: ReportReason = Field(description="SPAM / FRAUD / ABUSE / INAPPROPRIATE / OTHER")
    description: str | None = Field(
        default=None, max_length=MAX_REPORT_DESCRIPTION_LENGTH, description="설명 (OTHER면 필수)"
    )

    # 빈 문자열·공백만 보내면 "설명 없음"으로 본다. 길이 검사도 앞뒤 공백을 지운 뒤에 한다.
    @field_validator("description", mode="before")
    @classmethod
    def clean_description(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or None
        return value

    # "기타"는 사유만으로는 무엇이 문제인지 알 수 없으므로 설명을 받는다.
    @model_validator(mode="after")
    def require_description_for_other(self) -> "ReportCreate":
        if self.reason == ReportReason.OTHER and self.description is None:
            raise ValueError("기타 사유는 설명을 입력해 주세요.")
        return self


class ReportCreatedResponse(BaseModel):
    """신고 접수 응답. 처리 결과나 대상 정보는 담지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
