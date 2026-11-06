from sqlalchemy.orm import Session

from app.models import User


# 없으면 None을 돌려주고, 없을 때 어떤 에러로 볼지는 호출하는 쪽이 정한다.
# (인증에서는 401, 다른 기능에서는 404처럼 상황마다 의미가 다르기 때문)
def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)
