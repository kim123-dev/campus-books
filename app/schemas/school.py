from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.post import SchoolBrief


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


class SchoolResponse(SchoolBrief):
    """공개 학교 목록(GET /schools)의 한 항목. 활성 학교만 내려준다."""


class SchoolListResponse(BaseModel):
    items: list[SchoolResponse]


class MySchoolResponse(BaseModel):
    """내 학교. 없으면 school이 null."""

    school: SchoolBrief | None
    # 다시 바꿀 수 있는 시각(UTC). 지금 바꿀 수 있으면 null. (닉네임 변경 제한과 같은 방식)
    changeable_at: datetime | None


class MySchoolUpdate(BaseModel):
    """내 학교 변경. null을 보내면 학교를 비운다. 필드 자체는 꼭 보내야 한다(실수로 비우지 않게)."""

    model_config = ConfigDict(extra="forbid")

    school_id: int | None = Field(ge=1, description="학교 번호, 비우려면 null")


# ---------- 관리자 ----------


class AdminSchoolResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sort_order: int
    is_active: bool
    created_at: datetime


class AdminSchoolListResponse(BaseModel):
    items: list[AdminSchoolResponse]


class AdminSchoolCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(default=0, ge=0, le=9999)

    _strip_name = field_validator("name", mode="before")(_strip)


class AdminSchoolUpdate(BaseModel):
    """보낸 필드만 바꾼다. 비활성(is_active=false)이면 새로 고를 수 없지만 이미 연결된 글·사용자 표시는 남는다."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    sort_order: int | None = Field(default=None, ge=0, le=9999)
    is_active: bool | None = None

    _strip_name = field_validator("name", mode="before")(_strip)
