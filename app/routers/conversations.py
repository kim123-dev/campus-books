from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import ActiveUser, CurrentUser
from app.schemas.conversation import (
    ConversationListResponse,
    ConversationDetailResponse,
    MessageCreate,
    MessageListParams,
    MessageListResponse,
    MessageResponse,
    UnreadCountResponse,
)
from app.schemas.post import PageQuery, SizeQuery
from app.services import conversation_service

# 쪽지는 모두 로그인이 필요하다. 경로가 /posts와 /conversations에 걸쳐 있어 prefix는 두지 않는다.
router = APIRouter(tags=["conversations"])

# 대화방 API의 공통 에러 응답. Swagger 문서에 보이도록 정리해 둔다.
PARTICIPANT_ONLY_RESPONSES: dict[int | str, dict] = {
    401: {"description": "로그인 필요"},
    403: {"description": "대화 참여자(구매자·판매자)가 아님"},
    404: {"description": "없는 대화방"},
}


# 이미 방이 있으면 새로 만들지 않고 200으로 기존 방을 돌려준다. (버튼을 여러 번 눌러도 안전)
@router.post(
    "/posts/{post_id}/conversations",
    response_model=ConversationDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="판매글 문의 시작 (이미 있으면 기존 대화방)",
    responses={
        200: {"description": "이미 있는 대화방"},
        400: {"description": "본인 글, 판매 완료된 글에 새 문의"},
        401: {"description": "로그인 필요"},
        404: {"description": "없는 글"},
    },
)
def start_conversation(
    post_id: int,
    response: Response,
    current_user: ActiveUser,
    db: Annotated[Session, Depends(get_db)],
) -> ConversationDetailResponse:
    conversation, created = conversation_service.start_conversation(db, post_id, current_user)
    if not created:
        response.status_code = status.HTTP_200_OK
    return conversation


@router.get(
    "/conversations",
    response_model=ConversationListResponse,
    summary="내 대화방 목록 (최신 메시지순)",
    responses={401: {"description": "로그인 필요"}},
)
def list_conversations(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 1,
    size: SizeQuery = 20,
) -> ConversationListResponse:
    items, total = conversation_service.list_conversations(db, current_user, page, size)
    return ConversationListResponse(items=items, total=total, page=page, size=size)


# /conversations/{conversation_id}보다 먼저 등록해야 한다. 나중에 두면 "unread-count"를 대화방 id로 읽어 422가 난다.
@router.get(
    "/conversations/unread-count",
    response_model=UnreadCountResponse,
    summary="안 읽은 쪽지 수 (헤더 배지용)",
    responses={401: {"description": "로그인 필요"}},
)
def count_unread(
    current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> UnreadCountResponse:
    return UnreadCountResponse(unread_count=conversation_service.count_unread(db, current_user))


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="대화방 정보",
    responses=PARTICIPANT_ONLY_RESPONSES,
)
def read_conversation(
    conversation_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> ConversationDetailResponse:
    return conversation_service.get_conversation(db, conversation_id, current_user)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
    summary="메시지 목록 (조회 시 상대 메시지 읽음 처리)",
    responses=PARTICIPANT_ONLY_RESPONSES,
)
def list_messages(
    conversation_id: int,
    params: Annotated[MessageListParams, Query()],
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> MessageListResponse:
    return conversation_service.list_messages(db, conversation_id, current_user, params)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="메시지 전송",
    responses={**PARTICIPANT_ONLY_RESPONSES, 429: {"description": "짧은 시간에 너무 많이 보냄"}},
)
def send_message(
    conversation_id: int,
    data: MessageCreate,
    current_user: ActiveUser,
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    return conversation_service.send_message(db, conversation_id, current_user, data)
