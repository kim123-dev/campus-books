import hashlib
from dataclasses import dataclass
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
# auto_error=False: 토큰이 없을 때 FastAPI 기본 영어 메시지 대신
# deps.get_current_user에서 우리 예외(한국어 메시지)로 처리하기 위해서다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


# 솔트를 매번 새로 만들어, 같은 비밀번호라도 해시가 달라지게 한다.
# 작업 비용은 설정값을 쓴다. 검증(checkpw)은 해시 안에 적힌 비용을 따르므로 기존 해시도 그대로 확인된다.
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=get_settings().BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


# 해시 안에 솔트가 들어 있어서 별도 저장 없이 검증할 수 있다.
def verify_password(password: str, password_hash: str) -> bool:
    password_bytes = password.encode("utf-8")
    # 72바이트를 넘으면 bcrypt가 예외를 던져 500이 된다.
    # 가입 단계에서 이미 막았으므로 그런 비밀번호는 절대 일치할 수 없어 False로 처리한다.
    if len(password_bytes) > BCRYPT_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))
    except ValueError:
        # bcrypt 형식이 아닌 해시(탈퇴한 계정의 잠금 표시)는 어떤 비밀번호와도 일치하지 않는다.
        return False


def password_fingerprint(password_hash: str) -> str:
    """토큰에 넣을 비밀번호 지문. 비밀번호 해시가 바뀌면 지문도 바뀐다.

    비밀번호를 바꾸면(또는 탈퇴하면) 그 전에 발급한 토큰을 모두 쓸 수 없게 하려고 쓴다.
    토큰 목록을 저장하거나 DB 컬럼을 추가하지 않아도 되는 가장 단순한 방법이다.
    해시의 해시 일부만 넣으므로 토큰을 열어 봐도 비밀번호를 알아낼 수 없다.
    """
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class AccessTokenData:
    user_id: int
    # 발급 당시 비밀번호 지문. 지금 사용자의 지문과 다르면 비밀번호가 바뀐 뒤의 옛 토큰이다.
    password_fingerprint: str


def create_access_token(
    user_id: int, password_hash: str = "", expires_delta: timedelta | None = None
) -> str:
    """액세스 토큰 발급. 만료 시간을 바꿔야 하는 테스트를 위해 expires_delta를 열어둔다."""
    settings = get_settings()
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        # JWT 표준상 sub는 문자열이어야 해서 user id를 문자열로 넣는다.
        "sub": str(user_id),
        "pwd": password_fingerprint(password_hash),
        "exp": datetime.now(UTC) + expires_delta,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> AccessTokenData:
    """토큰을 검증해 user id와 비밀번호 지문을 돌려준다. 만료, 변조, 형식 오류는 모두 InvalidTokenError."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            # 허용 알고리즘을 고정해 alg 헤더를 바꾸는 공격(예: "none")을 막는다.
            algorithms=[ALGORITHM],
            # 지문(pwd)이 없는 토큰(이 기능 전에 발급된 토큰)도 거절한다. 다시 로그인하면 된다.
            options={"require": ["exp", "sub", "pwd"]},
        )
        return AccessTokenData(user_id=int(payload["sub"]), password_fingerprint=str(payload["pwd"]))
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise InvalidTokenError() from exc
