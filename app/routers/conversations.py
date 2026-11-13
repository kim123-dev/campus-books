from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import ActiveUser, CurrentUser
from app.schemas.conversation import (
    ConversationListResponse,
    ConversationDetailResponse,
    ImageSize,
    MAX_MESSAGE_LENGTH,
    MessageCreate,
    MessageListParams,
    MessageListResponse,
    MessageResponse,
    UnreadCountResponse,
)
from app.schemas.post import PageQuery, SizeQuery
from app.routers.images import private_image_response
from app.services import conversation_service, image_storage, message_image_service

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


# 내 목록에서만 지운다. 상대에게는 그대로 남고, 메시지는 신고 증거가 될 수 있어 지우지 않는다.
# 정지 중에도 나갈 수 있게 CurrentUser를 쓴다. (무언가를 새로 만드는 요청이 아니다)
@router.post(
    "/conversations/{conversation_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="대화방 나가기 (내 목록에서만 숨김)",
    responses=PARTICIPANT_ONLY_RESPONSES,
)
def leave_conversation(
    conversation_id: int, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> None:
    conversation_service.leave_conversation(db, conversation_id, current_user)


# 사진 한 장을 쪽지로 보낸다. 글 쪽지와 같은 검사(차단·탈퇴·정지·도배)에 사진 횟수 제한(10분 10장)이 더해진다.
@router.post(
    "/conversations/{conversation_id}/images",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="사진 쪽지 보내기 (JPG·PNG·WebP·HEIC, 25MB, 메시지당 1장)",
    responses={
        **PARTICIPANT_ONLY_RESPONSES,
        400: {"description": "차단 관계, 탈퇴한 상대"},
        413: {"description": "25MB 초과"},
        422: {"description": "지원하지 않는 형식, 해상도 초과, 깨진 사진"},
        429: {"description": "짧은 시간에 너무 많이 보냄(쪽지 10초 5건, 사진 10분 10장)"},
    },
)
def send_message_image(
    conversation_id: int,
    current_user: ActiveUser,
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File(description="사진 파일 (multipart 필드 이름: file)")],
    content: Annotated[str, Form(max_length=MAX_MESSAGE_LENGTH, description="함께 보낼 글 (없어도 됨)")] = "",
) -> MessageResponse:
    return message_image_service.send_image(db, conversation_id, current_user, file.file, content)


# 쪽지 사진은 공개 주소가 없다. 로그인한 대화 참여자만 받을 수 있고, 화면은 토큰을 붙여 받아 blob으로 보여준다.
# 차단·정지 중이어도 지난 대화의 사진은 볼 수 있다. (CurrentUser)
@router.get(
    "/messages/{message_id}/image",
    response_class=FileResponse,
    summary="쪽지 사진 (대화 참여자만)",
    responses={
        401: {"description": "로그인 필요"},
        403: {"description": "대화 참여자가 아님"},
        404: {"description": "없는 메시지, 나가며 숨긴 메시지, 사진 없음"},
    },
)
def get_message_image(
    message_id: int,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    size: ImageSize = ImageSize.FULL,
) -> FileResponse:
    filename = conversation_service.get_message_image(db, message_id, current_user, size)
    return private_image_response(filename, image_storage.get_message_image_dir())
