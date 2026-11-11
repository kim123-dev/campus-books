from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AdminUser
from app.routers.admin import ADMIN_ROUTER_OPTIONS
from app.schemas.admin import (
    AdminEmailBanListResponse,
    AdminEmailUnbanRequest,
    AdminReasonRequest,
    AdminSuspendRequest,
    AdminSuspendResponse,
    AdminUserDetail,
    AdminUserFilter,
    AdminUserListResponse,
    AdminWithdrawRequest,
    AdminWithdrawResponse,
)
from app.schemas.post import PageQuery, SizeQuery
from app.services import admin_user_service, email_ban_service

# 관리자 사용자 관리(정지·강제 탈퇴·재가입 차단 포함). 관리자 검사는 공통 설정(ADMIN_ROUTER_OPTIONS)이 라우터 전체에 건다.
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


@router.post(
    "/users/{user_id}/suspend",
    response_model=AdminSuspendResponse,
    summary="기간 정지 (신고 없이 직접). 사유 필수, 더 긴 정지가 있으면 줄이지 않는다",
    responses={
        400: {"description": "관리자(자기 자신 포함)는 정지할 수 없음"},
        404: {"description": "없는 사용자"},
        409: {"description": "탈퇴한 사용자"},
        422: {"description": "일수(1~365)·사유 형식 오류"},
    },
)
def suspend_user(
    user_id: int, data: AdminSuspendRequest, admin: AdminUser, db: Annotated[Session, Depends(get_db)]
) -> AdminSuspendResponse:
    return AdminSuspendResponse(suspended_until=admin_user_service.suspend(db, admin, user_id, data))


@router.post(
    "/users/{user_id}/unsuspend",
    response_model=AdminSuspendResponse,
    summary="정지 해제. 사유 필수",
    responses={
        404: {"description": "없는 사용자"},
        409: {"description": "탈퇴한 사용자, 정지 중이 아님"},
        422: {"description": "사유 형식 오류"},
    },
)
def unsuspend_user(
    user_id: int, data: AdminReasonRequest, admin: AdminUser, db: Annotated[Session, Depends(get_db)]
) -> AdminSuspendResponse:
    admin_user_service.unsuspend(db, admin, user_id, data)
    return AdminSuspendResponse(suspended_until=None)


@router.post(
    "/users/{user_id}/withdraw",
    response_model=AdminWithdrawResponse,
    summary="강제 탈퇴. 사유 필수, 기본으로 같은 이메일의 재가입도 막는다",
    responses={
        400: {"description": "관리자(자기 자신 포함)는 강제 탈퇴할 수 없음"},
        404: {"description": "없는 사용자"},
        409: {"description": "이미 탈퇴한 사용자"},
        422: {"description": "사유 형식 오류"},
    },
)
def withdraw_user(
    user_id: int, data: AdminWithdrawRequest, admin: AdminUser, db: Annotated[Session, Depends(get_db)]
) -> AdminWithdrawResponse:
    banned, deleted_posts = admin_user_service.force_withdraw(db, admin, user_id, data)
    return AdminWithdrawResponse(email_banned=banned, deleted_posts=deleted_posts)


@router.get("/email-bans", response_model=AdminEmailBanListResponse, summary="재가입 차단 목록 (차단 시각·사유만)")
def list_email_bans(
    db: Annotated[Session, Depends(get_db)], page: PageQuery = 1, size: SizeQuery = 20
) -> AdminEmailBanListResponse:
    items, total = email_ban_service.list_bans(db, page, size)
    return AdminEmailBanListResponse(items=items, total=total, page=page, size=size)


@router.post(
    "/email-bans/unban",
    status_code=204,
    summary="재가입 차단 해제. 관리자가 이메일을 입력하면 해시로 찾는다. 사유 필수",
    responses={404: {"description": "차단 목록에 없는 이메일"}, 422: {"description": "이메일·사유 형식 오류"}},
)
def unban_email(data: AdminEmailUnbanRequest, admin: AdminUser, db: Annotated[Session, Depends(get_db)]) -> None:
    email_ban_service.unban(db, admin, data)
