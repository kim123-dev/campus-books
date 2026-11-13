"""쪽지 사진 보내기.

- 검사·다시 인코딩은 판매글 사진과 같은 함수(image_service.process_upload)를 쓴다.
  형식을 실제 내용으로 확인하고, EXIF(GPS 위치 등)를 지운 WebP로 다시 만든다.
- 파일은 판매글 사진과 다른 폴더(uploads/messages/)에 둔다. 공개 주소가 없고,
  GET /messages/{id}/image로 대화 참여자만 받을 수 있다.
- 메시지는 지우지 않으므로(신고 증거) 사진 파일도 지우지 않는다. 상대가 탈퇴해도 남는다.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ImageUploadRateLimitError
from app.models import Message, MessageImage, User
from app.schemas.conversation import MessageResponse
from app.services import conversation_service, image_service, image_storage


@dataclass(frozen=True)
class ImageRateLimit:
    """window_seconds초 안에 max_images장까지 보낼 수 있다."""

    max_images: int
    window_seconds: int


# 사진은 다시 인코딩하느라 CPU를 많이 쓰므로 글 쪽지(10초 5건)와 따로 더 좁게 막는다. 이 값 하나만 바꾸면 된다.
MESSAGE_IMAGE_RATE_LIMIT = ImageRateLimit(max_images=10, window_seconds=600)


def send_image(db: Session, conversation_id: int, sender: User, upload: BinaryIO, content: str = "") -> MessageResponse:
    """사진 한 장을 쪽지로 보낸다. content는 함께 보낼 글(없어도 된다, 앞뒤 공백 제거·길이는 라우터가 검사).
    순서: 글 쪽지와 같은 검사(404·403·400·429) → 429 사진 횟수 제한 → 413/422 사진 검사.
    """
    conversation = conversation_service.check_can_send(db, conversation_id, sender)
    _check_rate_limit(db, sender)

    # 무거운 처리(읽기·디코딩)는 싼 검사를 모두 통과한 뒤에 한다.
    image_bytes, thumb_bytes = image_service.process_upload(upload, sender)
    directory = image_storage.get_message_image_dir()
    filename, thumb_filename = image_storage.new_filenames()
    image_storage.write_files({filename: image_bytes, thumb_filename: thumb_bytes}, directory)

    try:
        message = conversation_service.append_message(db, conversation, sender, content.strip())
        db.add(MessageImage(message_id=message.id, filename=filename, thumb_filename=thumb_filename))
        db.commit()
    except Exception:
        # DB에 기록하지 못했으면 주인 없는 파일이 남지 않게 지운다.
        db.rollback()
        image_storage.remove_files([filename, thumb_filename], directory)
        raise
    db.refresh(message)
    return conversation_service.to_message_response(message, sender, has_image=True)


def _check_rate_limit(db: Session, sender: User) -> None:
    # 다른 제한과 같은 방식: 저장된 created_at과 같은 기준인 DB 시간으로 최근 장수를 센다.
    db_now = db.scalar(select(func.now()))
    since = db_now - timedelta(seconds=MESSAGE_IMAGE_RATE_LIMIT.window_seconds)
    recent = db.scalar(
        select(func.count())
        .select_from(MessageImage)
        .join(Message, MessageImage.message_id == Message.id)
        .where(Message.sender_id == sender.id, MessageImage.created_at > since)
    )
    if (recent or 0) >= MESSAGE_IMAGE_RATE_LIMIT.max_images:
        raise ImageUploadRateLimitError(retry_after=MESSAGE_IMAGE_RATE_LIMIT.window_seconds)
