from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import BCRYPT_MAX_BYTES
from app.models import UserRole


# 가입과 비밀번호 변경이 같은 규칙을 쓰도록 한 곳에 둔다.
# 글자 수 제한(64자)만으로는 한글 비밀번호가 72바이트를 넘을 수 있어 바이트도 검사한다.
def _check_password_bytes(value: str) -> str:
    if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(f"비밀번호는 {BCRYPT_MAX_BYTES}바이트 이하여야 합니다.")
    return value


NewPassword = Annotated[str, Field(min_length=8, max_length=64), AfterValidator(_check_password_bytes)]


class UserCreate(BaseModel):
    """회원가입 요청. 형식이 틀린 입력은 서비스에 닿기 전에 422로 걸러낸다."""

    # role 같은 모르는 필드를 조용히 무시하지 않고 422로 거절한다. 가입으로 관리자가 될 수 없음을 분명히 한다.
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: NewPassword
    nickname: str = Field(min_length=2, max_length=30)

    # 대소문자만 다른 이메일로 중복 가입하는 것을 막기 위해 소문자로 통일한다.
    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()

    # 공백만 넣은 닉네임을 막기 위해 길이 검사 전에(before) 앞뒤 공백을 제거한다.
    @field_validator("nickname", mode="before")
    @classmethod
    def strip_nickname(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


# 탈퇴한 계정은 닉네임을 이 값으로 시작하게 바꾼다(account_service.erase_account). 다른 사람이 같은 모양의
# 닉네임을 쓰면 관리 화면에서 탈퇴 계정처럼 보이므로 닉네임 변경에서 막는다.
WITHDRAWN_NICKNAME_PREFIX = "withdrawn-"


class NicknameUpdate(BaseModel):
    """닉네임 변경 요청. 가입과 같은 규칙(앞뒤 공백 제거, 2~30자)으로 검사한다."""

    model_config = ConfigDict(extra="forbid")

    nickname: str = Field(min_length=2, max_length=30)

    @field_validator("nickname", mode="before")
    @classmethod
    def strip_nickname(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("nickname")
    @classmethod
    def reject_withdrawn_prefix(cls, value: str) -> str:
        if value.lower().startswith(WITHDRAWN_NICKNAME_PREFIX):
            raise ValueError(f"'{WITHDRAWN_NICKNAME_PREFIX}'로 시작하는 닉네임은 쓸 수 없습니다.")
        return value


class UserResponse(BaseModel):
    """회원 정보 응답. password_hash는 포함하지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    nickname: str
    created_at: datetime


class SignupResponse(UserResponse):
    """가입 응답. 복구 코드 원문은 이 응답에 한 번만 담기고 서버에는 해시만 남는다."""

    recovery_code: str


class MeResponse(UserResponse):
    """내 정보(/users/me)에만 쓰는 응답. 권한과 정지 상태는 본인에게만 보여준다."""

    role: UserRole
    # 정지 중이면 종료 시각(UTC), 아니면 null. 기간이 지난 정지는 null로 보여준다.
    suspended_until: datetime | None = None
    # 닉네임을 다시 바꿀 수 있는 시각(UTC). 지금 바꿀 수 있으면 null. 화면이 변경 버튼 옆에 안내한다.
    nickname_changeable_at: datetime | None = None
    # 복구 코드를 발급받은 시각. 없으면 null이고, 화면이 발급을 권한다. 코드 원문은 다시 보여주지 않는다.
    recovery_code_issued_at: datetime | None = None


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


class PasswordChange(BaseModel):
    """비밀번호 변경 요청. 새 비밀번호는 가입 때와 같은 규칙으로 검사한다."""

    model_config = ConfigDict(extra="forbid")

    # 현재 비밀번호는 맞는지만 확인하므로 빈 값만 막는다. (로그인과 같은 기준)
    current_password: str = Field(min_length=1)
    new_password: NewPassword


class WithdrawRequest(BaseModel):
    """회원 탈퇴 요청. 토큰만 훔친 사람이 계정을 지우지 못하게 비밀번호를 다시 받는다."""

    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1)


class RecoveryCodeIssueRequest(BaseModel):
    """복구 코드 발급·재발급 요청. 토큰만 훔친 사람이 코드를 만들지 못하게 현재 비밀번호를 받는다."""

    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1)


class RecoveryCodeResponse(BaseModel):
    """새 복구 코드. 이 응답에서만 원문을 볼 수 있다."""

    recovery_code: str
    issued_at: datetime


class PasswordResetRequest(BaseModel):
    """비밀번호 재설정 요청 (로그인하지 않은 상태). 새 비밀번호는 가입 때와 같은 규칙으로 검사한다."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    # 모양은 서비스가 맞춰 보고(하이픈·공백·소문자 허용), 틀리면 다른 실패와 같은 400으로 돌려준다.
    recovery_code: str = Field(min_length=1, max_length=64)
    new_password: NewPassword

    # 가입·로그인과 같은 규칙으로 소문자로 맞춘다.
    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class PasswordResetResponse(BaseModel):
    """재설정 성공. 쓴 코드는 소모되었으므로 다음에 쓸 새 코드를 한 번 보여준다."""

    recovery_code: str
