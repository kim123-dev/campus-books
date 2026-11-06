from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import PostNotFoundError
from app.models import Post, User
from app.schemas.post import PostCreate


def create_post(db: Session, seller: User, data: PostCreate) -> Post:
    """판매글 작성. status는 모델 기본값(ON_SALE)을 따른다."""
    post = Post(seller_id=seller.id, **data.model_dump())
    db.add(post)
    db.commit()
    # created_at/updated_at은 DB가 채우므로 다시 읽어와야 응답에 담을 수 있다.
    db.refresh(post)
    return post


def get_post(db: Session, post_id: int) -> Post:
    """글 상세 조회. 없으면 PostNotFoundError(404)."""
    post = db.scalar(
        select(Post).options(joinedload(Post.seller)).where(Post.id == post_id)
    )
    if post is None:
        raise PostNotFoundError()
    return post


def list_posts(db: Session, page: int, size: int) -> tuple[list[Post], int]:
    """전체 글 목록(최신순). (현재 페이지 글, 전체 글 수)를 돌려준다."""
    return _paginate(db, page, size)


def list_posts_by_seller(
    db: Session, seller_id: int, page: int, size: int
) -> tuple[list[Post], int]:
    """특정 판매자의 글 목록(최신순). 상태와 상관없이 모두 포함한다."""
    return _paginate(db, page, size, Post.seller_id == seller_id)


# 목록 조회 규칙(정렬, 페이지 계산, 판매자 함께 불러오기)을 한곳에서 관리한다.
def _paginate(
    db: Session, page: int, size: int, *conditions: ColumnElement[bool]
) -> tuple[list[Post], int]:
    total = db.scalar(select(func.count()).select_from(Post).where(*conditions)) or 0

    posts = db.scalars(
        select(Post)
        # 판매자를 JOIN으로 함께 가져와, 글마다 판매자 조회 쿼리가 나가는 N+1을 막는다.
        .options(joinedload(Post.seller))
        .where(*conditions)
        # SQLite는 시간을 초 단위로 저장해 같은 초에 쓴 글이 생길 수 있으므로 id로 한 번 더 정렬한다.
        .order_by(Post.created_at.desc(), Post.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return list(posts), total
