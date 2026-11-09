from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.post import Post
from app.models.user import User


class Conversation(Base):
    """판매글 하나를 두고 구매자와 판매자가 나누는 1:1 쪽지 대화방."""

    __tablename__ = "conversations"
    # 같은 글에 같은 구매자가 여러 방을 만들지 않게 DB에서도 막는다. (동시 요청 대비)
    # 글이 삭제되어 post_id가 NULL이 된 방끼리는 겹쳐도 된다. (NULL은 서로 다른 값으로 취급)
    __table_args__ = (UniqueConstraint("post_id", "buyer_id", name="uq_conversation_post_buyer"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # 글이 삭제되어도 대화 기록은 남기기 위해 NULL로 바꾼다. (SQLite는 FK를 검사하지 않으므로 서비스에서도 직접 처리)
    post_id: Mapped[int | None] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL"), nullable=True
    )
    # 내 대화방 목록을 구매자·판매자 양쪽에서 찾으므로 둘 다 index를 둔다.
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # 글이 삭제된 뒤에도 권한 검사를 할 수 있도록 판매자를 글과 별도로 저장한다.
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # 목록을 최신 메시지순으로 정렬하기 위해 따로 둔다. 메시지가 없으면 방을 만든 시각이다.
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # SQLite는 시간을 초 단위로 저장해 같은 초의 메시지끼리 순서를 가릴 수 없으므로, 정렬 보조와
    # 마지막 메시지 조회에 쓴다. messages와 서로 참조하는 FK를 만들지 않으려고 일반 정수 컬럼으로 둔다.
    last_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    post: Mapped[Post | None] = relationship()
    buyer: Mapped[User] = relationship(foreign_keys=[buyer_id])
    seller: Mapped[User] = relationship(foreign_keys=[seller_id])


class Message(Base):
    """대화방 안의 쪽지 한 건."""

    __tablename__ = "messages"
    __table_args__ = (
        # 대화방의 메시지를 id 순서로 읽는 조회(커서 페이지네이션)를 위한 index
        Index("ix_messages_conversation_id_id", "conversation_id", "id"),
        # 도배 검사: 한 사용자가 최근 몇 초 동안 보낸 메시지 수를 센다.
        Index("ix_messages_sender_id_created_at", "sender_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # 받는 사람이 읽은 시각. NULL이면 아직 안 읽었다.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
