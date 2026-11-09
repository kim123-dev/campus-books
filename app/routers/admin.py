from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AdminUser, require_admin
from app.models import ReportStatus
from app.schemas.admin import AdminReportListResponse, ReportResolveRequest, ReportResolveResponse
from app.schemas.post import PageQuery, SizeQuery
from app.services import admin_service

# 관리자 검사를 라우터 전체에 건다. 여기에 API를 추가하면 따로 적지 않아도 관리자만 쓸 수 있다.
# (테스트가 /admin으로 시작하는 모든 경로에 대해 401·403을 확인한다)
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
    responses={401: {"description": "로그인 필요"}, 403: {"description": "관리자가 아님"}},
)


@router.get("/reports", response_model=AdminReportListResponse, summary="신고 목록 (미처리 먼저, 최신순)")
def list_reports(
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 1,
    size: SizeQuery = 20,
    status: Annotated[
        ReportStatus | None, Query(description="PENDING(미처리) / RESOLVED(처리됨), 생략하면 전체")
    ] = None,
) -> AdminReportListResponse:
    items, total = admin_service.list_reports(db, page, size, status)
    return AdminReportListResponse(items=items, total=total, page=page, size=size)


@router.post(
    "/reports/{report_id}/resolve",
    response_model=ReportResolveResponse,
    summary="신고 처리 (기각·글 삭제·기간 정지)",
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
