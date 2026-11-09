"""사용자 차단.

차단하면 두 사람 사이에는 새 문의와 쪽지 전송이 막히고(양방향), 차단한 사람의 글 목록에서
차단당한 사람의 글이 빠진다. 누가 나를 차단했는지 알려주는 API는 두지 않는다.
"""

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import CannotBlockSelfError, UserNotFoundError
from app.models import User, UserBlock
from app.schemas.block import BlockedUserResponse, BlockResponse


def block(db: Session, target_id: int, user: User) -> bool:
    """차단. 새로 차단했으면 True, 이미 차단한 사람이면 False. 순서: 404 없는 사용자 → 400 자기 자신."""
    _get_user(db, target_id)
    if target_id == user.id:
        raise CannotBlockSelfError()
    if db.get(UserBlock, (user.id, target_id)) is not None:
        return False

    db.add(UserBlock(blocker_id=user.id, blocked_id=target_id))
    try:
        db.commit()
    except IntegrityError:
        # 같은 요청 두 개가 동시에 들어와 다른 요청이 먼저 차단했다. 이미 차단한 것으로 본다.
        db.rollback()
        if db.get(UserBlock, (user.id, target_id)) is None:
            raise
        return False
    return True


def unblock(db: Session, target_id: int, user: User) -> None:
    """차단 해제. 차단하지 않은 사람이어도 성공한다. 없는 사용자면 404."""
    _get_user(db, target_id)
    db.execute(delete(UserBlock).where(UserBlock.blocker_id == user.id, UserBlock.blocked_id == target_id))
    db.commit()


def list_blocks(db: Session, user: User, page: int, size: int) -> tuple[list[BlockResponse], int]:
    """내가 차단한 사람 목록(차단한 순서 최신순)."""
    total = db.scalar(select(func.count()).select_from(UserBlock).where(UserBlock.blocker_id == user.id)) or 0
    rows = db.execute(
        select(UserBlock, User)
        .join(User, User.id == UserBlock.blocked_id)
        .where(UserBlock.blocker_id == user.id)
        # SQLite는 시간을 초 단위로 저장하므로 같은 초에 차단한 사람은 사용자 번호 역순으로 고정한다.
        .order_by(UserBlock.created_at.desc(), UserBlock.blocked_id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    items = [
        BlockResponse(user=BlockedUserResponse.model_validate(blocked), created_at=row.created_at)
        for row, blocked in rows
    ]
    return items, total


def has_blocked(db: Session, user: User | None, other_id: int) -> bool | None:
    """user가 other를 차단했는지. 로그인하지 않았으면 None(알 수 없음)."""
    if user is None:
        return None
    return db.get(UserBlock, (user.id, other_id)) is not None


def block_state(db: Session, me_id: int, other_id: int) -> tuple[bool, bool]:
    """(내가 상대를 차단했는지, 상대가 나를 차단했는지). 쿼리 한 번으로 양방향을 본다."""
    blockers = set(
        db.scalars(
            select(UserBlock.blocker_id).where(
                or_(
                    (UserBlock.blocker_id == me_id) & (UserBlock.blocked_id == other_id),
                    (UserBlock.blocker_id == other_id) & (UserBlock.blocked_id == me_id),
                )
            )
        )
    )
    return me_id in blockers, other_id in blockers


def blocked_ids_query(user_id: int) -> Select:
    """내가 차단한 사용자 id들. 글 목록 쿼리의 WHERE 안에 하위 쿼리로 넣어 쿼리 수를 늘리지 않는다."""
    return select(UserBlock.blocked_id).where(UserBlock.blocker_id == user_id)


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise UserNotFoundError()
    return user
