from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class School(Base):
    """학교. 관리자가 추가·이름 수정·비활성 처리한다. 앱 시작 시 기본 학교 하나를 넣는다(school_service.seed_default).

    학교 이름은 번역하지 않고 원문 그대로 보여준다.
    비활성 학교는 새로 고를 수 없지만, 이미 연결된 사용자·글의 학교 표시는 그대로 남는다.
    """

    __tablename__ = "schools"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # 목록 순서. 작은 값이 먼저, 같으면 이름순.
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserSchool(Base):
    """사용자의 학교(사용자당 1행). users 테이블에 컬럼을 더하지 않으려고 새 테이블로 둔다. (운영 DB는 create_all만 쓴다)

    학교를 비우면 school_id를 null로 두고 행은 남긴다. 7일에 한 번 바꿀 수 있는 기준 시각(changed_at)을 지키기 위해서다.
    """

    __tablename__ = "user_schools"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    school_id: Mapped[int | None] = mapped_column(ForeignKey("schools.id"), nullable=True, index=True)
    # 마지막으로 바꾼 시각(UTC, 시간대 없이 저장). 다음 변경 가능 시각을 계산한다.
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PostSchool(Base):
    """글의 학교(글당 최대 1행). 학교 없는 글(기존 글)은 행이 없다. posts 테이블은 바꾸지 않는다."""

    __tablename__ = "post_schools"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), unique=True)
    # 학교 필터(GET /posts?school_id=)가 이 인덱스로 글 번호를 찾는다.
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), index=True)
