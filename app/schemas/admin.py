"""관리자 API의 요청·응답. 이메일은 사용자 관리 API(/admin/users)에만 담는다."""

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import (
    AdminActionType,
    AdminTargetType,
    PostStatus,
    ReportAction,
    ReportReason,
    ReportStatus,
    ReportTargetType,
    ReviewRating,
    UserRole,
)

MAX_RESOLUTION_NOTE_LENGTH = 500
MAX_SUSPEND_DAYS = 365
MAX_REASON_LENGTH = 500
# 사유를 꼭 적어야 하는 신고 처리. 기각은 조치가 없으므로 선택이다.
REASON_REQUIRED_ACTIONS = {ReportAction.DELETE_POST, ReportAction.SUSPEND, ReportAction.HIDE_REVIEW}


# ---------- 요청 ----------


class ReportResolveRequest(BaseModel):
    """신고 처리 요청."""

    model_config = ConfigDict(extra="forbid")

    action: ReportAction = Field(
        description="DISMISS(기각) / DELETE_POST(글 삭제) / SUSPEND(기간 정지) / HIDE_REVIEW(후기 숨김)"
    )
    suspend_days: int | None = Field(
        default=None, ge=1, le=MAX_SUSPEND_DAYS, description="정지 일수 (SUSPEND일 때만, 필수)"
    )
    note: str | None = Field(
        default=None,
        max_length=MAX_RESOLUTION_NOTE_LENGTH,
        description="처리 사유. 글 삭제·정지·후기 숨김은 필수, 기각은 선택",
    )
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
        # 강제 조치는 나중에 왜 했는지 확인할 수 있게 사유를 꼭 남긴다. (관리 기록에도 그대로 들어간다)
        if self.action in REASON_REQUIRED_ACTIONS and self.note is None:
            raise ValueError("글 삭제·정지·후기 숨김은 처리 사유를 입력해 주세요.")
        if self.action == ReportAction.SUSPEND and self.suspend_days is None:
            raise ValueError("정지 기간(일)을 입력해 주세요.")
        if self.action != ReportAction.SUSPEND and self.suspend_days is not None:
            raise ValueError("정지 기간은 정지 조치에만 넣을 수 있습니다.")
        # 글 삭제는 그 글 하나에 대한 조치라, 다른 글·사용자 신고까지 "글 삭제"로 기록하면 사실과 달라진다.
        # (같은 글에 대한 다른 신고는 글이 없어지므로 서버가 자동으로 함께 처리한다)
        if self.action == ReportAction.DELETE_POST and self.include_same_user:
            raise ValueError("글 삭제는 같은 사용자의 다른 신고와 함께 처리할 수 없습니다.")
        # 후기 숨김도 그 후기 하나에 대한 조치다. (같은 후기에 대한 다른 신고는 서버가 함께 처리한다)
        if self.action == ReportAction.HIDE_REVIEW and self.include_same_user:
            raise ValueError("후기 숨김은 같은 사용자의 다른 신고와 함께 처리할 수 없습니다.")
        return self


def _clean_text(value: Any) -> Any:
    # 공백만 보낸 사유는 "사유 없음"으로 보고 길이 검사(min_length=1)에서 422가 되게 한다.
    return value.strip() if isinstance(value, str) else value


class AdminReasonRequest(BaseModel):
    """사유만 받는 관리자 조치 요청 (정지 해제, 후기 숨김 해제, 글 삭제, 강제 탈퇴 등)."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=MAX_REASON_LENGTH, description="조치 사유 (필수)")

    @field_validator("reason", mode="before")
    @classmethod
    def clean_reason(cls, value: Any) -> Any:
        return _clean_text(value)


class AdminSuspendRequest(AdminReasonRequest):
    """사용자 직접 정지. 신고 없이도 관리자가 정지할 수 있다."""

    days: int = Field(ge=1, le=MAX_SUSPEND_DAYS, description="정지 일수 (1~365)")


# ---------- 응답 ----------


class AdminUserBrief(BaseModel):
    """신고 목록의 사용자. 닉네임까지만 보여준다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nickname: str


class AdminUserRef(AdminUserBrief):
    """관리 화면의 사용자 표시. 탈퇴한 사용자는 닉네임 대신 "탈퇴한 사용자"이고 withdrawn이 true다."""

    withdrawn: bool = False


class ReportedUserBrief(AdminUserBrief):
    # 지금 정지 중이면 종료 시각(UTC), 아니면 null.
    suspended_until: datetime | None = None


class AdminReviewBrief(BaseModel):
    """후기 신고의 대상 후기. 작성자는 피신고자(reported_user)로 따로 보여준다."""

    rating: ReviewRating
    content: str | None
    book_title: str
    reviewee: AdminUserBrief | None  # 후기를 받은 사람. 탈퇴했으면 null
    hidden: bool  # 이미 숨긴 후기인지


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
    # 글 신고에서 그 글이 아직 있는지. 사용자·후기 신고면 null. (글 삭제 버튼을 보여줄지 정한다)
    post_exists: bool | None
    # 후기 신고의 대상 후기. 다른 신고면 null.
    review: AdminReviewBrief | None = None
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


class AdminActionResponse(BaseModel):
    """관리 기록 한 줄."""

    id: int
    action: AdminActionType
    admin: AdminUserRef | None  # 조치한 관리자. 계정이 지워졌으면 null
    target_type: AdminTargetType
    target_id: int
    target_user: AdminUserRef | None  # 조치와 관련된 사용자. 없으면 null
    reason: str | None  # 신고 기각만 비어 있을 수 있다
    detail: dict[str, Any]  # 신고 번호, 정지 일수, 지운 글 제목 등
    created_at: datetime


class AdminActionListResponse(BaseModel):
    items: list[AdminActionResponse]
    total: int
    page: int
    size: int


# ---------- 대시보드 ----------


class DashboardUserCounts(BaseModel):
    total: int  # 탈퇴하지 않은 가입자 (관리자 포함)
    suspended: int  # 지금 정지 중
    admins: int
    withdrawn: int  # 탈퇴한 계정 (익명화되어 남은 행)


class DashboardPostCounts(BaseModel):
    total: int
    on_sale: int
    reserved: int
    sold: int


class DashboardPeriodCounts(BaseModel):
    today: int  # 한국 시간 오늘 자정부터
    last_7_days: int  # 오늘을 포함한 최근 7일


class AdminDashboardResponse(BaseModel):
    today: date  # 기준 날짜 (한국 시간)
    users: DashboardUserCounts
    posts: DashboardPostCounts
    signups: DashboardPeriodCounts
    new_posts: DashboardPeriodCounts
    pending_reports: int


# ---------- 사용자 관리 ----------


class AdminUserFilter(StrEnum):
    """사용자 목록 필터. 생략하면 탈퇴한 계정을 뺀 전체."""

    SUSPENDED = "SUSPENDED"  # 지금 정지 중
    ADMIN = "ADMIN"
    WITHDRAWN = "WITHDRAWN"  # 탈퇴한 계정 (스스로 탈퇴 + 강제 탈퇴)


class AdminUserItem(BaseModel):
    """사용자 목록의 한 줄. 이메일은 관리자 API 중 사용자 관리에만 담는다. 탈퇴한 계정은 이메일이 null이다."""

    id: int
    email: str | None
    nickname: str  # 탈퇴했으면 "탈퇴한 사용자"
    role: UserRole
    created_at: datetime
    suspended_until: datetime | None  # 지금 정지 중이면 종료 시각(UTC)
    withdrawn: bool
    post_count: int
    pending_report_count: int  # 이 사용자에 대한 미처리 신고 수


class AdminUserListResponse(BaseModel):
    items: list[AdminUserItem]
    total: int
    page: int
    size: int


class AdminUserCounts(BaseModel):
    posts: int
    reports_received: int
    reports_pending: int
    reviews_received: int
    reviews_hidden: int  # 받은 후기 중 숨긴 것
    reviews_written: int


class AdminUserDetail(AdminUserItem):
    counts: AdminUserCounts
    # 정지·정지 해제 이력 (관리 기록에서, 최신순). 관리 기록 기능 전의 정지는 남아 있지 않다.
    suspensions: list[AdminActionResponse]


# ---------- 글·후기 관리 ----------


class AdminPostItem(BaseModel):
    id: int
    title: str
    book_title: str
    price: int
    status: PostStatus
    created_at: datetime
    seller: AdminUserRef
    pending_report_count: int  # 이 글에 대한 미처리 신고 수


class AdminPostListResponse(BaseModel):
    items: list[AdminPostItem]
    total: int
    page: int
    size: int


class AdminReviewItem(BaseModel):
    id: int
    rating: ReviewRating
    content: str | None
    book_title: str
    reviewer: AdminUserRef  # 후기를 쓴 사람
    reviewee: AdminUserRef  # 후기를 받은 사람
    created_at: datetime
    hidden_at: datetime | None  # 숨겼으면 숨긴 시각


class AdminReviewListResponse(BaseModel):
    items: list[AdminReviewItem]
    total: int
    page: int
    size: int


class AdminSuspendResponse(BaseModel):
    # 정지 종료 시각(UTC). 이미 더 늦게 끝나는 정지가 있으면 그 시각이다. 정지 해제면 null.
    suspended_until: datetime | None
