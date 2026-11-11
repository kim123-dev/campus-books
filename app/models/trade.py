from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.user import User


class Trade(Base):
    """거래 기록. 판매자가 판매 완료로 바꾸면서 구매자를 고른 경우에만 생긴다.

    posts에 buyer_id 컬럼을 더하지 않고 따로 둔 이유: 운영 DB는 create_all만 쓰므로 기존 테이블에는
    컬럼이 추가되지 않는다. 새 테이블은 배포 후 시작할 때 자동으로 만들어진다. (ALTER 불필요)
    구매자 없이 판매 완료한 글(오프라인 거래, 기능 추가 전에 판매 완료된 글)에는 행이 없다.
    """

    __tablename__ = "trades"
    __table_args__ = (
        # 한 글에는 거래가 하나뿐이다. 글이 삭제되어 post_id가 NULL이 된 행끼리는 겹쳐도 된다.
        UniqueConstraint("post_id", name="uq_trade_post"),
        # 쪽지 화면에서 이 대화의 거래를 찾는다. 글이 지워져도 대화방으로 이어지게 한다.
        UniqueConstraint("conversation_id", name="uq_trade_conversation"),
        CheckConstraint("seller_id <> buyer_id", name="ck_trade_not_self"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # 글이 삭제되어도 거래와 후기는 남기기 위해 NULL로 바꾼다. (SQLite는 FK를 실행하지 않아 서비스에서도 직접 처리)
    post_id: Mapped[int | None] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL"), nullable=True
    )
    # 구매자와 쪽지를 주고받은 대화방. 글이 삭제되면 대화방의 post_id도 NULL이 되므로, 거래는 대화방을 직접 가리킨다.
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # 글이 지워진 뒤에도 후기에 어떤 교재 거래였는지 보여주기 위한 사본
    book_title_snapshot: Mapped[str] = mapped_column(String(200))
    # 후기 작성 기간의 기준. 구매자를 바꿔도 그대로 둬서 기간이 늘어나지 않게 한다.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    seller: Mapped[User] = relationship(foreign_keys=[seller_id])
    buyer: Mapped[User] = relationship(foreign_keys=[buyer_id])
