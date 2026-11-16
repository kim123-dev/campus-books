"""학교: 공개 목록, 기본 학교 넣기, 관리자 추가·수정, 내 학교(7일 제한), 글의 학교."""

from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    DuplicateSchoolNameError,
    InactiveSchoolError,
    SameSchoolError,
    SchoolChangeTooSoonError,
    SchoolNotFoundError,
)
from app.models import Post, PostSchool, School, User, UserSchool
from app.schemas.school import AdminSchoolCreate, AdminSchoolUpdate
from app.services import user_service

# 앱을 처음 띄울 때 넣는 학교. 이미 있으면 건너뛴다.
DEFAULT_SCHOOL_NAME = "울산과학대학교"
# 학교를 자주 바꾸면 학교 필터의 의미가 흐려진다. 닉네임(30일)보다는 짧게 둔다.
SCHOOL_CHANGE_INTERVAL = timedelta(days=7)


def seed_default(db: Session) -> None:
    """기본 학교를 넣는다(앱 시작 시). 이름이 같은 학교가 이미 있으면 아무것도 하지 않는다."""
    if db.scalar(select(School.id).where(School.name == DEFAULT_SCHOOL_NAME)) is not None:
        return
    db.add(School(name=DEFAULT_SCHOOL_NAME))
    try:
        db.commit()
    except IntegrityError:
        # 서버 여러 대가 동시에 시작해 같은 이름을 넣으면 unique 제약이 하나만 남긴다.
        db.rollback()


def _ordered():
    return select(School).order_by(School.sort_order, School.name, School.id)


def list_active(db: Session) -> list[School]:
    """화면의 학교 선택 목록. 비활성 학교는 뺀다."""
    return list(db.scalars(_ordered().where(School.is_active.is_(True))).all())


def list_all(db: Session) -> list[School]:
    """관리자 목록. 비활성 학교도 보여준다."""
    return list(db.scalars(_ordered()).all())


def get_selectable(db: Session, school_id: int) -> School:
    """새로 고를 수 있는 학교. 없으면 404, 비활성이면 400."""
    school = db.get(School, school_id)
    if school is None:
        raise SchoolNotFoundError()
    if not school.is_active:
        raise InactiveSchoolError()
    return school


# ---------- 관리자 ----------


def create_school(db: Session, data: AdminSchoolCreate) -> School:
    """학교 추가. 같은 이름이면 409."""
    school = School(name=data.name, sort_order=data.sort_order)
    db.add(school)
    _commit_unique_name(db)
    db.refresh(school)
    return school


def update_school(db: Session, school_id: int, data: AdminSchoolUpdate) -> School:
    """이름·순서·활성 여부 수정(보낸 것만). 없으면 404, 다른 학교와 이름이 같으면 409."""
    school = db.get(School, school_id)
    if school is None:
        raise SchoolNotFoundError()
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(school, field, value)
    _commit_unique_name(db)
    db.refresh(school)
    return school


def _commit_unique_name(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicateSchoolNameError() from None


# ---------- 내 학교 ----------


def get_user_school(db: Session, user: User) -> UserSchool | None:
    return db.scalar(select(UserSchool).where(UserSchool.user_id == user.id))


def school_of(db: Session, row: UserSchool | None) -> School | None:
    return db.get(School, row.school_id) if row is not None and row.school_id is not None else None


def changeable_at(row: UserSchool | None, now: datetime | None = None) -> datetime | None:
    """학교를 다시 바꿀 수 있는 시각(UTC). 지금 바꿀 수 있으면 None. 처음 정할 때는 바로 정할 수 있다."""
    if row is None:
        return None
    available = user_service.as_utc(row.changed_at) + SCHOOL_CHANGE_INTERVAL
    return available if available > (now or user_service.utc_now()) else None


def change_user_school(db: Session, user: User, school_id: int | None, now: datetime | None = None) -> UserSchool:
    """내 학교 변경(None이면 비움). 순서: 400 지금과 같음 → 400 7일 안에 이미 바꿈 → 404/400 없거나 비활성 학교."""
    now = now or user_service.utc_now()
    row = get_user_school(db, user)
    current = row.school_id if row is not None else None
    if school_id == current:
        raise SameSchoolError()
    available = changeable_at(row, now)
    if available is not None:
        local = available.astimezone(user_service.KST)
        raise SchoolChangeTooSoonError(
            f"학교는 7일에 한 번만 바꿀 수 있습니다. {local.month}월 {local.day}일 {local:%H:%M}부터 바꿀 수 있어요."
        )
    if school_id is not None:
        get_selectable(db, school_id)

    # DB에는 시간대 없이 UTC로 저장한다. (닉네임 변경 기록과 같은 방식)
    if row is None:
        row = UserSchool(user_id=user.id)
        db.add(row)
    row.school_id = school_id
    row.changed_at = now.replace(tzinfo=None)
    db.commit()
    db.refresh(row)
    return row


def delete_for_user(db: Session, user_id: int) -> None:
    """탈퇴 때 내 학교 행을 지운다(커밋 전)."""
    db.execute(delete(UserSchool).where(UserSchool.user_id == user_id))


# ---------- 글의 학교 ----------


def check_post_school(db: Session, school_id: int | None) -> None:
    """글에 붙일 학교 확인(저장 전). 없는 학교 404, 비활성 400."""
    if school_id is not None:
        get_selectable(db, school_id)


def set_post_school(db: Session, post: Post, school_id: int | None) -> None:
    """글의 학교를 바꾼다(커밋 전). None이면 행을 지워 학교 없는 글로 만든다."""
    db.execute(delete(PostSchool).where(PostSchool.post_id == post.id))
    if school_id is not None:
        db.add(PostSchool(post_id=post.id, school_id=school_id))


def delete_for_post(db: Session, post_id: int) -> None:
    """글 삭제 때 학교 연결 행을 지운다(커밋 전). SQLite는 FK의 CASCADE를 실행하지 않는다."""
    db.execute(delete(PostSchool).where(PostSchool.post_id == post_id))


def search_condition(school_id: int) -> ColumnElement[bool]:
    """목록 필터: 그 학교로 등록된 글만. 학교 없는 글은 빠진다(전체에서만 보임)."""
    return Post.id.in_(select(PostSchool.post_id).where(PostSchool.school_id == school_id))
