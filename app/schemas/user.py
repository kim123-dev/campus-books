from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# bcrypt는 72바이트를 넘는 비밀번호를 처리하지 못한다. (한글은 1자 = 3바이트)
BCRYPT_MAX_BYTES = 72


class UserCreate(BaseModel):
    """회원가입 요청. 형식이 틀린 입력은 서비스에 닿기 전에 422로 걸러낸다."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=64)
    nickname: str = Field(min_length=2, max_length=30)

    # 대소문자만 다른 이메일로 중복 가입하는 것을 막기 위해 소문자로 통일한다.
    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()

    # 글자 수 제한(64자)만으로는 한글 비밀번호가 72바이트를 넘을 수 있어 바이트도 검사한다.
    @field_validator("password")
    @classmethod
    def check_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
            raise ValueError(f"비밀번호는 {BCRYPT_MAX_BYTES}바이트 이하여야 합니다.")
        return value

    # 공백만 넣은 닉네임을 막기 위해 길이 검사 전에(before) 앞뒤 공백을 제거한다.
    @field_validator("nickname", mode="before")
    @classmethod
    def strip_nickname(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class UserResponse(BaseModel):
    """회원 정보 응답. password_hash는 포함하지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    nickname: str
    created_at: datetime
