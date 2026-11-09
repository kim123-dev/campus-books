"""찜(관심 목록) 추가·해제·조회.

추가와 해제는 같은 요청을 여러 번 보내도 결과가 같다. (토글이 아니라 POST·DELETE)
더블클릭이나 네트워크 재시도 때 상태가 거꾸로 뒤집히지 않게 하기 위해서다.
"""

from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import CannotWishlistOwnPostError, SoldPostNotWishlistableError
from app.models import Post, PostStatus, User, Wishlist
from app.schemas.post import PostResponse
from app.services import post_service


def add(db: Session, post_id: int, user: User) -> bool:
    """찜 추가. 새로 찜했으면 True, 이미 찜해 둔 글이면 False.
    판정 순서: 404 글 없음 → 400 내 글 → (이미 찜했으면 그대로 성공) → 400 판매 완료 글에 새 찜.
    """
    post = post_service.get_post(db, post_id)
    if post.seller_id == user.id:
        raise CannotWishlistOwnPostError()
    # 찜해 둔 뒤 판매 완료된 글에 다시 요청해도 실패하지 않게, 판매 완료 검사보다 먼저 본다.
    if db.get(Wishlist, (user.id, post.id)) is not None:
        return False
    if post.status == PostStatus.SOLD:
        raise SoldPostNotWishlistableError()

    db.add(Wishlist(user_id=user.id, post_id=post.id))
    try:
        db.commit()
    except IntegrityError:
        # 같은 사용자의 요청 두 개가 동시에 들어와 다른 요청이 먼저 찜했다. 이미 찜한 것으로 본다.
        db.rollback()
        if db.get(Wishlist, (user.id, post.id)) is None:
            raise
        return False
    return True


def remove(db: Session, post_id: int, user: User) -> None:
    """찜 해제. 찜하지 않은 글이어도 성공한다. 글이 없으면 404."""
    post_service.get_post(db, post_id)
    db.execute(delete(Wishlist).where(Wishlist.user_id == user.id, Wishlist.post_id == post_id))
    db.commit()


def list_wishlist(db: Session, user: User, page: int, size: int) -> tuple[list[PostResponse], int]:
    """내 찜 목록(찜한 순서 최신순). 판매 완료된 글도 포함한다."""
    total = db.scalar(select(func.count()).select_from(Wishlist).where(Wishlist.user_id == user.id)) or 0
    posts = db.scalars(
        select(Post)
        .join(Wishlist, Wishlist.post_id == Post.id)
        .options(joinedload(Post.seller))
        .where(Wishlist.user_id == user.id)
        # SQLite는 시간을 초 단위로 저장하므로, 같은 초에 찜한 글은 글 번호 역순으로 순서를 고정한다.
        .order_by(Wishlist.created_at.desc(), Wishlist.post_id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return [_with_flag(post, True) for post in posts], total


def is_wishlisted(db: Session, post_id: int, user: User | None) -> bool | None:
    """상세 화면용 찜 여부. 로그인하지 않았으면 None(알 수 없음)."""
    if user is None:
        return None
    return db.get(Wishlist, (user.id, post_id)) is not None


def with_wishlist_flags(db: Session, posts: Sequence[Post], user: User | None) -> list[PostResponse]:
    """목록 응답에 찜 여부를 채운다. 이 페이지의 글 중 찜한 글을 쿼리 한 번으로 찾는다. (글마다 묻지 않음)"""
    if user is None:
        return [_with_flag(post, None) for post in posts]
    ids = [post.id for post in posts]
    wished = (
        set(db.scalars(select(Wishlist.post_id).where(Wishlist.user_id == user.id, Wishlist.post_id.in_(ids))))
        if ids
        else set()
    )
    return [_with_flag(post, post.id in wished) for post in posts]


# ORM 객체에는 찜 여부 칸이 없으므로 응답 객체에서만 채운다.
def _with_flag(post: Post, flag: bool | None) -> PostResponse:
    return PostResponse.model_validate(post).model_copy(update={"is_wishlisted": flag})
