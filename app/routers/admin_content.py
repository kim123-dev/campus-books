from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AdminUser
from app.models import PostStatus
from app.routers.admin import ADMIN_ROUTER_OPTIONS
from app.schemas.admin import AdminPostListResponse, AdminReasonRequest, AdminReviewListResponse
from app.schemas.post import PageQuery, SizeQuery
from app.services import admin_content_service

# 관리자 글·후기 관리. 관리자 검사는 공통 설정(ADMIN_ROUTER_OPTIONS)이 라우터 전체에 건다.
router = APIRouter(**ADMIN_ROUTER_OPTIONS)


@router.get("/posts", response_model=AdminPostListResponse, summary="글 목록·검색 (최신순, 미처리 신고 수 포함)")
def list_posts(
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 1,
    size: SizeQuery = 20,
    q: Annotated[str | None, Query(max_length=100, description="제목·교재명 일부")] = None,
    status: Annotated[PostStatus | None, Query(description="판매 상태, 생략하면 전체")] = None,
    seller_id: Annotated[int | None, Query(ge=1, description="이 사용자의 글만")] = None,
) -> AdminPostListResponse:
    items, total = admin_content_service.list_posts(db, page, size, q=q, status=status, seller_id=seller_id)
    return AdminPostListResponse(items=items, total=total, page=page, size=size)


@router.get("/reviews", response_model=AdminReviewListResponse, summary="후기 목록 (최신순, 숨긴 후기 포함)")
def list_reviews(
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 1,
    size: SizeQuery = 20,
    hidden: Annotated[bool | None, Query(description="true면 숨긴 후기만, false면 보이는 후기만")] = None,
    reviewee_id: Annotated[int | None, Query(ge=1, description="이 사용자가 받은 후기만")] = None,
    reviewer_id: Annotated[int | None, Query(ge=1, description="이 사용자가 쓴 후기만")] = None,
) -> AdminReviewListResponse:
    items, total = admin_content_service.list_reviews(
        db, page, size, hidden=hidden, reviewee_id=reviewee_id, reviewer_id=reviewer_id
    )
    return AdminReviewListResponse(items=items, total=total, page=page, size=size)


@router.post(
    "/reviews/{review_id}/unhide",
    status_code=204,
    summary="후기 숨김 해제. 사유 필수",
    responses={
        404: {"description": "없는 후기"},
        409: {"description": "숨긴 후기가 아님"},
        422: {"description": "사유 형식 오류"},
    },
)
def unhide_review(
    review_id: int, data: AdminReasonRequest, admin: AdminUser, db: Annotated[Session, Depends(get_db)]
) -> None:
    admin_content_service.unhide_review(db, admin, review_id, data)
