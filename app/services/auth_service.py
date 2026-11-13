from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BannedEmailError,
    DuplicateEmailError,
    DuplicateNicknameError,
    InvalidCredentialsError,
    SuspendedUserError,
)
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.user import LoginForm, SignupResponse, UserCreate, UserResponse
from app.services import email_ban_service, recovery_service, user_service


# 미리 중복을 확인해 어떤 값이 겹쳤는지 구분된 에러를 돌려준다.
def _ensure_unique(db: Session, email: str, nickname: str) -> None:
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise DuplicateEmailError()
    if db.scalar(select(User.id).where(User.nickname == nickname)) is not None:
        raise DuplicateNicknameError()


def signup(db: Session, data: UserCreate) -> SignupResponse:
    """회원가입. 순서: 409 이메일·닉네임 중복 → 400 재가입이 막힌 이메일(강제 탈퇴).
    복구 코드를 함께 만들어 응답에 한 번만 담는다. 사용자와 코드는 같은 트랜잭션으로 저장한다.
    """
    _ensure_unique(db, data.email, data.nickname)
    if email_ban_service.is_banned(db, data.email):
        raise BannedEmailError()

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        nickname=data.nickname,
    )
    db.add(user)
    try:
        # 코드 행이 사용자 id를 가리키므로 먼저 INSERT해 id를 받는다. 중복이면 여기서 IntegrityError가 난다.
        db.flush()
        code, _ = recovery_service.issue(db, user)
        db.commit()
    except IntegrityError:
        # 동시에 같은 값으로 가입하면 위 확인을 둘 다 통과할 수 있다.
        # DB unique 제약에 걸린 경우 다시 조회해 어떤 값이 겹쳤는지 알려준다.
        db.rollback()
        _ensure_unique(db, data.email, data.nickname)
        raise
    # created_at은 DB가 채우므로 다시 읽어와야 응답에 담을 수 있다.
    db.refresh(user)
    return SignupResponse(**UserResponse.model_validate(user).model_dump(), recovery_code=code)


def login(db: Session, data: LoginForm) -> str:
    """로그인. 성공하면 액세스 토큰을, 실패하면 InvalidCredentialsError를 던진다."""
    user = db.scalar(select(User).where(User.email == data.username))
    # 이메일이 없는 경우와 비밀번호가 틀린 경우를 같은 에러로 처리한다.
    if user is None or not verify_password(data.password, user.password_hash):
        raise InvalidCredentialsError()
    # 비밀번호가 맞은 뒤에만 정지 여부를 알려준다. 비밀번호를 모르는 사람은 정지 사실을 알 수 없다.
    end = user_service.active_suspension_end(user)
    if end is not None:
        raise SuspendedUserError(user_service.suspension_message(end))
    return create_access_token(user.id, user.password_hash)
