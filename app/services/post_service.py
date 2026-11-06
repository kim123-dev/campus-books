from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import (
    InvalidStatusTransitionError,
    NotPostOwnerError,
    PostNotFoundError,
    SoldPostNotEditableError,
)
from app.models import Post, PostStatus, User
from app.schemas.post import PostCreate, PostSearchParams, PostUpdate

# LIKE 패턴에서 특수문자를 일반 글자로 다루기 위한 이스케이프 문자
LIKE_ESCAPE = "\\"

# 현재 상태에서 바꿀 수 있는 상태 목록. 판매 완료(SOLD)는 되돌릴 수 없는 마지막 상태다.
# 같은 상태로의 변경은 이 표와 상관없이 항상 허용한다(멱등).
ALLOWED_TRANSITIONS: dict[PostStatus, set[PostStatus]] = {
    PostStatus.ON_SALE: {PostStatus.RESERVED, PostStatus.SOLD},
    PostStatus.RESERVED: {PostStatus.ON_SALE, PostStatus.SOLD},
    PostStatus.SOLD: set(),
}


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


def update_post(db: Session, post_id: int, user: User, data: PostUpdate) -> Post:
    """글 내용 수정. 보낸 필드만 바꾸고, 판매 완료된 글은 SoldPostNotEditableError(400)."""
    post = _get_own_post(db, post_id, user)
    if post.status == PostStatus.SOLD:
        raise SoldPostNotEditableError()

    # exclude_unset: 요청에 없던 필드를 None으로 덮어쓰지 않게 한다. 빈 본문이면 아무것도 바뀌지 않는다.
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(post, field, value)
    return _commit_and_refresh(db, post)


def change_status(db: Session, post_id: int, user: User, new_status: PostStatus) -> Post:
    """판매 상태 변경. 허용되지 않은 전이는 InvalidStatusTransitionError(400)."""
    post = _get_own_post(db, post_id, user)
    # 같은 상태 요청은 재시도해도 안전하도록 에러 없이 그대로 돌려준다(SOLD → SOLD 포함).
    if post.status == new_status:
        return post
    if new_status not in ALLOWED_TRANSITIONS[post.status]:
        raise InvalidStatusTransitionError()

    post.status = new_status
    return _commit_and_refresh(db, post)


def delete_post(db: Session, post_id: int, user: User) -> None:
    """글 삭제(hard delete). 판매 완료된 글도 삭제할 수 있다."""
    post = _get_own_post(db, post_id, user)
    db.delete(post)
    db.commit()


def list_posts(
    db: Session, page: int, size: int, search: PostSearchParams | None = None
) -> tuple[list[Post], int]:
    """글 목록(최신순). (현재 페이지 글, 검색 조건에 맞는 전체 글 수)를 돌려준다."""
    conditions = _search_conditions(search) if search is not None else []
    return _paginate(db, page, size, *conditions)


def list_posts_by_seller(
    db: Session, seller_id: int, page: int, size: int
) -> tuple[list[Post], int]:
    """특정 판매자의 글 목록(최신순). 상태와 상관없이 모두 포함한다."""
    return _paginate(db, page, size, Post.seller_id == seller_id)


def _search_conditions(search: PostSearchParams) -> list[ColumnElement[bool]]:
    """검색 조건을 WHERE 절 조건 목록으로 바꾼다. 보내지 않은 조건은 건너뛴다."""
    conditions: list[ColumnElement[bool]] = []

    if search.q is not None:
        pattern = f"%{_escape_like(search.q)}%"
        # 대소문자를 무시해 SQLite와 MySQL의 결과를 같게 맞춘다.
        conditions.append(
            or_(
                Post.title.ilike(pattern, escape=LIKE_ESCAPE),
                Post.book_title.ilike(pattern, escape=LIKE_ESCAPE),
                Post.course_name.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    if search.status is not None:
        conditions.append(Post.status == search.status)
    if search.course_name is not None:
        # 부분 검색은 q가 담당하므로, 과목 필터는 정확히 일치하는 글만 고른다.
        conditions.append(func.lower(Post.course_name) == search.course_name.lower())
    if search.min_price is not None:
        conditions.append(Post.price >= search.min_price)
    if search.max_price is not None:
        conditions.append(Post.price <= search.max_price)
    return conditions


# 사용자가 입력한 %, _ 가 와일드카드로 동작하지 않게 한다.
# 이스케이프 문자 자체도 먼저 바꿔야 "\%" 같은 입력이 잘못 해석되지 않는다.
def _escape_like(text: str) -> str:
    return (
        text.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )


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


# 수정·삭제 API의 공통 순서: 글이 없으면 404, 작성자가 아니면 403.
def _get_own_post(db: Session, post_id: int, user: User) -> Post:
    post = get_post(db, post_id)
    if post.seller_id != user.id:
        raise NotPostOwnerError()
    return post


def _commit_and_refresh(db: Session, post: Post) -> Post:
    # 값이 실제로 바뀐 경우에만 UPDATE가 나가므로, 변경이 없으면 updated_at도 그대로다.
    db.commit()
    # updated_at은 DB가 갱신하므로 다시 읽어와야 응답에 최신 값이 담긴다.
    db.refresh(post)
    return post
