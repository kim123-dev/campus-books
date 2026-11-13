from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PendingImage(Base):
    """글에 붙기 전의 임시 사진. 글쓰기 화면이 사진을 고르는 즉시 올려 두고, 글을 저장할 때 번호로 붙인다.

    글에 붙으면 이 행은 지워지고 post_images 행이 된다. 붙지 않은 채 24시간이 지나면 정리된다.
    파일은 공개 주소가 없는 폴더(uploads/pending/)에 둔다.
    """

    __tablename__ = "pending_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 올린 사람만 글에 붙이거나 지울 수 있다. 사용자별 개수·횟수를 세므로 index를 둔다.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(64))
    thumb_filename: Mapped[str] = mapped_column(String(64))
    # 오래된 임시 사진을 찾을 때 쓰므로 index를 둔다.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
