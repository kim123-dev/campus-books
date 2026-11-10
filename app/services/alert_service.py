"""찾는 교재 알림: 조건 등록·삭제, 새 글과 조건 매칭, 알림 목록·읽음 처리.

매칭은 검색(post_service._search_conditions)과 같은 의미로 한다: 부분 일치, 대소문자 무시,
%·_ 는 글자 그대로. 다만 방향이 반대라("글들 중 키워드를 포함한 것"이 아니라 "이 글이 포함하는
키워드들") SQL LIKE를 재사용하지 않는다. 가격·본인·차단·중복 조건은 SQL로 먼저 좁히고, 남은
조건의 키워드만 파이썬 문자열 비교로 확인한다. 와일드카드가 없어 이스케이프가 필요 없다.

글 제목은 보지 않는다. "운영체제 말고 자료구조 팝니다" 같은 제목 때문에 엉뚱한 알림이 가지 않게 하기 위해서다.
알림은 다른 사람의 판매 중(ON_SALE)인 글에만 만든다. (예약 중·판매 완료 글은 지금 살 수 없다)
"""

from sqlalchemy import ColumnElement, delete, func, or_, select, update
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import AlertNotFoundError, DuplicateAlertError, TooManyAlertsError
from app.models import MAX_ALERTS_PER_USER, AlertNotification, BookAlert, Post, PostStatus, User, UserBlock
from app.schemas.alert import AlertCreate
from app.services import block_service

# 글 수정에서 이 필드가 바뀔 때만 다시 매칭한다. 제목·설명은 매칭에 쓰지 않는다.
MATCH_FIELDS = ("book_title", "course_name", "price")


# ---------- 조건 등록·삭제 ----------


def list_alerts(db: Session, user: User) -> list[BookAlert]:
    """내 조건 목록(등록한 순서 최신순)."""
    return list(
        db.scalars(
            select(BookAlert)
            .where(BookAlert.user_id == user.id)
            .order_by(BookAlert.created_at.desc(), BookAlert.id.desc())
        )
    )


def create_alert(db: Session, user: User, data: AlertCreate) -> BookAlert:
    """조건 등록. 순서: 409 같은 키워드(대소문자 무시) → 400 개수 초과."""
    duplicate = db.scalar(
        select(BookAlert.id).where(
            BookAlert.user_id == user.id, func.lower(BookAlert.keyword) == data.keyword.lower()
        )
    )
    if duplicate is not None:
        raise DuplicateAlertError()
    count = db.scalar(select(func.count()).select_from(BookAlert).where(BookAlert.user_id == user.id)) or 0
    if count >= MAX_ALERTS_PER_USER:
        raise TooManyAlertsError(f"찾는 교재는 최대 {MAX_ALERTS_PER_USER}개까지 등록할 수 있습니다.")

    alert = BookAlert(user_id=user.id, keyword=data.keyword, max_price=data.max_price)
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def delete_alert(db: Session, alert_id: int, user: User) -> None:
    """조건 삭제. 없거나 남의 조건이면 404. (남의 조건이 있는지 드러내지 않는다)
    이미 받은 알림은 지우지 않는다. 알림에 키워드 사본이 있어 그대로 보여줄 수 있다.
    """
    alert = db.get(BookAlert, alert_id)
    if alert is None or alert.user_id != user.id:
        raise AlertNotFoundError()
    db.delete(alert)
    db.commit()


# ---------- 매칭 (글 작성·수정에서 호출, 커밋은 호출한 쪽) ----------


def keyword_matches(keyword: str, post: Post) -> bool:
    """키워드가 교재명이나 과목명에 들어 있으면 True. 대소문자는 무시한다."""
    needle = keyword.lower()
    return needle in post.book_title.lower() or (
        post.course_name is not None and needle in post.course_name.lower()
    )


def match_fields_changed(post: Post, changes: dict) -> bool:
    """수정 요청이 매칭에 쓰는 필드(교재명·과목명·가격)를 실제로 바꾸는지."""
    return any(field in changes and changes[field] != getattr(post, field) for field in MATCH_FIELDS)


def notify_matching(db: Session, post: Post) -> int:
    """이 글에 맞는 조건을 가진 사람들에게 알림을 만든다(커밋 전). 만든 알림 수를 돌려준다.

    - 판매 중인 글만. 예약 중인 글을 수정해 조건에 새로 맞아도 알리지 않는다.
    - 내 글, 내가 차단한 판매자의 글은 제외한다. (글 목록과 같은 기준: 내가 한 차단만 본다)
    - 이미 이 글로 알림을 받은 사람은 건너뛴다. 그래서 글 수정 때 다시 불러도 새로 맞게 된 사람만 받는다.
    """
    if post.status != PostStatus.ON_SALE:
        return 0
    # post.id가 있어야 하므로, 새 글은 호출 전에 flush해 둔다.
    blockers_of_seller = select(UserBlock.blocker_id).where(UserBlock.blocked_id == post.seller_id)
    already_notified = select(AlertNotification.user_id).where(AlertNotification.post_id == post.id)
    candidates = db.scalars(
        select(BookAlert)
        .where(
            BookAlert.user_id != post.seller_id,
            or_(BookAlert.max_price.is_(None), BookAlert.max_price >= post.price),
            BookAlert.user_id.not_in(blockers_of_seller),
            BookAlert.user_id.not_in(already_notified),
        )
        # 한 사람의 조건이 여러 개 맞으면 먼저 등록한 조건의 키워드로 알림을 하나만 만든다.
        .order_by(BookAlert.id)
    ).all()

    notified: set[int] = set()
    for alert in candidates:
        if alert.user_id in notified or not keyword_matches(alert.keyword, post):
            continue
        db.add(AlertNotification(user_id=alert.user_id, post_id=post.id, keyword=alert.keyword))
        notified.add(alert.user_id)
    # 같은 글을 동시에 두 번 수정하는 경우(작성자 본인의 중복 요청)에만 unique 제약에 걸릴 수 있다.
    # 그때는 수정 요청 하나가 실패하고 다시 시도하면 되므로 따로 처리하지 않는다.
    return len(notified)


# ---------- 알림 목록·읽음 ----------


def _visible_conditions(user: User) -> list[ColumnElement[bool]]:
    # 알림을 받은 뒤 판매자를 차단했으면 목록과 개수에서 뺀다. (글 목록과 같은 기준)
    return [
        AlertNotification.user_id == user.id,
        Post.seller_id.not_in(block_service.blocked_ids_query(user.id)),
    ]


def list_notifications(
    db: Session, user: User, page: int, size: int
) -> tuple[list[AlertNotification], int]:
    """내 알림 목록(최신순)."""
    conditions = _visible_conditions(user)
    total = (
        db.scalar(
            select(func.count())
            .select_from(AlertNotification)
            .join(Post, Post.id == AlertNotification.post_id)
            .where(*conditions)
        )
        or 0
    )
    items = db.scalars(
        select(AlertNotification)
        .join(Post, Post.id == AlertNotification.post_id)
        .options(joinedload(AlertNotification.post))
        .where(*conditions)
        # SQLite는 시간을 초 단위로 저장하므로 같은 초의 알림은 id로 순서를 고정한다.
        .order_by(AlertNotification.created_at.desc(), AlertNotification.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return list(items), total


def count_unread(db: Session, user: User) -> int:
    """헤더 배지용 안 읽은 알림 수."""
    return (
        db.scalar(
            select(func.count())
            .select_from(AlertNotification)
            .join(Post, Post.id == AlertNotification.post_id)
            .where(*_visible_conditions(user), AlertNotification.read_at.is_(None))
        )
        or 0
    )


def mark_all_read(db: Session, user: User) -> None:
    """내 알림을 모두 읽음 처리한다. 알림 화면이 목록을 그린 뒤 부른다."""
    db.execute(
        update(AlertNotification)
        .where(AlertNotification.user_id == user.id, AlertNotification.read_at.is_(None))
        .values(read_at=func.now())
    )
    db.commit()


# ---------- 정리 (SQLite는 FK의 CASCADE를 실행하지 않으므로 직접 지운다) ----------


def delete_for_post(db: Session, post_id: int) -> None:
    """글 삭제 때 그 글의 알림을 지운다(커밋 전)."""
    db.execute(delete(AlertNotification).where(AlertNotification.post_id == post_id))


def delete_for_user(db: Session, user_id: int) -> None:
    """회원 탈퇴 때 내 조건과 알림을 지운다(커밋 전)."""
    db.execute(delete(AlertNotification).where(AlertNotification.user_id == user_id))
    db.execute(delete(BookAlert).where(BookAlert.user_id == user_id))
