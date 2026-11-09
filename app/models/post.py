from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship

from app.core.database import Base
from app.models.post_image import PostImage
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
    # 구매자가 판매자에게 연락할 카카오 오픈채팅 주소. 허용 형식 검사는 스키마에서 한다.
    open_chat_url: Mapped[str | None] = mapped_column(String(200), nullable=True)
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
    # 상세 화면의 사진들. 보여주는 순서(slot)대로 정렬한다.
    # SQLite는 FK의 ON DELETE CASCADE를 실행하지 않으므로, 글을 지울 때 ORM이 사진 행도 함께 지우게 한다.
    images: Mapped[list[PostImage]] = relationship(
        order_by=PostImage.slot, cascade="all, delete-orphan"
    )

    # 목록 카드에 쓸 첫 사진의 썸네일 파일 이름. 글을 읽는 SELECT 안에 하위 쿼리로 함께 가져와,
    # 목록 요청의 쿼리 수가 늘지 않게 한다. (글마다 사진을 따로 조회하는 N+1 방지)
    thumbnail_filename: Mapped[str | None] = column_property(
        select(PostImage.thumb_filename)
        .where(PostImage.post_id == id)
        .order_by(PostImage.slot)
        .limit(1)
        .correlate_except(PostImage)
        .scalar_subquery()
    )
