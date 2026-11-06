from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi.security import OAuth2PasswordBearer

from app.core.config import get_settings
from app.core.exceptions import InvalidTokenError

# bcrypt는 72바이트를 넘는 비밀번호를 처리하지 못한다. (한글은 1자 = 3바이트)
BCRYPT_MAX_BYTES = 72
ALGORITHM = "HS256"

# Swagger의 Authorize 버튼이 이 주소로 username/password를 보내 토큰을 받아온다.
# 3단계에서 보호가 필요한 API의 의존성으로 사용한다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# 솔트를 매번 새로 만들어, 같은 비밀번호라도 해시가 달라지게 한다.
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# 해시 안에 솔트가 들어 있어서 별도 저장 없이 검증할 수 있다.
def verify_password(password: str, password_hash: str) -> bool:
    password_bytes = password.encode("utf-8")
    # 72바이트를 넘으면 bcrypt가 예외를 던져 500이 된다.
    # 가입 단계에서 이미 막았으므로 그런 비밀번호는 절대 일치할 수 없어 False로 처리한다.
    if len(password_bytes) > BCRYPT_MAX_BYTES:
        return False
    return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))


def create_access_token(user_id: int, expires_delta: timedelta | None = None) -> str:
    """액세스 토큰 발급. 만료 시간을 바꿔야 하는 테스트를 위해 expires_delta를 열어둔다."""
    settings = get_settings()
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        # JWT 표준상 sub는 문자열이어야 해서 user id를 문자열로 넣는다.
        "sub": str(user_id),
        "exp": datetime.now(UTC) + expires_delta,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int:
    """토큰을 검증하고 user id를 돌려준다. 만료, 변조, 형식 오류는 모두 InvalidTokenError."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            # 허용 알고리즘을 고정해 alg 헤더를 바꾸는 공격(예: "none")을 막는다.
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        return int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise InvalidTokenError() from exc
