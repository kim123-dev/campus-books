from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import ActiveUser, CurrentUser
from app.models import User
from app.schemas.post import SchoolBrief
from app.schemas.school import MySchoolResponse, MySchoolUpdate, SchoolListResponse, SchoolResponse
from app.services import school_service

router = APIRouter(tags=["schools"])


@router.get("/schools", response_model=SchoolListResponse, summary="학교 목록 (활성 학교만, 로그인 불필요)")
def list_schools(db: Annotated[Session, Depends(get_db)]) -> SchoolListResponse:
    return SchoolListResponse(items=[SchoolResponse.model_validate(s) for s in school_service.list_active(db)])


@router.get(
    "/users/me/school",
    response_model=MySchoolResponse,
    summary="내 학교",
    responses={401: {"description": "로그인 필요"}},
)
def read_my_school(current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> MySchoolResponse:
    return _my_school(db, current_user)


# 정지 중에는 바꿀 수 없다(403). 닉네임 변경과 같은 기준이다.
@router.put(
    "/users/me/school",
    response_model=MySchoolResponse,
    summary="내 학교 변경 (7일에 한 번, null이면 비움)",
    responses={
        400: {"description": "지금과 같음, 7일 안에 이미 바꿈, 비활성 학교"},
        401: {"description": "로그인 필요"},
        403: {"description": "이용 정지 중"},
        404: {"description": "없는 학교"},
    },
)
def update_my_school(
    data: MySchoolUpdate, current_user: ActiveUser, db: Annotated[Session, Depends(get_db)]
) -> MySchoolResponse:
    school_service.change_user_school(db, current_user, data.school_id)
    return _my_school(db, current_user)


def _my_school(db: Session, user: User) -> MySchoolResponse:
    row = school_service.get_user_school(db, user)
    school = school_service.school_of(db, row)
    return MySchoolResponse(
        school=SchoolBrief.model_validate(school) if school is not None else None,
        changeable_at=school_service.changeable_at(row),
    )
