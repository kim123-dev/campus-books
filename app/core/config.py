import hashlib
import hmac
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 배포 플랫폼(Railway 등)은 "postgresql://" 또는 옛 형식 "postgres://"로 주소를 준다.
# SQLAlchemy는 드라이버를 적지 않으면 psycopg2를 찾으므로, 설치한 psycopg(3)를 쓰도록 바꿔 준다.
_POSTGRES_PREFIXES = ("postgres://", "postgresql://")
_PSYCOPG_PREFIX = "postgresql+psycopg://"

# 운영 키가 이보다 짧으면 JWT 위조를 막기 어렵다. (HS256 권장 최소 길이 32바이트)
MIN_PRODUCTION_SECRET_KEY_LENGTH = 32
# 재가입 차단 이메일 해시 키의 운영 최소 길이. 짧으면 흔한 이메일을 대입해 해시를 맞춰 볼 수 있다.
MIN_PRODUCTION_EMAIL_HASH_KEY_LENGTH = 32


class Settings(BaseSettings):
    """환경변수/.env에서 읽는 설정값. 비밀값을 코드에 두지 않기 위해 분리했다."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # development: 로컬 개발, production: 배포 서버. 운영에서는 API 문서를 끄고 설정을 더 엄격히 확인한다.
    ENVIRONMENT: Literal["development", "production"] = "development"
    # 개발 기본값은 SQLite. 운영에서는 PostgreSQL 주소를 환경변수로 넣는다.
    DATABASE_URL: str = "sqlite:///./dev.db"
    # 기본값을 두지 않아, 키 없이 실수로 서버가 뜨는 일을 막는다.
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    # 판매글 사진 저장 폴더. 누구나 받을 수 있는 static/ 밖에 두고, 이미지 전용 API로만 내려준다.
    # 운영에서는 재배포해도 지워지지 않는 영구 디스크(볼륨) 경로를 넣는다.
    UPLOAD_DIR: str = "./uploads"
    # bcrypt 작업 비용(2의 거듭제곱 횟수). 운영 기본값 12는 bcrypt 라이브러리 기본값과 같다.
    # 테스트만 4(허용 최솟값)로 낮춰 가입·로그인이 많은 테스트를 빠르게 한다. (tests/conftest.py)
    BCRYPT_ROUNDS: int = Field(default=12, ge=4, le=31)
    # 강제 탈퇴한 이메일의 재가입 차단에 쓰는 HMAC 키. 이메일 원문 대신 이 키로 만든 해시만 저장한다.
    # SECRET_KEY와 따로 두는 이유: 토큰 키를 바꿔도(유출 대응 등) 차단 목록이 그대로 맞아야 하기 때문이다.
    # 운영에서는 필수다. 개발·테스트에서 비워 두면 SECRET_KEY에서 만든 값을 쓴다.
    EMAIL_HASH_KEY: str | None = None

    @property
    def email_hash_key(self) -> bytes:
        if self.EMAIL_HASH_KEY:
            return self.EMAIL_HASH_KEY.encode()
        return hmac.new(self.SECRET_KEY.encode(), b"email-ban", hashlib.sha256).digest()

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @field_validator("DATABASE_URL")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        for prefix in _POSTGRES_PREFIXES:
            if value.startswith(prefix):
                return _PSYCOPG_PREFIX + value.removeprefix(prefix)
        return value

    # 운영에서 설정을 빠뜨리면 서버가 떠도 데이터가 사라지거나 토큰이 위조될 수 있으므로, 아예 시작하지 않게 한다.
    @model_validator(mode="after")
    def check_production(self) -> "Settings":
        if not self.is_production:
            return self
        if self.DATABASE_URL.startswith("sqlite"):
            # 배포 서버의 디스크는 재배포 때 초기화되므로 SQLite 파일이 통째로 사라진다.
            raise ValueError("운영(production)에서는 DATABASE_URL에 PostgreSQL 주소를 넣어야 합니다.")
        if len(self.SECRET_KEY) < MIN_PRODUCTION_SECRET_KEY_LENGTH:
            raise ValueError(
                f"운영(production) SECRET_KEY는 {MIN_PRODUCTION_SECRET_KEY_LENGTH}자 이상이어야 합니다."
            )
        if len(self.EMAIL_HASH_KEY or "") < MIN_PRODUCTION_EMAIL_HASH_KEY_LENGTH:
            raise ValueError(
                f"운영(production)에서는 EMAIL_HASH_KEY를 {MIN_PRODUCTION_EMAIL_HASH_KEY_LENGTH}자 이상으로 넣어야 합니다."
            )
        if self.EMAIL_HASH_KEY == self.SECRET_KEY:
            raise ValueError("EMAIL_HASH_KEY는 SECRET_KEY와 다른 값이어야 합니다.")
        return self


# 매 요청마다 .env를 다시 읽지 않도록 한 번만 생성해 재사용한다.
@lru_cache
def get_settings() -> Settings:
    return Settings()
