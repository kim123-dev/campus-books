"""관리자 신고 처리 API의 요청·응답. 사용자 정보는 닉네임까지만 담고 이메일은 넣지 않는다."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import ReportAction, ReportReason, ReportStatus, ReportTargetType

MAX_RESOLUTION_NOTE_LENGTH = 500
MAX_SUSPEND_DAYS = 365


# ---------- 요청 ----------


class ReportResolveRequest(BaseModel):
    """신고 처리 요청."""

    model_config = ConfigDict(extra="forbid")

    action: ReportAction = Field(description="DISMISS(기각) / DELETE_POST(글 삭제) / SUSPEND(기간 정지)")
    suspend_days: int | None = Field(
        default=None, ge=1, le=MAX_SUSPEND_DAYS, description="정지 일수 (SUSPEND일 때만, 필수)"
    )
    note: str | None = Field(default=None, max_length=MAX_RESOLUTION_NOTE_LENGTH, description="처리 메모 (선택)")
    include_same_user: bool = Field(
        default=False,
        description="같은 피신고자의 다른 미처리 신고도 같은 조치로 함께 처리 (DISMISS·SUSPEND만)",
    )

    # 공백만 보낸 메모는 "메모 없음"으로 본다.
    @field_validator("note", mode="before")
    @classmethod
    def clean_note(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def check_action_options(self) -> "ReportResolveRequest":
        if self.action == ReportAction.SUSPEND and self.suspend_days is None:
            raise ValueError("정지 기간(일)을 입력해 주세요.")
        if self.action != ReportAction.SUSPEND and self.suspend_days is not None:
            raise ValueError("정지 기간은 정지 조치에만 넣을 수 있습니다.")
        # 글 삭제는 그 글 하나에 대한 조치라, 다른 글·사용자 신고까지 "글 삭제"로 기록하면 사실과 달라진다.
        # (같은 글에 대한 다른 신고는 글이 없어지므로 서버가 자동으로 함께 처리한다)
        if self.action == ReportAction.DELETE_POST and self.include_same_user:
            raise ValueError("글 삭제는 같은 사용자의 다른 신고와 함께 처리할 수 없습니다.")
        return self


# ---------- 응답 ----------


class AdminUserBrief(BaseModel):
    """신고 목록의 사용자. 닉네임까지만 보여준다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nickname: str


class ReportedUserBrief(AdminUserBrief):
    # 지금 정지 중이면 종료 시각(UTC), 아니면 null.
    suspended_until: datetime | None = None


class ReportResolution(BaseModel):
    """처리 기록."""

    action: ReportAction
    note: str | None
    resolved_by: AdminUserBrief | None  # 처리한 관리자 계정이 지워졌으면 null
    resolved_at: datetime
    resolved_with_report_id: int | None  # 다른 신고와 함께 처리됐으면 그 신고 번호


class AdminReportResponse(BaseModel):
    """관리 화면의 신고 한 건."""

    id: int
    target_type: ReportTargetType
    target_id: int
    reason: ReportReason
    description: str | None
    post_title_snapshot: str | None
    post_content_snapshot: str | None
    # 글 신고에서 그 글이 아직 있는지. 사용자 신고면 null. (글 삭제 버튼을 보여줄지 정한다)
    post_exists: bool | None
    reporter: AdminUserBrief | None  # 신고자가 탈퇴했으면 null
    reported_user: ReportedUserBrief | None
    status: ReportStatus
    created_at: datetime
    resolution: ReportResolution | None
    # 같은 피신고자에 대한, 이 신고를 뺀 미처리 신고 수. "함께 처리"를 고를지 판단하는 데 쓴다.
    other_pending_count: int


class AdminReportListResponse(BaseModel):
    items: list[AdminReportResponse]
    total: int
    page: int
    size: int


class ReportResolveResponse(BaseModel):
    """처리 결과."""

    action: ReportAction
    # 처리된 신고 번호. 첫 번째가 요청한 신고이고, 나머지는 함께 처리된 신고다.
    resolved_ids: list[int]
    # SUSPEND일 때 실제 정지 종료 시각(UTC). 이미 더 긴 정지가 있으면 그 시각이다.
    suspended_until: datetime | None = None
