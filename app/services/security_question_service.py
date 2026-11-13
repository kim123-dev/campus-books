"""본인 확인 질문 등록·변경과 답 확인.

- 답은 정리한 뒤(normalize_answer) SHA-256 16진수로 바꾸고 그 값을 bcrypt로 해시한다. 한글·이모지 답은 20자여도
  72바이트를 넘을 수 있는데, bcrypt는 72바이트까지만 보므로 먼저 고정 길이(64자)로 만든다.
- 관리자는 질문을 쓸 수 없다. 관리자 계정을 질문 하나로 가져갈 수 있으면 피해가 크기 때문이다.
  관리자가 비밀번호를 잊으면 서버 명령(python -m app.cli reset-password)으로 재설정한다.
- 질문으로 비밀번호가 재설정된 뒤 7일 동안은 질문을 바꿀 수 없다. 남이 답을 맞혀 재설정했더라도
  질문까지 바꾸지 못하게 해서, 원래 주인이 같은 답으로 다시 재설정해 계정을 되찾을 수 있게 한다.
"""

import hashlib
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AdminSecurityQuestionError, SecurityQuestionChangeTooSoonError, WrongPasswordError
from app.core.security import hash_password, verify_password
from app.models import PasswordResetMethod, PasswordResetNotice, SecurityQuestion, User, UserRole
from app.schemas.security_question import PRESET_QUESTIONS, SecurityQuestionInput, SecurityQuestionUpdate, normalize_answer
from app.services import user_service

CHANGE_LOCK_AFTER_RESET = timedelta(days=7)


def answer_digest(answer: str) -> str:
    """bcrypt에 넣을 고정 길이 값. 정리한 답의 SHA-256 16진수(64자, 72바이트 안)."""
    return hashlib.sha256(normalize_answer(answer).encode("utf-8")).hexdigest()


def hash_answer(answer: str) -> str:
    return hash_password(answer_digest(answer))


def verify_answer(answer: str, answer_hash: str) -> bool:
    return verify_password(answer_digest(answer), answer_hash)


# 질문이 없는 계정·없는 이메일에도 bcrypt 비교를 한 번 해서, 응답 시간으로 가입 여부를 알 수 없게 한다.
_DUMMY_HASH: str | None = None


def dummy_hash() -> str:
    # bcrypt 비용(BCRYPT_ROUNDS)이 테스트 설정을 읽은 뒤에 정해지도록 처음 쓸 때 만든다.
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_answer("dummy-answer")
    return _DUMMY_HASH


def get_row(db: Session, user_id: int) -> SecurityQuestion | None:
    return db.scalar(select(SecurityQuestion).where(SecurityQuestion.user_id == user_id))


def question_text(row: SecurityQuestion) -> str:
    return row.custom_text if row.custom_text is not None else PRESET_QUESTIONS.get(row.preset_key, "")


def add_for_signup(db: Session, user: User, data: SecurityQuestionInput) -> None:
    """가입할 때 함께 저장한다(커밋은 호출한 쪽). user.id가 있어야 하므로 flush한 뒤에 부른다."""
    db.add(_new_row(user.id, data))


def current_question(db: Session, user: User) -> str | None:
    """내 정보에 보여줄 지금 질문. 없거나 관리자면 None."""
    if user.role == UserRole.ADMIN:
        return None
    row = get_row(db, user.id)
    return question_text(row) if row is not None else None


def changeable_at(db: Session, user: User, now: datetime | None = None) -> datetime | None:
    """질문을 다시 바꿀 수 있는 시각(UTC). 지금 바꿀 수 있으면 None. 질문으로 재설정한 지 7일이 안 됐을 때만 값이 있다."""
    last = db.scalar(
        select(func.max(PasswordResetNotice.reset_at)).where(
            PasswordResetNotice.user_id == user.id, PasswordResetNotice.method == PasswordResetMethod.QUESTION
        )
    )
    if last is None:
        return None
    available = user_service.as_utc(last) + CHANGE_LOCK_AFTER_RESET
    return available if available > (now or user_service.utc_now()) else None


def set_question(db: Session, user: User, data: SecurityQuestionUpdate, now: datetime | None = None) -> None:
    """등록·변경. 순서: 400 관리자 → 400 비밀번호 틀림 → 400 질문으로 재설정한 지 7일 안 됨."""
    if user.role == UserRole.ADMIN:
        raise AdminSecurityQuestionError()
    if not verify_password(data.password, user.password_hash):
        raise WrongPasswordError()
    available = changeable_at(db, user, now)
    if available is not None:
        local = available.astimezone(user_service.KST)
        raise SecurityQuestionChangeTooSoonError(
            "본인 확인 질문으로 비밀번호가 재설정된 뒤 7일 동안은 질문을 바꿀 수 없어요. "
            f"{local.month}월 {local.day}일 {local:%H:%M}부터 바꿀 수 있어요."
        )

    row = get_row(db, user.id)
    if row is None:
        db.add(_new_row(user.id, data.security_question))
    else:
        question = data.security_question
        row.preset_key = question.question_key
        row.custom_text = question.custom_question
        row.answer_hash = hash_answer(question.answer)
        row.updated_at = func.now()
    db.commit()


def delete_for_user(db: Session, user_id: int) -> None:
    """탈퇴할 때 질문과 재설정 안내를 지운다(커밋은 호출한 쪽)."""
    db.execute(delete(SecurityQuestion).where(SecurityQuestion.user_id == user_id))
    db.execute(delete(PasswordResetNotice).where(PasswordResetNotice.user_id == user_id))


def _new_row(user_id: int, data: SecurityQuestionInput) -> SecurityQuestion:
    return SecurityQuestion(
        user_id=user_id,
        preset_key=data.question_key,
        custom_text=data.custom_question,
        answer_hash=hash_answer(data.answer),
    )
