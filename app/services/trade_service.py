"""거래 기록: 판매 완료 때 고를 수 있는 구매자 후보와 거래 행 저장·변경.

작성자 확인과 커밋은 post_service가 한다. 이 모듈은 글을 받아 거래만 다뤄서,
post_service → trade_service 한 방향으로만 의존하게 했다.
"""

from datetime import timedelta

from sqlalchemy import Select, delete, exists, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidBuyerError
from app.models import Conversation, Message, Post, Trade, User, UserBlock
from app.schemas.trade import BuyerCandidateResponse, PostBuyerResponse
from app.services import user_service

# 후기를 남길 수 있는 기간. 거래가 기록된 시각부터 센다. 이 값 하나만 바꾸면 된다.
REVIEW_PERIOD = timedelta(days=14)


def list_candidates(db: Session, post: Post) -> list[User]:
    """구매자로 고를 수 있는 사람(최근 대화순)."""
    query = _candidates_query(post, User).order_by(Conversation.last_message_at.desc(), Conversation.id.desc())
    return list(db.scalars(query))


def _candidate_conversation_id(db: Session, post: Post, buyer_id: int) -> int:
    """후보이면 그 사람과의 대화방 번호. 후보가 아니면 400."""
    conversation_id = db.scalar(_candidates_query(post, Conversation.id).where(User.id == buyer_id))
    if conversation_id is None:
        raise InvalidBuyerError()
    return conversation_id


def get_for_post(db: Session, post_id: int) -> Trade | None:
    return db.scalar(select(Trade).where(Trade.post_id == post_id))


def record(db: Session, post: Post, buyer_id: int) -> None:
    """거래 행을 추가한다(커밋 전). 후보인지 먼저 확인한다: 400."""
    conversation_id = _candidate_conversation_id(db, post, buyer_id)
    db.add(
        Trade(
            post_id=post.id,
            conversation_id=conversation_id,
            seller_id=post.seller_id,
            buyer_id=buyer_id,
            book_title_snapshot=post.book_title,
        )
    )


def is_recorded_buyer(db: Session, post_id: int, buyer_id: int) -> bool:
    trade = get_for_post(db, post_id)
    return trade is not None and trade.buyer_id == buyer_id


def buyer_info(db: Session, post: Post) -> PostBuyerResponse:
    """판매자 화면용: 지금 구매자, 고를 수 있는 후보, 바꿀 수 있는지."""
    trade = get_for_post(db, post.id)
    return PostBuyerResponse(
        buyer=BuyerCandidateResponse.model_validate(trade.buyer) if trade is not None else None,
        candidates=[BuyerCandidateResponse.model_validate(user) for user in list_candidates(db, post)],
        changeable=trade is not None,
    )


def change_buyer(db: Session, post: Post, trade: Trade, buyer_id: int | None) -> None:
    """구매자를 다른 후보로 바꾸거나(buyer_id) 거래 기록을 지운다(None). 커밋 전.

    거래 시각(created_at)은 그대로 둬서, 구매자를 바꿔도 후기 작성 기간이 늘어나지 않는다.
    """
    if buyer_id is None:
        db.execute(delete(Trade).where(Trade.id == trade.id))
        return
    if buyer_id == trade.buyer_id:
        return
    conversation_id = _candidate_conversation_id(db, post, buyer_id)
    db.execute(
        update(Trade).where(Trade.id == trade.id).values(buyer_id=buyer_id, conversation_id=conversation_id)
    )


def detach_post(db: Session, post_id: int) -> None:
    """글을 지울 때 거래의 글 연결만 끊는다. 거래와 후기, 교재명 사본은 남는다.
    FK의 ondelete="SET NULL"은 SQLite가 실행하지 않으므로 직접 바꾼다.
    """
    db.execute(update(Trade).where(Trade.post_id == post_id).values(post_id=None))


def _candidates_query(post: Post, column) -> Select:
    """이 글의 대화방 상대 중 쪽지를 한 번 이상 보낸 사람. 탈퇴했거나 판매자와 차단 관계(어느 쪽이든)면 뺀다.
    정지된 사용자는 넣는다. 거래 사실은 정지와 상관없기 때문이다.
    """
    seller_id = post.seller_id
    blocked_by_seller = select(UserBlock.blocked_id).where(UserBlock.blocker_id == seller_id)
    blocking_seller = select(UserBlock.blocker_id).where(UserBlock.blocked_id == seller_id)
    # 방만 열고 아무 말도 하지 않은 사람은 거래했다고 보기 어렵다.
    sent_message = exists().where(
        Message.conversation_id == Conversation.id, Message.sender_id == Conversation.buyer_id
    )
    return (
        select(column)
        .select_from(User)
        .join(Conversation, Conversation.buyer_id == User.id)
        .where(
            Conversation.post_id == post.id,
            sent_message,
            User.password_hash != user_service.WITHDRAWN_PASSWORD_HASH,
            User.id.not_in(blocked_by_seller),
            User.id.not_in(blocking_seller),
        )
    )
