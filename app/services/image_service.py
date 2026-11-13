"""판매글 사진 업로드·삭제.

보안 규칙
- 확장자나 브라우저가 보낸 Content-Type이 아니라, Pillow로 실제 내용을 열어 형식을 확인한다.
- 원본 바이트를 그대로 저장하지 않고 다시 인코딩한다. 이미지에 숨겨 붙인 내용과
  사진의 GPS 위치 같은 메타데이터(EXIF)가 저장되지 않는다.
- 파일 이름은 서버가 새로 만든다. (image_storage)
"""

import io
import logging
import threading
from dataclasses import dataclass
from datetime import timedelta
from typing import BinaryIO

import pillow_heif
from PIL import ExifTags, Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BrokenImageError,
    ImageNotFoundError,
    ImageResolutionTooLargeError,
    ImageTooLargeError,
    ImageUploadRateLimitError,
    TooManyImagesError,
    UnsupportedImageError,
)
from app.models import MAX_IMAGES_PER_POST, Post, PostImage, User
from app.services import image_storage, post_service

# 장당 25MB. 화면이 보통 2000px JPEG(1MB 안팎)로 줄여 보내므로, 이 한도는 화면이 줄이지 못한
# 사진(예: 안드로이드 크롬이 못 여는 HEIC)을 원본 그대로 받을 때를 위한 것이다.
MAX_IMAGE_BYTES = 25 * 1024 * 1024
# 작은 파일이 풀면 거대한 이미지가 되어 메모리를 다 쓰는 공격(decompression bomb)을 막는다.
# JPEG(MPO 포함)는 처음부터 1/2·1/4·1/8 크기로 풀 수 있어(draft) 2억 화소도 메모리를 적게 쓴다.
# 나머지 형식은 원래 크기로 다 풀어야 하므로 5천만 화소(5천만 화소 휴대폰 카메라 원본)까지만 받는다.
MAX_JPEG_PIXELS = 200_000_000
MAX_OTHER_PIXELS = 50_000_000
# Pillow 자체의 폭탄 검사(기본 약 9천만 화소)가 위 JPEG 한도보다 먼저 막지 않게 맞춘다.
# 형식별 한도는 _reencode가 픽셀을 풀기 전에 직접 검사한다.
Image.MAX_IMAGE_PIXELS = MAX_JPEG_PIXELS
# MPO: 갤럭시 등의 "울트라 HDR"·움직이는 사진처럼 JPEG 안에 사진이 여러 장 든 형식. 첫 장만 쓴다.
# HEIF: 아이폰 기본 사진 형식(HEIC). pillow-heif가 Pillow에 여는 방법을 더한다.
JPEG_FORMATS = {"JPEG", "MPO"}
ALLOWED_FORMATS = JPEG_FORMATS | {"PNG", "WEBP", "HEIF"}
MAX_SIDE = 1600  # 상세 화면용 사진의 긴 변
THUMB_SIDE = 400  # 목록 카드용 썸네일의 긴 변
WEBP_QUALITY = 85
# 5천만 화소 PNG·HEIC 한 장을 푸는 데 메모리를 350~430MB 쓴다. (JPEG는 draft 덕분에 2억 화소도 약 30MB)
# 배포 서버 메모리 한도가 1GB(평소 약 110MB 사용)라 2장을 동시에 풀면 한도에 가까워지므로 한 번에 1장만 처리한다.
# 한 장 처리는 2초 안쪽이라, 동시에 올린 다른 요청은 잠깐 기다리면 된다.
MAX_CONCURRENT_DECODES = 1
_decode_slots = threading.BoundedSemaphore(MAX_CONCURRENT_DECODES)
READ_CHUNK = 64 * 1024

pillow_heif.register_heif_opener()

# EXIF 회전 값(Orientation)별로 똑바로 세우는 방법. Pillow의 ImageOps.exif_transpose와 같은 표다.
_ORIENTATION_TRANSPOSE = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UploadRateLimit:
    """window_seconds초 안에 max_uploads장까지 올릴 수 있다."""

    max_uploads: int
    window_seconds: int


# 업로드 횟수 제한. 다시 인코딩하느라 CPU를 많이 쓰므로 한 사용자가 몰아서 올리지 못하게 한다.
# 이 값 하나만 바꾸면 된다.
IMAGE_UPLOAD_RATE_LIMIT = UploadRateLimit(max_uploads=20, window_seconds=600)


def add_image(db: Session, post_id: int, user: User, upload: BinaryIO) -> PostImage:
    """사진 한 장 추가. 판정 순서: 404 글 없음 → 403 작성자 아님 → 400 판매 완료 → 400 3장 → 429 → 413/422.

    형식: JPG(MPO 포함)·PNG·WebP·HEIC. 큰 사진은 한 번에 1장만 풀고, 나머지 요청은 순서를 기다린다.
    """
    post = post_service.get_editable_post(db, post_id, user)
    if len(post.images) >= MAX_IMAGES_PER_POST:
        raise TooManyImagesError()
    _check_rate_limit(db, user)

    # 무거운 처리(읽기·디코딩)는 싼 검사를 모두 통과한 뒤에 한다.
    image_bytes, thumb_bytes = process_upload(upload, user)
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


def process_upload(upload: BinaryIO, user: User) -> tuple[bytes, bytes]:
    """업로드 파일을 검사하고 (상세용, 썸네일) WebP 바이트로 만든다. 판매글 사진과 쪽지 사진이 함께 쓴다.

    413(25MB)·422(형식·해상도·손상). 메모리를 많이 쓰는 디코딩은 서버 전체에서 한 번에 1장만 한다.
    순서를 기다리는 동안에는 업로드 파일이 디스크 임시 파일에 있다. 차례가 오면 메모리로 읽어 처리한다.
    """
    with _decode_slots:
        return _reencode(_read_limited(upload, user), user)


# ---------- 내부 함수 ----------


def _read_limited(upload: BinaryIO, user: User) -> bytes:
    """25MB를 넘는 순간 읽기를 멈추고 거절한다. 큰 파일을 통째로 메모리에 올리지 않기 위해서다."""
    chunks: list[bytes] = []
    size = 0
    while chunk := upload.read(READ_CHUNK):
        size += len(chunk)
        if size > MAX_IMAGE_BYTES:
            _log_rejection(user, "bytes", f"over {MAX_IMAGE_BYTES}")
            raise ImageTooLargeError()
        chunks.append(chunk)
    return b"".join(chunks)


def _reencode(data: bytes, user: User) -> tuple[bytes, bytes]:
    """실제 내용으로 형식을 확인하고 (상세용, 썸네일) WebP로 다시 인코딩한다."""
    try:
        # 1단계: 헤더만 읽어 형식과 크기를 본다. 여기서는 픽셀을 풀지 않는다.
        with Image.open(io.BytesIO(data)) as probe:
            fmt, size = probe.format, probe.size
            if fmt not in ALLOWED_FORMATS:
                _log_rejection(user, "format", str(fmt))
                raise UnsupportedImageError()
            limit = MAX_JPEG_PIXELS if fmt in JPEG_FORMATS else MAX_OTHER_PIXELS
            if size[0] * size[1] > limit:
                _log_rejection(user, "pixels", f"{fmt} {size[0]}x{size[1]}")
                raise ImageResolutionTooLargeError()
            probe.verify()  # 구조가 깨진 파일을 거른다. (verify 뒤에는 같은 객체를 쓸 수 없어 다시 연다)

        # 2단계: 전체를 풀어 본다. 앞부분만 이미지이고 뒤가 깨진 파일은 여기서 실패한다.
        with Image.open(io.BytesIO(data)) as source:
            if fmt in JPEG_FORMATS:
                # 긴 변이 MAX_SIDE 이상 남는 가장 작은 배율(1/2·1/4·1/8)로 푼다. 2억 화소 사진도 수백만 화소로 풀린다.
                scale = MAX_SIDE / max(size)
                source.draft("RGB", (max(1, int(size[0] * scale)), max(1, int(size[1] * scale))))
            source.load()
            # 휴대폰 사진은 회전 정보를 EXIF에 담는다. 메타데이터를 지우기 전에 실제 픽셀을 돌려 둔다.
            # 원본 크기에서 돌리면 원본만 한 사본이 하나 더 생기므로(5천만 화소 PNG면 200MB), 먼저 줄이고 돌린다.
            orientation = source.getexif().get(ExifTags.Base.Orientation)
            image = _to_web_mode(source)
            image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)  # 제자리에서 줄여 원본 픽셀을 놓아준다.
            if (method := _ORIENTATION_TRANSPOSE.get(orientation)) is not None:
                image = image.transpose(method)
            return _encode_webp(image, MAX_SIDE), _encode_webp(image, THUMB_SIDE)
    except (UnsupportedImageError, ImageResolutionTooLargeError):
        raise
    except Image.DecompressionBombError as exc:
        # 한도의 2배를 넘으면 Pillow가 헤더를 읽는 단계에서 먼저 막는다.
        _log_rejection(user, "pixels", "decompression bomb")
        raise ImageResolutionTooLargeError() from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        # 이미지가 아니거나 깨진 파일. 라이브러리 메시지는 화면에 보이지 않게 한 가지 메시지로 바꾼다.
        _log_rejection(user, "broken", type(exc).__name__)
        if isinstance(exc, UnidentifiedImageError):
            raise UnsupportedImageError() from exc
        raise BrokenImageError() from exc


def _log_rejection(user: User, reason: str, detail: str) -> None:
    # 휴대폰 사진이 왜 거절됐는지(형식·해상도·용량·손상) 배포 로그에서 바로 알 수 있게 남긴다. 사진 내용은 남기지 않는다.
    logger.warning("사진 거절: user=%s reason=%s detail=%s", user.id, reason, detail)


def _to_web_mode(image: Image.Image) -> Image.Image:
    """WebP가 저장할 수 있는 RGB/RGBA로 바꾼다. 투명도가 있으면 유지한다."""
    has_alpha = image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info)
    target = "RGBA" if has_alpha else "RGB"
    return image if image.mode == target else image.convert(target)


def _encode_webp(image: Image.Image, max_side: int) -> bytes:
    # 이미 MAX_SIDE 이하로 줄인 사진을 받으므로 사본을 만들어도 작다.
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
