from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import DuplicateEmailError, DuplicateNicknameError
from app.core.security import hash_password
from app.models import User
from app.schemas.user import UserCreate


# 미리 중복을 확인해 어떤 값이 겹쳤는지 구분된 에러를 돌려준다.
def _ensure_unique(db: Session, email: str, nickname: str) -> None:
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise DuplicateEmailError()
    if db.scalar(select(User.id).where(User.nickname == nickname)) is not None:
        raise DuplicateNicknameError()


def signup(db: Session, data: UserCreate) -> User:
    """회원가입. 중복이면 DuplicateEmailError / DuplicateNicknameError를 던진다."""
    _ensure_unique(db, data.email, data.nickname)

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        nickname=data.nickname,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # 동시에 같은 값으로 가입하면 위 확인을 둘 다 통과할 수 있다.
        # DB unique 제약에 걸린 경우 다시 조회해 어떤 값이 겹쳤는지 알려준다.
        db.rollback()
        _ensure_unique(db, data.email, data.nickname)
        raise
    # created_at은 DB가 채우므로 다시 읽어와야 응답에 담을 수 있다.
    db.refresh(user)
    return user
