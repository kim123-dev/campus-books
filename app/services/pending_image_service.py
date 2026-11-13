"""임시 사진: 글에 붙기 전에 미리 올려 둔 사진의 보관·삭제·글에 붙이기.

글쓰기 화면은 사진을 고르는 즉시 올려 두고(POST /pending-images), 글을 저장할 때 번호만 보낸다.
그래서 글을 쓰는 동안 업로드가 끝나고, 글과 사진이 한 트랜잭션으로 함께 저장된다.

- 파일은 공개 주소가 없는 폴더(uploads/pending/)에 두었다가, 글에 붙일 때 판매글 사진 폴더로 옮긴다.
- 사진 검사·다시 인코딩은 image_service가 하고, 여기서는 이미 만들어진 WebP 바이트만 다룬다.
  (image_service와 post_service가 모두 이 모듈을 쓰므로, 이 모듈은 두 서비스를 불러오지 않는다)
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ImageNotFoundError, PendingImageMissingError, TooManyImagesError
from app.models import MAX_IMAGES_PER_POST, PendingImage, PostImage, User
from app.services import image_storage

logger = logging.getLogger(__name__)

# 글에 붙지 않은 임시 사진을 지우는 기준. 글을 쓰다 말고 나간 사진이 서버에 계속 남지 않게 한다.
PENDING_TTL = timedelta(hours=24)
# 한 사람이 쌓아 둘 수 있는 임시 사진 수. 넘으면 가장 오래된 것부터 지운다. (글 2개 분량)
MAX_PENDING_PER_USER = MAX_IMAGES_PER_POST * 2
# 정리 한 번에 지우는 최대 개수. 업로드 요청에 끼워서 하므로 오래 걸리지 않게 한다.
PURGE_BATCH = 100


def create(db: Session, user: User, image_bytes: bytes, thumb_bytes: bytes) -> PendingImage:
    """검사를 마친 사진(상세용, 썸네일)을 임시 사진으로 저장한다."""
    directory = image_storage.get_pending_image_dir()
    filename, thumb_filename = image_storage.new_filenames()
    image_storage.write_files({filename: image_bytes, thumb_filename: thumb_bytes}, directory)

    pending = PendingImage(user_id=user.id, filename=filename, thumb_filename=thumb_filename)
    db.add(pending)
    try:
        db.commit()
    except Exception:
        # DB에 기록하지 못했으면 주인 없는 파일이 남지 않게 지운다.
        db.rollback()
        image_storage.remove_files([filename, thumb_filename], directory)
        raise
    db.refresh(pending)
    _trim_oldest(db, user)
    return pending


def delete_pending(db: Session, user: User, pending_id: int) -> None:
    """임시 사진 한 장 삭제(화면에서 사진을 뺐을 때). 다른 사람의 사진은 없는 것과 똑같이 404다."""
    pending = db.scalar(
        select(PendingImage).where(PendingImage.id == pending_id, PendingImage.user_id == user.id)
    )
    if pending is None:
        raise ImageNotFoundError()
    _delete_rows_and_files(db, [pending])


def attach(db: Session, post_id: int, user: User, pending_ids: list[int], used_slots: set[int]) -> list[str]:
    """임시 사진을 글의 사진으로 바꾼다(커밋 전). 보낸 순서대로 빈 칸에 넣고, 옮긴 파일 이름을 돌려준다.

    호출한 쪽은 커밋이 실패하면 restore_files로 파일을 되돌려야 한다.
    400: 없는(지워진) 임시 사진·남의 사진, 3장 초과.
    """
    if not pending_ids:
        return []
    rows = db.scalars(
        select(PendingImage).where(PendingImage.id.in_(pending_ids), PendingImage.user_id == user.id)
    ).all()
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(pending_ids):
        raise PendingImageMissingError()
    free_slots = [slot for slot in range(MAX_IMAGES_PER_POST) if slot not in used_slots]
    if len(pending_ids) > len(free_slots):
        raise TooManyImagesError()

    names: list[str] = []
    for slot, pending_id in zip(free_slots, pending_ids):
        row = by_id[pending_id]
        # 올린 시각을 그대로 가져가, 업로드 횟수 제한이 글에 붙인 뒤에도 같은 사진을 같은 시각으로 센다.
        db.add(
            PostImage(
                post_id=post_id,
                slot=slot,
                filename=row.filename,
                thumb_filename=row.thumb_filename,
                created_at=row.created_at,
            )
        )
        names += [row.filename, row.thumb_filename]
    # 같은 임시 사진을 두 요청이 동시에 붙이려 하면, 늦은 쪽은 지운 행 수가 모자라 여기서 걸린다.
    deleted = db.execute(delete(PendingImage).where(PendingImage.id.in_(pending_ids)))
    if deleted.rowcount != len(pending_ids):
        raise PendingImageMissingError()
    try:
        # 파일을 먼저 옮기고 커밋한다. 순서가 반대면 옮기기에 실패했을 때 행은 있는데 파일이 없는 사진이 생긴다.
        image_storage.move_files(names, image_storage.get_pending_image_dir(), image_storage.get_image_dir())
    except OSError:
        raise PendingImageMissingError() from None
    return names


def restore_files(names: list[str]) -> None:
    """attach가 옮긴 파일을 임시 폴더로 되돌린다. (글 저장 커밋이 실패했을 때)"""
    if not names:
        return
    try:
        image_storage.move_files(names, image_storage.get_image_dir(), image_storage.get_pending_image_dir())
    except OSError:
        logger.warning("임시 사진 파일을 되돌리지 못했습니다: %s", names, exc_info=True)


def count_since(db: Session, user: User, since: datetime) -> int:
    """since 뒤에 올린, 아직 글에 붙지 않은 임시 사진 수. (업로드 횟수 제한용)"""
    count = db.scalar(
        select(func.count())
        .select_from(PendingImage)
        .where(PendingImage.user_id == user.id, PendingImage.created_at > since)
    )
    return count or 0


def purge_expired(db: Session) -> int:
    """24시간이 지난 임시 사진을 지운다. 업로드 요청과 서버 시작 때 불린다. 지운 수를 돌려준다."""
    # 다른 제한과 같은 방식: 저장된 created_at과 같은 기준인 DB 시간으로 비교한다.
    db_now = db.scalar(select(func.now()))
    expired = db.scalars(
        select(PendingImage)
        .where(PendingImage.created_at < db_now - PENDING_TTL)
        .order_by(PendingImage.id)
        .limit(PURGE_BATCH)
    ).all()
    _delete_rows_and_files(db, list(expired))
    return len(expired)


def delete_for_user(db: Session, user_id: int) -> None:
    """탈퇴하는 사용자의 임시 사진을 지운다(커밋 전).

    파일을 커밋 전에 지운다. 커밋이 실패해 행만 남더라도 임시 사진이라 글에 붙일 때 400으로 안내될 뿐이다.
    """
    rows = db.scalars(select(PendingImage).where(PendingImage.user_id == user_id)).all()
    if not rows:
        return
    names = [name for row in rows for name in (row.filename, row.thumb_filename)]
    db.execute(delete(PendingImage).where(PendingImage.user_id == user_id))
    image_storage.remove_files(names, image_storage.get_pending_image_dir())


# ---------- 내부 함수 ----------


def _trim_oldest(db: Session, user: User) -> None:
    # 최신 MAX_PENDING_PER_USER장만 남긴다. 글을 쓰다 만 사진이 사람마다 끝없이 쌓이지 않게 한다.
    overflow = db.scalars(
        select(PendingImage)
        .where(PendingImage.user_id == user.id)
        .order_by(PendingImage.id.desc())
        .offset(MAX_PENDING_PER_USER)
    ).all()
    _delete_rows_and_files(db, list(overflow))


def _delete_rows_and_files(db: Session, rows: list[PendingImage]) -> None:
    if not rows:
        return
    names = [name for row in rows for name in (row.filename, row.thumb_filename)]
    db.execute(delete(PendingImage).where(PendingImage.id.in_([row.id for row in rows])))
    db.commit()
    # 파일은 DB 커밋이 성공한 뒤에 지운다. (글 삭제와 같은 순서)
    image_storage.remove_files(names, image_storage.get_pending_image_dir())
