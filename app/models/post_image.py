from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 글 하나에 올릴 수 있는 사진 수. 아래 CHECK 제약과 서비스 검사가 함께 쓴다.
MAX_IMAGES_PER_POST = 3


class PostImage(Base):
    """판매글 사진 한 장. 파일은 UPLOAD_DIR에 두고, DB에는 서버가 만든 파일 이름만 저장한다."""

    __tablename__ = "post_images"
    __table_args__ = (
        # 칸(slot) 0~2에 한 장씩만 들어가게 해, 동시에 올려도 DB가 3장을 넘지 않게 막는다.
        UniqueConstraint("post_id", "slot", name="uq_post_image_slot"),
        CheckConstraint(f"slot >= 0 AND slot < {MAX_IMAGES_PER_POST}", name="ck_post_image_slot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # MySQL에서는 글이 지워지면 행도 함께 지워진다. SQLite는 FK를 검사하지 않으므로 서비스에서 직접 지운다.
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    # 보여주는 순서. 지운 칸은 다음 업로드가 다시 쓴다.
    slot: Mapped[int]
    # 예: 3f9c...e1.webp (32자리 16진수 + .webp). 원본 파일 이름은 저장하지 않는다.
    filename: Mapped[str] = mapped_column(String(64))
    thumb_filename: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
