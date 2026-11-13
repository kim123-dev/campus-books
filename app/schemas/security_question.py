"""본인 확인 질문: 준비된 질문 목록, 답 정리 규칙, 등록·변경 요청.

질문 목록은 화면(static/js/security-question.js)에도 같은 내용이 있고, 테스트가 둘이 같은지 확인한다.
"""

import unicodedata
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

# 답이 몇 개 안 되는 질문(색·숫자·혈액형·출신 도시), 공개된 정보(출신 학교), SNS에 자주 올라오는 것(반려동물 이름)은
# 넣지 않았다. 답이 다양하고 남이 알기 어려우면서, 본인은 몇 년 뒤에도 똑같이 적을 수 있는 질문만 둔다.
PRESET_QUESTIONS: dict[str, str] = {
    "CHILDHOOD_SHOP": "어릴 때 살던 동네에서 자주 가던 가게 이름은?",
    "FIRST_BOOK_OR_ALBUM": "처음으로 산 책이나 음반의 제목은?",
    "CHILDHOOD_FRIEND_NICKNAME": "초등학교 때 가장 친했던 친구의 별명은?",
    "FIRST_PART_TIME_JOB": "처음 아르바이트한 곳의 이름은?",
    "CHILDHOOD_TOY_NAME": "어릴 때 아끼던 인형이나 장난감에 붙인 이름은?",
    "SCHOOL_CLUB": "중·고등학교 때 들었던 동아리 이름은?",
    "FIRST_AWARD": "처음으로 받은 상장의 이름은?",
    "FAMILY_RESTAURANT": "어릴 때 가족끼리 자주 가던 식당 이름은?",
    "FIRST_SOLO_TRIP_STAY": "처음 혼자 여행 간 곳에서 묵은 숙소나 동네 이름은?",
}

CUSTOM_QUESTION_MIN = 5
CUSTOM_QUESTION_MAX = 60
ANSWER_MIN = 2
ANSWER_MAX = 20
# 정리하기 전 원문 길이 상한. 공백을 많이 넣은 긴 입력을 정리 단계 전에 거른다.
ANSWER_RAW_MAX = 100


def normalize_answer(value: str) -> str:
    """답을 비교할 모양으로 맞춘다. 전각·반각 같은 모양 차이(NFKC), 대소문자, 모든 공백을 무시한다.
    "Happy Mart"와 "happymart", "해피 마트"와 "해피마트"를 같은 답으로 본다.
    """
    return "".join(unicodedata.normalize("NFKC", value).lower().split())


class SecurityQuestionInput(BaseModel):
    """질문 하나와 답. question_key(준비된 질문)와 custom_question(직접 만든 질문) 중 하나만 보낸다."""

    model_config = ConfigDict(extra="forbid")

    question_key: str | None = None
    custom_question: str | None = Field(default=None, min_length=CUSTOM_QUESTION_MIN, max_length=CUSTOM_QUESTION_MAX)
    answer: str = Field(max_length=ANSWER_RAW_MAX)

    @field_validator("custom_question", mode="before")
    @classmethod
    def strip_question(cls, value: Any) -> Any:
        # 빈 칸(공백만)은 "보내지 않음"으로 본다. 화면이 두 칸을 모두 보내도 고른 쪽만 남는다.
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("question_key")
    @classmethod
    def check_key(cls, value: str | None) -> str | None:
        if value is not None and value not in PRESET_QUESTIONS:
            raise ValueError("목록에 있는 질문을 골라 주세요.")
        return value

    @field_validator("answer")
    @classmethod
    def check_answer(cls, value: str) -> str:
        normalized = normalize_answer(value)
        if len(normalized) < ANSWER_MIN:
            raise ValueError(f"답은 공백을 빼고 {ANSWER_MIN}자 이상이어야 합니다.")
        if len(normalized) > ANSWER_MAX:
            raise ValueError(f"답은 공백을 빼고 {ANSWER_MAX}자 이하여야 합니다.")
        return value

    @model_validator(mode="after")
    def check_question(self) -> "SecurityQuestionInput":
        if (self.question_key is None) == (self.custom_question is None):
            raise ValueError("질문을 하나 고르거나 직접 입력해 주세요.")
        # 질문만 보고 답을 알 수 있으면 안 된다. 같은 답, 질문 안에 그대로 들어 있는 답은 거절한다.
        question = normalize_answer(self.question_text)
        if normalize_answer(self.answer) in question:
            raise ValueError("답이 질문 안에 그대로 들어 있어요. 질문만 보고 알 수 없는 답으로 정해 주세요.")
        return self

    @property
    def question_text(self) -> str:
        return self.custom_question if self.custom_question is not None else PRESET_QUESTIONS[self.question_key]


class SecurityQuestionUpdate(BaseModel):
    """내 정보에서 질문·답 등록·변경. 토큰만 훔친 사람이 질문을 바꿔 계정을 가져가지 못하게 현재 비밀번호를 받는다."""

    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1)
    security_question: SecurityQuestionInput


class PasswordResetQuestionRequest(BaseModel):
    """재설정 1단계: 이메일로 질문 받기. 이메일이 서버 접속 기록(주소)에 남지 않게 POST 본문으로 받는다."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    # 가입·로그인과 같은 규칙으로 소문자로 맞춘다.
    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class PasswordResetQuestionResponse(BaseModel):
    """그 계정의 질문. 계정이 없거나 질문을 쓸 수 없는 계정이면 이메일마다 늘 같은 "그럴듯한 질문"이다."""

    question: str


class PasswordResetVerifyResponse(BaseModel):
    """답이 맞았을 때 주는 일회용 확인증. 새 비밀번호를 정할 때(POST /auth/password-reset) 그대로 보낸다."""

    reset_token: str
    expires_in: int = Field(description="확인증이 유효한 시간(초)")


class PasswordResetNoticeResponse(BaseModel):
    """아직 확인하지 않은 재설정 안내. method: QUESTION(본인 확인 질문) 또는 SERVER(서버 명령)."""

    reset_at: datetime
    method: str
