from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.models import Report
from app.schemas.report import ReportCreate, ReportCreatedResponse
from app.services import report_service

router = APIRouter(tags=["reports"])

# 신고 API의 공통 에러 응답. Swagger 문서에 보이도록 정리해 둔다.
REPORT_RESPONSES: dict[int | str, dict] = {
    401: {"description": "로그인 필요"},
    404: {"description": "없는 대상"},
    409: {"description": "이미 신고한 대상"},
    422: {"description": "사유 없음, 기타 사유에 설명 없음, 설명 500자 초과"},
    429: {"description": "신고 횟수 제한 (Retry-After 헤더)"},
}


@router.post(
    "/posts/{post_id}/reports",
    response_model=ReportCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="판매글 신고",
    responses={**REPORT_RESPONSES, 400: {"description": "본인 글"}},
)
def report_post(
    post_id: int,
    data: ReportCreate,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Report:
    return report_service.report_post(db, post_id, current_user, data)


@router.post(
    "/users/{user_id}/reports",
    response_model=ReportCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="사용자 신고",
    responses={**REPORT_RESPONSES, 400: {"description": "자기 자신"}},
)
def report_user(
    user_id: int,
    data: ReportCreate,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> Report:
    return report_service.report_user(db, user_id, current_user, data)
