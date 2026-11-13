from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AdminUser, require_admin
from app.models import AdminActionType, ReportStatus
from app.schemas.admin import (
    AdminActionListResponse,
    AdminDashboardResponse,
    AdminReportListResponse,
    ReportResolveRequest,
    ReportResolveResponse,
)
from app.schemas.post import PageQuery, SizeQuery
from app.routers.images import private_image_response
from app.services import admin_dashboard_service, admin_log_service, admin_service, image_storage

# 관리자 검사를 라우터 전체에 건다. 여기에 API를 추가하면 따로 적지 않아도 관리자만 쓸 수 있다.
# (테스트가 /admin으로 시작하는 모든 경로에 대해 401·403을 확인한다)
# 관리자 라우터 공통 설정. 사용자 관리·글·후기 라우터(admin_users.py, admin_content.py)도 같은 설정을 쓴다.
ADMIN_ROUTER_OPTIONS = {
    "prefix": "/admin",
    "tags": ["admin"],
    "dependencies": [Depends(require_admin)],
    "responses": {401: {"description": "로그인 필요"}, 403: {"description": "관리자가 아님"}},
}
router = APIRouter(**ADMIN_ROUTER_OPTIONS)


@router.get("/dashboard", response_model=AdminDashboardResponse, summary="대시보드 (가입자·글·미처리 신고 수)")
def get_dashboard(db: Annotated[Session, Depends(get_db)]) -> AdminDashboardResponse:
    return admin_dashboard_service.get_dashboard(db)


@router.get("/reports", response_model=AdminReportListResponse, summary="신고 목록 (미처리 먼저, 최신순)")
def list_reports(
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 1,
    size: SizeQuery = 20,
    status: Annotated[
        ReportStatus | None, Query(description="PENDING(미처리) / RESOLVED(처리됨), 생략하면 전체")
    ] = None,
    reported_user_id: Annotated[int | None, Query(ge=1, description="이 사용자가 신고당한 것만")] = None,
) -> AdminReportListResponse:
    items, total = admin_service.list_reports(db, page, size, status, reported_user_id)
    return AdminReportListResponse(items=items, total=total, page=page, size=size)


@router.post(
    "/reports/{report_id}/resolve",
    response_model=ReportResolveResponse,
    summary="신고 처리 (기각·글 삭제·기간 정지·후기 숨김). 기각 외에는 사유(note) 필수",
    responses={
        400: {"description": "사용자 신고에 글 삭제, 이미 삭제된 글, 관리자 정지, 피신고자 없음"},
        404: {"description": "없는 신고"},
        409: {"description": "이미 처리된 신고"},
        422: {"description": "조치·정지 기간·메모 형식 오류"},
    },
)
def resolve_report(
    report_id: int,
    data: ReportResolveRequest,
    admin: AdminUser,
    db: Annotated[Session, Depends(get_db)],
) -> ReportResolveResponse:
    resolved_ids, suspended_until = admin_service.resolve_report(db, report_id, admin, data)
    return ReportResolveResponse(action=data.action, resolved_ids=resolved_ids, suspended_until=suspended_until)


@router.get("/actions", response_model=AdminActionListResponse, summary="관리 기록 (최신순)")
def list_actions(
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 1,
    size: SizeQuery = 20,
    action: Annotated[AdminActionType | None, Query(description="조치 종류, 생략하면 전체")] = None,
    admin_id: Annotated[int | None, Query(ge=1, description="이 관리자가 한 조치만")] = None,
    target_user_id: Annotated[int | None, Query(ge=1, description="이 사용자에 대한 조치만")] = None,
) -> AdminActionListResponse:
    items, total = admin_log_service.list_actions(
        db, page, size, action=action, admin_id=admin_id, target_user_id=target_user_id
    )
    return AdminActionListResponse(items=items, total=total, page=page, size=size)


# 쪽지 신고에 붙은 사진. 신고 시점 사본에 남은 사진만 보여주고, 대화의 다른 사진은 볼 수 없다.
@router.get(
    "/reports/{report_id}/image",
    response_class=FileResponse,
    summary="쪽지 신고의 사진",
    responses={404: {"description": "쪽지 신고가 아니거나 사진 없음"}},
)
def get_reported_image(report_id: int, db: Annotated[Session, Depends(get_db)]) -> FileResponse:
    filename = admin_service.reported_message_image(db, report_id)
    return private_image_response(filename, image_storage.get_message_image_dir())
