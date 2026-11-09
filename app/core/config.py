from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수/.env에서 읽는 설정값. 비밀값을 코드에 두지 않기 위해 분리했다."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # 개발 기본값은 SQLite. 운영에서는 .env에서 MySQL URL로 교체한다.
    DATABASE_URL: str = "sqlite:///./dev.db"
    # 기본값을 두지 않아, 키 없이 실수로 서버가 뜨는 일을 막는다.
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    # 판매글 사진 저장 폴더. 누구나 받을 수 있는 static/ 밖에 두고, 이미지 전용 API로만 내려준다.
    UPLOAD_DIR: str = "./uploads"


# 매 요청마다 .env를 다시 읽지 않도록 한 번만 생성해 재사용한다.
@lru_cache
def get_settings() -> Settings:
    return Settings()
