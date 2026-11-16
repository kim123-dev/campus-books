from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin import ADMIN_ROUTER_OPTIONS
from app.schemas.school import AdminSchoolCreate, AdminSchoolListResponse, AdminSchoolResponse, AdminSchoolUpdate
from app.services import school_service

# 관리자 학교 관리(추가·이름/순서 수정·비활성). 관리자 검사는 공통 설정이 라우터 전체에 건다.
router = APIRouter(**ADMIN_ROUTER_OPTIONS)


@router.get("/schools", response_model=AdminSchoolListResponse, summary="학교 목록 (비활성 포함)")
def list_schools(db: Annotated[Session, Depends(get_db)]) -> AdminSchoolListResponse:
    return AdminSchoolListResponse(items=[AdminSchoolResponse.model_validate(s) for s in school_service.list_all(db)])


@router.post(
    "/schools",
    response_model=AdminSchoolResponse,
    status_code=status.HTTP_201_CREATED,
    summary="학교 추가",
    responses={409: {"description": "같은 이름의 학교가 있음"}},
)
def create_school(data: AdminSchoolCreate, db: Annotated[Session, Depends(get_db)]) -> AdminSchoolResponse:
    return AdminSchoolResponse.model_validate(school_service.create_school(db, data))


@router.patch(
    "/schools/{school_id}",
    response_model=AdminSchoolResponse,
    summary="학교 이름·순서 수정, 비활성/다시 활성",
    responses={404: {"description": "없는 학교"}, 409: {"description": "같은 이름의 학교가 있음"}},
)
def update_school(
    school_id: int, data: AdminSchoolUpdate, db: Annotated[Session, Depends(get_db)]
) -> AdminSchoolResponse:
    return AdminSchoolResponse.model_validate(school_service.update_school(db, school_id, data))
