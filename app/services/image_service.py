"""판매글 사진 업로드·삭제.

보안 규칙
- 확장자나 브라우저가 보낸 Content-Type이 아니라, Pillow로 실제 내용을 열어 형식을 확인한다.
- 원본 바이트를 그대로 저장하지 않고 다시 인코딩한다. 이미지에 숨겨 붙인 내용과
  사진의 GPS 위치 같은 메타데이터(EXIF)가 저장되지 않는다.
- 파일 이름은 서버가 새로 만든다. (image_storage)
"""

import io
from dataclasses import dataclass
from datetime import timedelta
from typing import BinaryIO

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ImageNotFoundError,
    ImageTooLargeError,
    ImageUploadRateLimitError,
    TooManyImagesError,
    UnsupportedImageError,
)
from app.models import MAX_IMAGES_PER_POST, Post, PostImage, User
from app.services import image_storage, post_service

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 장당 5MB
# 작은 파일이 풀면 거대한 이미지가 되어 메모리를 다 쓰는 공격(decompression bomb)을 막는다.
# 4천만 픽셀이면 휴대폰 사진(약 1200만~5천만)은 대부분 통과하고 비정상 크기는 거절된다.
MAX_IMAGE_PIXELS = 40_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_SIDE = 1600  # 상세 화면용 사진의 긴 변
THUMB_SIDE = 400  # 목록 카드용 썸네일의 긴 변
WEBP_QUALITY = 85
READ_CHUNK = 64 * 1024


@dataclass(frozen=True)
class UploadRateLimit:
    """window_seconds초 안에 max_uploads장까지 올릴 수 있다."""

    max_uploads: int
    window_seconds: int


# 업로드 횟수 제한. 다시 인코딩하느라 CPU를 많이 쓰므로 한 사용자가 몰아서 올리지 못하게 한다.
# 이 값 하나만 바꾸면 된다.
IMAGE_UPLOAD_RATE_LIMIT = UploadRateLimit(max_uploads=20, window_seconds=600)


def add_image(db: Session, post_id: int, user: User, upload: BinaryIO) -> PostImage:
    """사진 한 장 추가. 판정 순서: 404 글 없음 → 403 작성자 아님 → 400 판매 완료 → 400 3장 → 429 → 413/422."""
    post = post_service.get_editable_post(db, post_id, user)
    if len(post.images) >= MAX_IMAGES_PER_POST:
        raise TooManyImagesError()
    _check_rate_limit(db, user)

    # 무거운 처리(읽기·디코딩)는 싼 검사를 모두 통과한 뒤에 한다.
    image_bytes, thumb_bytes = _reencode(_read_limited(upload))
    filename, thumb_filename = image_storage.new_filenames()
    image_storage.write_files({filename: image_bytes, thumb_filename: thumb_bytes})

    try:
        image = _insert_into_free_slot(db, post, filename, thumb_filename)
    except Exception:
        # DB에 기록하지 못했으면 주인 없는 파일이 남지 않게 지운다.
        image_storage.remove_files([filename, thumb_filename])
        raise
    return image


def delete_image(db: Session, post_id: int, image_id: int, user: User) -> None:
    """사진 한 장 삭제. DB를 먼저 커밋하고 파일을 지운다."""
    post = post_service.get_editable_post(db, post_id, user)
    image = next((image for image in post.images if image.id == image_id), None)
    if image is None:
        # 다른 글의 사진 id를 보내도 여기서 걸린다.
        raise ImageNotFoundError()

    names = [image.filename, image.thumb_filename]
    db.delete(image)
    db.commit()
    db.expire(post, ["images", "thumbnail_filename"])
    image_storage.remove_files(names)


# ---------- 내부 함수 ----------


def _read_limited(upload: BinaryIO) -> bytes:
    """5MB를 넘는 순간 읽기를 멈추고 거절한다. 큰 파일을 통째로 메모리에 올리지 않기 위해서다."""
    chunks: list[bytes] = []
    size = 0
    while chunk := upload.read(READ_CHUNK):
        size += len(chunk)
        if size > MAX_IMAGE_BYTES:
            raise ImageTooLargeError()
        chunks.append(chunk)
    return b"".join(chunks)


def _reencode(data: bytes) -> tuple[bytes, bytes]:
    """실제 내용으로 형식을 확인하고 (상세용, 썸네일) WebP로 다시 인코딩한다."""
    try:
        # 1단계: 헤더만 읽어 형식과 크기를 본다. 여기서는 픽셀을 풀지 않는다.
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise UnsupportedImageError()
            if probe.width * probe.height > MAX_IMAGE_PIXELS:
                raise UnsupportedImageError("사진 해상도가 너무 큽니다.")
            probe.verify()  # 구조가 깨진 파일을 거른다. (verify 뒤에는 같은 객체를 쓸 수 없어 다시 연다)

        # 2단계: 전체를 풀어 본다. 앞부분만 이미지이고 뒤가 깨진 파일은 여기서 실패한다.
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            # 휴대폰 사진은 회전 정보를 EXIF에 담는다. 메타데이터를 지우기 전에 실제 픽셀을 돌려 둔다.
            image = ImageOps.exif_transpose(source)
            image = _to_web_mode(image)
            return _encode_webp(image, MAX_SIDE), _encode_webp(image, THUMB_SIDE)
    except UnsupportedImageError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError) as exc:
        # 이미지가 아니거나 깨진 파일. 라이브러리 메시지는 화면에 보이지 않게 한 가지 메시지로 바꾼다.
        raise UnsupportedImageError() from exc


def _to_web_mode(image: Image.Image) -> Image.Image:
    """WebP가 저장할 수 있는 RGB/RGBA로 바꾼다. 투명도가 있으면 유지한다."""
    has_alpha = image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info)
    target = "RGBA" if has_alpha else "RGB"
    return image if image.mode == target else image.convert(target)


def _encode_webp(image: Image.Image, max_side: int) -> bytes:
    resized = image.copy()
    resized.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    # info를 비워 EXIF(GPS 위치, 기기 정보)·XMP·ICC 같은 메타데이터가 새 파일로 따라가지 않게 한다.
    resized.info = {}
    buffer = io.BytesIO()
    resized.save(buffer, format="WEBP", quality=WEBP_QUALITY, method=4)
    return buffer.getvalue()


def _insert_into_free_slot(db: Session, post: Post, filename: str, thumb_filename: str) -> PostImage:
    """빈 칸(slot)에 넣는다. 동시에 올린 요청과 칸이 겹치면 unique 제약에 걸리므로 다시 고른다."""
    for _ in range(MAX_IMAGES_PER_POST):
        used = set(db.scalars(select(PostImage.slot).where(PostImage.post_id == post.id)))
        free = [slot for slot in range(MAX_IMAGES_PER_POST) if slot not in used]
        if not free:
            raise TooManyImagesError()
        image = PostImage(post_id=post.id, slot=free[0], filename=filename, thumb_filename=thumb_filename)
        db.add(image)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        db.refresh(image)
        # 글 객체에 남아 있는 예전 사진 목록·썸네일을 다음 조회에서 다시 읽게 한다.
        db.expire(post, ["images", "thumbnail_filename"])
        return image
    raise TooManyImagesError()


def _check_rate_limit(db: Session, user: User) -> None:
    # 쪽지 도배 제한과 같은 방식: 저장된 created_at과 같은 기준인 DB 시간으로 최근 업로드 수를 센다.
    # 지금 남아 있는 사진만 세므로, 올렸다 지우기를 반복하면 덜 센다. (README 향후 개선 참고)
    db_now = db.scalar(select(func.now()))
    since = db_now - timedelta(seconds=IMAGE_UPLOAD_RATE_LIMIT.window_seconds)
    recent = db.scalar(
        select(func.count())
        .select_from(PostImage)
        .join(Post, PostImage.post_id == Post.id)
        .where(Post.seller_id == user.id, PostImage.created_at > since)
    )
    if (recent or 0) >= IMAGE_UPLOAD_RATE_LIMIT.max_uploads:
        raise ImageUploadRateLimitError(retry_after=IMAGE_UPLOAD_RATE_LIMIT.window_seconds)
