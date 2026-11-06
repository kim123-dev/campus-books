from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.user import User


class PostStatus(StrEnum):
    """판매 상태. 작성 시에는 항상 ON_SALE로 시작한다."""

    ON_SALE = "ON_SALE"
    RESERVED = "RESERVED"
    SOLD = "SOLD"


class BookCondition(StrEnum):
    """책 상태(상/중/하)."""

    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"


# MySQL과 SQLite에서 똑같이 동작하도록 DB 고유 ENUM 대신 문자열 컬럼 + 값 검사로 저장한다.
def _enum_column(enum_cls: type[StrEnum]) -> SAEnum:
    return SAEnum(enum_cls, native_enum=False, length=20, validate_strings=True)


class Post(Base):
    """판매글. 한 사용자(판매자)가 여러 글을 쓸 수 있다."""

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 내 글 목록 조회에서 seller_id로 찾으므로 index를 둔다.
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    book_title: Mapped[str] = mapped_column(String(200))
    course_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    condition: Mapped[BookCondition] = mapped_column(_enum_column(BookCondition))
    price: Mapped[int] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PostStatus] = mapped_column(
        _enum_column(PostStatus),
        default=PostStatus.ON_SALE,
        server_default=PostStatus.ON_SALE.value,
    )
    # 목록을 최신순으로 정렬하므로 index를 둔다.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # ORM으로 수정(UPDATE)할 때마다 DB 시간으로 자동 갱신된다.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # User 쪽에는 관계를 두지 않는다. 지금은 글 → 판매자 방향만 필요하다.
    seller: Mapped[User] = relationship()
