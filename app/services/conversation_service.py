from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import (
    BlockedByUserMessageError,
    BlockedUserMessageError,
    CannotContactOwnPostError,
    ConversationNotFoundError,
    MessageRateLimitError,
    NotConversationParticipantError,
    SoldPostNotContactableError,
    WithdrawnPartnerMessageError,
)
from app.models import Conversation, ConversationUserState, Message, PostStatus, User
from app.schemas.conversation import (
    ConversationDetailResponse,
    ConversationPostResponse,
    ConversationResponse,
    ConversationRole,
    LastMessageResponse,
    MessageCreate,
    MessageListParams,
    MessageListResponse,
    MessageResponse,
    PartnerResponse,
)
from app.services import block_service, post_service, review_service, user_service


@dataclass(frozen=True)
class RateLimit:
    """window_seconds초 안에 max_messages개까지 보낼 수 있다."""

    max_messages: int
    window_seconds: int


# 도배 방지 기준. 이 값 하나만 바꾸면 된다.
MESSAGE_RATE_LIMIT = RateLimit(max_messages=5, window_seconds=10)


# ---------- 대화방 ----------


def start_conversation(
    db: Session, post_id: int, buyer: User
) -> tuple[ConversationDetailResponse, bool]:
    """글에 대한 문의를 시작한다. (대화방, 새로 만들었는지)를 돌려준다.

    이미 방이 있으면 글 상태와 상관없이 그 방을 돌려준다. 거래 마무리 연락이 끊기지 않게 하기 위해서다.
    """
    post = post_service.get_post(db, post_id)  # 없으면 404
    if post.seller_id == buyer.id:
        raise CannotContactOwnPostError()

    existing = _find_conversation(db, post.id, buyer.id)
    if existing is not None:
        # 차단했어도 이미 있는 방은 돌려준다. 지난 대화는 거래 분쟁 때 필요해 읽을 수 있게 둔다.
        # 나갔던 방이면 목록에 다시 보이게 한다. 나가기 전 메시지는 계속 숨긴 채로(빈 방처럼) 열린다.
        _rejoin(db, existing.id, buyer.id)
        return _to_detail(db, existing, buyer), False

    if post.status == PostStatus.SOLD:
        raise SoldPostNotContactableError()
    _check_not_blocked(db, buyer, post.seller_id)

    conversation = Conversation(post_id=post.id, buyer_id=buyer.id, seller_id=post.seller_id)
    db.add(conversation)
    try:
        db.commit()
    except IntegrityError:
        # 같은 사용자의 요청 두 개가 동시에 들어와 다른 요청이 먼저 방을 만들었다. 그 방을 돌려준다.
        db.rollback()
        existing = _find_conversation(db, post.id, buyer.id)
        if existing is None:
            raise
        return _to_detail(db, existing, buyer), False

    return _to_detail(db, _load_conversation(db, conversation.id), buyer), True


def get_conversation(db: Session, conversation_id: int, user: User) -> ConversationDetailResponse:
    """대화방 정보 하나. 없으면 404, 참여자가 아니면 403."""
    conversation = _get_participating_conversation(db, conversation_id, user)
    return _to_detail(db, conversation, user)


def list_conversations(
    db: Session, user: User, page: int, size: int
) -> tuple[list[ConversationResponse], int]:
    """내가 구매자나 판매자로 참여한 대화방 목록(최신 메시지순)과 전체 개수. 내가 나간 방은 빠진다."""
    is_mine = or_(Conversation.buyer_id == user.id, Conversation.seller_id == user.id)
    state = _state_join(user.id)
    total = (
        db.scalar(
            select(func.count()).select_from(Conversation).outerjoin(ConversationUserState, state).where(is_mine, _visible())
        )
        or 0
    )

    conversations = db.scalars(
        _conversation_query()
        .outerjoin(ConversationUserState, state)
        .where(is_mine, _visible())
        # 같은 초에 온 메시지끼리는 메시지 id로 순서를 정한다. 메시지 없는 방(NULL)은 DESC에서 뒤로 간다.
        .order_by(
            Conversation.last_message_at.desc(),
            Conversation.last_message_id.desc(),
            Conversation.id.desc(),
        )
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return _to_responses(db, conversations, user), total


def count_unread(db: Session, user: User) -> int:
    """내가 참여한 모든 대화방에서 상대가 보낸 안 읽은 메시지 수. 화면마다 헤더가 부르므로 쿼리 1번으로 끝낸다.
    나가기 전 메시지(숨김 표시 이하)는 세지 않는다.
    """
    return (
        db.scalar(
            select(func.count())
            .select_from(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .outerjoin(ConversationUserState, _state_join(user.id))
            .where(
                or_(Conversation.buyer_id == user.id, Conversation.seller_id == user.id),
                Message.sender_id != user.id,
                Message.read_at.is_(None),
                Message.id > func.coalesce(ConversationUserState.cleared_through_message_id, 0),
            )
        )
        or 0
    )


def leave_conversation(db: Session, conversation_id: int, user: User) -> None:
    """대화방 나가기. 내 목록에서만 빠지고 상대에게는 그대로 남는다. 메시지는 지우지 않는다.
    지금까지의 메시지를 나에게 숨기고(숨김 표시), 안 읽은 메시지도 읽음 처리해 배지에서 뺀다.
    """
    conversation = _get_participating_conversation(db, conversation_id, user)
    state = _get_state(db, conversation.id, user.id)
    if state is None:
        state = ConversationUserState(conversation_id=conversation.id, user_id=user.id)
        db.add(state)
    state.cleared_through_message_id = conversation.last_message_id or 0
    state.left = True
    state.updated_at = func.now()
    try:
        db.commit()
    except IntegrityError:
        # 두 기기에서 동시에 나가 같은 행을 두 번 만들려 했다. 이미 나간 상태라 그대로 둔다.
        db.rollback()
    _mark_as_read(db, conversation.id, user)


# ---------- 메시지 ----------


def list_messages(
    db: Session, conversation_id: int, user: User, params: MessageListParams
) -> MessageListResponse:
    """메시지 목록(오래된 것부터). 조회하면 상대가 보낸 안 읽은 메시지를 모두 읽음 처리한다."""
    conversation = _get_participating_conversation(db, conversation_id, user)
    _mark_as_read(db, conversation.id, user)

    # 내가 나가기 전 메시지는 보여주지 않는다. (상대 화면에는 그대로 있다)
    query = select(Message).where(
        Message.conversation_id == conversation.id, Message.id > cleared_through(db, conversation.id, user.id)
    )
    # 한 개 더 읽어 보고, 넘치면 같은 방향으로 더 있다는 뜻이다.
    fetch = params.limit + 1
    if params.after_id is not None:
        rows = db.scalars(
            query.where(Message.id > params.after_id).order_by(Message.id.asc()).limit(fetch)
        ).all()
        has_more = len(rows) > params.limit
        messages = list(rows[: params.limit])
    else:
        # 기본(최근 메시지)과 before_id(이전 메시지)는 최신부터 읽어 limit개를 자른 뒤 뒤집는다.
        if params.before_id is not None:
            query = query.where(Message.id < params.before_id)
        rows = db.scalars(query.order_by(Message.id.desc()).limit(fetch)).all()
        has_more = len(rows) > params.limit
        messages = list(reversed(rows[: params.limit]))

    return MessageListResponse(
        items=[_to_message_response(message, user) for message in messages], has_more=has_more
    )


def send_message(
    db: Session, conversation_id: int, sender: User, data: MessageCreate
) -> MessageResponse:
    """메시지 전송. 차단 관계면 400, 짧은 시간에 너무 많이 보내면 MessageRateLimitError(429)."""
    conversation = _get_participating_conversation(db, conversation_id, sender)
    if user_service.is_withdrawn(_partner(conversation, sender)):
        raise WithdrawnPartnerMessageError()
    _check_not_blocked(db, sender, _partner_id(conversation, sender))
    _check_rate_limit(db, sender)

    message = Message(conversation_id=conversation.id, sender_id=sender.id, content=data.content)
    db.add(message)
    # 메시지 id가 있어야 대화방의 마지막 메시지로 기록할 수 있으므로 먼저 INSERT한다.
    db.flush()
    conversation.last_message_at = func.now()
    conversation.last_message_id = message.id
    db.commit()
    # created_at은 DB가 채우므로 다시 읽어와야 응답에 담을 수 있다.
    db.refresh(message)
    return _to_message_response(message, sender)


def cleared_through(db: Session, conversation_id: int, user_id: int) -> int:
    """이 번호 이하의 메시지는 이 사용자에게 숨긴다(나가기). 나간 적이 없으면 0."""
    state = _get_state(db, conversation_id, user_id)
    return state.cleared_through_message_id if state is not None else 0


# ---------- 내부 함수 ----------


def _state_join(user_id: int):
    """대화방과 이 사용자의 나가기 상태를 잇는 조건(LEFT OUTER JOIN용)."""
    return and_(ConversationUserState.conversation_id == Conversation.id, ConversationUserState.user_id == user_id)


def _visible():
    """목록에 보일 방: 나간 적이 없거나, 다시 들어왔거나, 나간 뒤에 새 메시지가 온 방."""
    return or_(
        ConversationUserState.id.is_(None),
        ConversationUserState.left.is_(False),
        func.coalesce(Conversation.last_message_id, 0) > ConversationUserState.cleared_through_message_id,
    )


def _get_state(db: Session, conversation_id: int, user_id: int) -> ConversationUserState | None:
    return db.scalar(
        select(ConversationUserState).where(
            ConversationUserState.conversation_id == conversation_id, ConversationUserState.user_id == user_id
        )
    )


def _rejoin(db: Session, conversation_id: int, user_id: int) -> None:
    state = _get_state(db, conversation_id, user_id)
    if state is not None and state.left:
        state.left = False
        db.commit()


def _partner(conversation: Conversation, user: User) -> User:
    return conversation.seller if conversation.buyer_id == user.id else conversation.buyer


def _partner_id(conversation: Conversation, user: User) -> int:
    return conversation.seller_id if conversation.buyer_id == user.id else conversation.buyer_id


def _check_not_blocked(db: Session, me: User, other_id: int) -> None:
    """둘 중 한 명이라도 상대를 차단했으면 400. 내가 차단한 경우와 상대가 차단한 경우의 문구를 나눈다."""
    i_blocked, they_blocked = block_service.block_state(db, me.id, other_id)
    if i_blocked:
        raise BlockedUserMessageError()
    if they_blocked:
        raise BlockedByUserMessageError()


def _to_detail(db: Session, conversation: Conversation, viewer: User) -> ConversationDetailResponse:
    """대화 화면용 응답. 목록 응답에 차단 상태(쿼리 1번)를 더한다."""
    base = _to_responses(db, [conversation], viewer)[0]
    i_blocked, they_blocked = block_service.block_state(db, viewer.id, _partner_id(conversation, viewer))
    # 상대가 탈퇴했으면 답장할 사람이 없으므로 입력창을 잠근다. (차단 행은 탈퇴 때 지워졌다)
    partner_withdrawn = user_service.is_withdrawn(_partner(conversation, viewer))
    return ConversationDetailResponse(
        **base.model_dump(),
        can_send=not (i_blocked or they_blocked or partner_withdrawn),
        blocked_by_me=i_blocked,
        # 후기는 차단 관계여도 남길 수 있어 차단과 상관없이 알려준다.
        trade=review_service.state_for_conversation(db, conversation, viewer),
    )


def _conversation_query():
    # 응답에 필요한 글·구매자·판매자를 JOIN으로 함께 가져와, 방마다 추가 조회(N+1)가 나가지 않게 한다.
    return select(Conversation).options(
        joinedload(Conversation.post),
        joinedload(Conversation.buyer),
        joinedload(Conversation.seller),
    )


def _load_conversation(db: Session, conversation_id: int) -> Conversation | None:
    return db.scalar(_conversation_query().where(Conversation.id == conversation_id))


def _find_conversation(db: Session, post_id: int, buyer_id: int) -> Conversation | None:
    return db.scalar(
        _conversation_query().where(
            Conversation.post_id == post_id, Conversation.buyer_id == buyer_id
        )
    )


# 대화방 API의 공통 순서: 방이 없으면 404, 참여자가 아니면 403.
def _get_participating_conversation(db: Session, conversation_id: int, user: User) -> Conversation:
    conversation = _load_conversation(db, conversation_id)
    if conversation is None:
        raise ConversationNotFoundError()
    if user.id not in (conversation.buyer_id, conversation.seller_id):
        raise NotConversationParticipantError()
    return conversation


def _mark_as_read(db: Session, conversation_id: int, reader: User) -> None:
    # 응답에 담긴 페이지만이 아니라 상대가 보낸 안 읽은 메시지 전체를 읽음 처리한다.
    # 기본 조회가 최신 메시지라 사용자가 보는 것과 일치하고, 규칙이 단순해진다.
    db.execute(
        update(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.sender_id != reader.id,
            Message.read_at.is_(None),
        )
        .values(read_at=func.now())
    )
    db.commit()


def _check_rate_limit(db: Session, sender: User) -> None:
    # 저장된 created_at과 같은 기준으로 비교하도록 앱 서버 시간 대신 DB 시간을 쓴다.
    # (서버가 여러 대이거나 재시작해도 같은 기준으로 동작한다)
    db_now = db.scalar(select(func.now()))
    since = db_now - timedelta(seconds=MESSAGE_RATE_LIMIT.window_seconds)
    recent = db.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.sender_id == sender.id, Message.created_at > since)
    )
    if (recent or 0) >= MESSAGE_RATE_LIMIT.max_messages:
        raise MessageRateLimitError(retry_after=MESSAGE_RATE_LIMIT.window_seconds)


def _to_responses(
    db: Session, conversations: Sequence[Conversation], viewer: User
) -> list[ConversationResponse]:
    """대화방들을 보는 사람 기준의 응답으로 바꾼다. 방 수와 상관없이 쿼리 3번으로 끝낸다."""
    if not conversations:
        return []
    ids = [c.id for c in conversations]
    cleared = dict(
        db.execute(
            select(ConversationUserState.conversation_id, ConversationUserState.cleared_through_message_id).where(
                ConversationUserState.conversation_id.in_(ids), ConversationUserState.user_id == viewer.id
            )
        ).all()
    )

    last_ids = [c.last_message_id for c in conversations if c.last_message_id is not None]
    last_messages = (
        {m.id: m for m in db.scalars(select(Message).where(Message.id.in_(last_ids)))}
        if last_ids
        else {}
    )
    unread_counts = dict(
        db.execute(
            select(Message.conversation_id, func.count())
            .join(Conversation, Message.conversation_id == Conversation.id)
            .outerjoin(ConversationUserState, _state_join(viewer.id))
            .where(
                Message.conversation_id.in_(ids),
                Message.sender_id != viewer.id,
                Message.read_at.is_(None),
                Message.id > func.coalesce(ConversationUserState.cleared_through_message_id, 0),
            )
            .group_by(Message.conversation_id)
        ).all()
    )

    responses = []
    for conversation in conversations:
        is_buyer = conversation.buyer_id == viewer.id
        last = last_messages.get(conversation.last_message_id)
        # 마지막 메시지가 내가 나가기 전 것이면 미리보기를 비운다. (다시 문의해 연 빈 방)
        if last is not None and last.id <= cleared.get(conversation.id, 0):
            last = None
        responses.append(
            ConversationResponse(
                id=conversation.id,
                post=(
                    ConversationPostResponse.model_validate(conversation.post)
                    if conversation.post is not None
                    else None
                ),
                partner=_to_partner_response(conversation.seller if is_buyer else conversation.buyer),
                my_role=ConversationRole.BUYER if is_buyer else ConversationRole.SELLER,
                last_message=(
                    LastMessageResponse(
                        content=last.content,
                        is_mine=last.sender_id == viewer.id,
                        created_at=last.created_at,
                    )
                    if last is not None
                    else None
                ),
                unread_count=unread_counts.get(conversation.id, 0),
                created_at=conversation.created_at,
                last_message_at=conversation.last_message_at,
            )
        )
    return responses


def _to_partner_response(partner: User) -> PartnerResponse:
    # 탈퇴한 상대는 닉네임 대신 "탈퇴한 사용자"로 보여준다. (탈퇴 때 바꾼 임의 닉네임을 드러내지 않는다)
    return PartnerResponse(
        id=partner.id,
        nickname=user_service.display_nickname(partner),
        withdrawn=user_service.is_withdrawn(partner),
    )


def _to_message_response(message: Message, viewer: User) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        sender_id=message.sender_id,
        is_mine=message.sender_id == viewer.id,
        content=message.content,
        created_at=message.created_at,
        read_at=message.read_at,
    )
