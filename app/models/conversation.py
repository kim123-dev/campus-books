from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, false, func
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


class ConversationUserState(Base):
    """대화방에 대한 사람별 상태: 나가기. 메시지는 지우지 않고 "이 번호까지는 나에게 숨김"만 기록한다.

    - 나가면 내 목록에서 빠지고, 상대 화면에는 아무 변화가 없다.
    - 상대가 새 메시지를 보내면(또는 내가 같은 글에 다시 문의하면) 방이 다시 보이지만,
      나가기 전 메시지는 계속 숨긴다. 안 읽은 수도 숨김 표시 이후 메시지만 센다.
    - 메시지는 신고 증거가 될 수 있어 지우지 않는다. 관리자 신고 처리는 이 숨김과 상관없다.
    conversations 테이블에 컬럼을 더하면 ALTER가 필요하므로 새 테이블로 둔다.
    """

    __tablename__ = "conversation_user_states"
    __table_args__ = (UniqueConstraint("conversation_id", "user_id", name="uq_conversation_user_state"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    # 내 목록을 만들 때 내 상태를 함께 읽으므로 index를 둔다.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # 이 번호 이하의 메시지는 나에게 보이지 않는다. 0이면 숨긴 메시지가 없다.
    cleared_through_message_id: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # 나간 상태. 이보다 새 메시지가 오거나 다시 문의하면 목록에 다시 나타난다.
    left: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageImage(Base):
    """쪽지에 붙인 사진 한 장(메시지 하나에 한 장).

    판매글 사진과 달리 공개 주소(/images)가 없다. 파일은 uploads/messages/에 두고,
    대화 참여자(와 신고를 처리하는 관리자)만 로그인한 요청으로 받을 수 있다.
    messages 테이블에 컬럼을 더하면 ALTER가 필요하므로 새 테이블로 둔다.
    """

    __tablename__ = "message_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 메시지 하나에 사진 한 장. unique라 index도 함께 생긴다.
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), unique=True)
    filename: Mapped[str] = mapped_column(String(64))
    thumb_filename: Mapped[str] = mapped_column(String(64))
    # 사진 횟수 제한(10분 10장)을 셀 때 쓴다.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
