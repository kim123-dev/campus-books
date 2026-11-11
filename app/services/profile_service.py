"""판매자 프로필: 닉네임, 매너 점수, 판매 중인 글, 받은 후기. 로그인 없이도 볼 수 있다."""

from sqlalchemy.orm import Session

from app.core.exceptions import UserNotFoundError
from app.models import Post, User
from app.schemas.review import ProfileResponse, ReviewResponse
from app.services import post_service, review_service, user_service


def get_profile(db: Session, user_id: int) -> ProfileResponse:
    """이메일·권한·정지 여부는 응답에 넣지 않는다."""
    user = _get_user(db, user_id)
    return ProfileResponse(id=user.id, nickname=user.nickname, manner=review_service.manner_summary(db, user.id))


def list_selling_posts(db: Session, user_id: int, page: int, size: int) -> tuple[list[Post], int]:
    _get_user(db, user_id)
    return post_service.list_selling_posts_by_seller(db, user_id, page, size)


def list_reviews(db: Session, user_id: int, page: int, size: int) -> tuple[list[ReviewResponse], int]:
    _get_user(db, user_id)
    return review_service.list_received(db, user_id, page, size)


# 프로필 API의 공통 기준: 없거나 탈퇴한 사용자는 404.
def _get_user(db: Session, user_id: int) -> User:
    user = user_service.get_user_by_id(db, user_id)
    if user is None:
        raise UserNotFoundError()
    return user
