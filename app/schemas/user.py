from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import BCRYPT_MAX_BYTES


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


class LoginForm(BaseModel):
    """로그인 요청(form). OAuth2 규격상 필드 이름은 username이지만 이메일을 받는다."""

    username: EmailStr = Field(description="가입한 이메일")
    # 로그인에서는 길이 규칙을 알려줄 필요가 없으므로 빈 값만 막는다.
    password: str = Field(min_length=1)

    # 가입 때와 같은 규칙으로 소문자로 바꿔야 대소문자와 상관없이 로그인된다.
    @field_validator("username")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class TokenResponse(BaseModel):
    """토큰 응답. Swagger Authorize가 이 형식(access_token, token_type)을 기대한다."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
