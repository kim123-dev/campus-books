from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin import ADMIN_ROUTER_OPTIONS
from app.schemas.admin import AdminUserDetail, AdminUserFilter, AdminUserListResponse
from app.schemas.post import PageQuery, SizeQuery
from app.services import admin_user_service

# 관리자 사용자 관리. 관리자 검사는 공통 설정(ADMIN_ROUTER_OPTIONS)이 라우터 전체에 건다.
router = APIRouter(**ADMIN_ROUTER_OPTIONS)


@router.get("/users", response_model=AdminUserListResponse, summary="사용자 목록·검색 (가입 최신순, 이메일 포함)")
def list_users(
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 1,
    size: SizeQuery = 20,
    status: Annotated[
        AdminUserFilter | None,
        Query(description="SUSPENDED(정지 중) / ADMIN / WITHDRAWN(탈퇴), 생략하면 탈퇴하지 않은 전체"),
    ] = None,
    q: Annotated[str | None, Query(max_length=100, description="닉네임·이메일 일부 또는 사용자 번호")] = None,
) -> AdminUserListResponse:
    items, total = admin_user_service.list_users(db, page, size, status=status, q=q)
    return AdminUserListResponse(items=items, total=total, page=page, size=size)


@router.get(
    "/users/{user_id}",
    response_model=AdminUserDetail,
    summary="사용자 상세 (글·신고·후기 수, 정지 이력)",
    responses={404: {"description": "없는 사용자"}},
)
def get_user(user_id: int, db: Annotated[Session, Depends(get_db)]) -> AdminUserDetail:
    return admin_user_service.get_user(db, user_id)
