"""복구 코드와 비밀번호 재설정.

이메일을 보낼 수단이 없어서 "이메일만 알면 재설정"은 남의 계정을 가져가는 길이 된다. 그래서 가입할 때 한 번만
보여준 복구 코드를 가진 사람만 재설정할 수 있게 한다. 코드를 잃어버리면 재설정할 수 없다는 점은 화면이 안내한다.

- 코드: 헷갈리는 글자(0/O, 1/I/L)를 뺀 31글자에서 16자를 뽑아 4자씩 끊는다(ABCD-EFGH-JKMN-PQRS). 약 79비트.
- 저장: SHA-256 해시만 저장한다. 코드가 충분히 무작위라 느린 해시(bcrypt)가 필요 없고, SECRET_KEY와 묶지 않아
  키를 바꿔도 코드는 그대로 쓸 수 있다.
- 재설정 실패는 이유와 관계없이 같은 400이다(없는 이메일, 틀린 코드, 코드 미발급, 탈퇴). 가입 여부를 숨기기 위해서다.
- 시도 제한: 이메일당 1시간 5회, IP당 1시간 30회. 없는 이메일도 똑같이 센다.
"""

import hashlib
import math
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidRecoveryCodeError, PasswordResetRateLimitError, WrongPasswordError
from app.core.security import hash_password, verify_password
from app.models import AdminActionType, AdminTargetType, PasswordResetAttempt, RecoveryCode, User, UserRole
from app.schemas.user import PasswordResetRequest
from app.services import admin_log_service, email_ban_service, user_service

CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 16
CODE_GROUP = 4

RESET_WINDOW = timedelta(hours=1)
MAX_ATTEMPTS_PER_EMAIL = 5
MAX_ATTEMPTS_PER_IP = 30
# 시도 기록은 제한을 세는 데만 쓰므로 하루가 지나면 지운다. (재설정할 때마다 함께 정리)
ATTEMPT_RETENTION = timedelta(days=1)


def generate_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    return "-".join(raw[i : i + CODE_GROUP] for i in range(0, CODE_LENGTH, CODE_GROUP))


def normalize_code(code: str) -> str:
    """사람이 옮겨 적은 코드를 비교할 모양으로 맞춘다. 소문자, 띄어쓰기, 하이픈은 달라도 같은 코드로 본다."""
    return "".join(ch for ch in code.upper() if ch not in " -\t")


def hash_code(code: str) -> str:
    return hashlib.sha256(normalize_code(code).encode()).hexdigest()


# 없는 이메일에도 같은 비교를 한 번 해서, 응답 시간으로 가입 여부를 알 수 없게 한다.
_DUMMY_HASH = hash_code(generate_code())


def issue(db: Session, user: User) -> tuple[str, RecoveryCode]:
    """새 코드를 만들어 해시를 저장하고(커밋은 호출한 쪽) 원문을 돌려준다. 이전 코드는 이 순간 무효가 된다."""
    code = generate_code()
    row = db.scalar(select(RecoveryCode).where(RecoveryCode.user_id == user.id))
    if row is None:
        row = RecoveryCode(user_id=user.id, code_hash=hash_code(code))
        db.add(row)
    else:
        row.code_hash = hash_code(code)
        # 발급일을 새로 적는다. server_default는 INSERT에만 쓰이므로 직접 넣는다.
        row.created_at = func.now()
    return code, row


def issued_at(db: Session, user: User) -> datetime | None:
    """내 정보 화면이 "코드 있음·발급일"을 보여주고, 없으면 발급을 권하도록 알려준다."""
    return db.scalar(select(RecoveryCode.created_at).where(RecoveryCode.user_id == user.id))


def reissue(db: Session, user: User, password: str) -> tuple[str, datetime]:
    """내 정보에서 발급·재발급. 토큰만 훔친 사람이 코드를 새로 만들어 계정을 가져가지 못하게 비밀번호를 다시 받는다."""
    if not verify_password(password, user.password_hash):
        raise WrongPasswordError()
    code, row = issue(db, user)
    db.commit()
    db.refresh(row)
    return code, row.created_at


def reset_password(db: Session, data: PasswordResetRequest, ip: str) -> str:
    """이메일 + 복구 코드로 비밀번호를 바꾸고, 다음에 쓸 새 코드를 돌려준다.
    순서: 422 형식(스키마) → 429 시도 횟수 초과 → 400 이메일·코드 불일치.

    - 비밀번호 해시가 바뀌므로 이 계정의 기존 토큰은 모두 401이 된다. (토큰의 비밀번호 지문)
    - 정지된 계정도 재설정할 수 있다. 정지는 그대로라 로그인은 여전히 403이다.
    - 관리자 계정이면 관리 기록을 남긴다.
    """
    email_hash = email_ban_service.hash_email(data.email)
    _check_rate_limit(db, email_hash, ip)

    attempt = PasswordResetAttempt(email_hash=email_hash, ip=ip, success=False)
    db.add(attempt)
    # 탈퇴한 계정은 이메일이 지워져 있어 여기서 찾을 수 없다. (없는 이메일과 같은 응답)
    user = db.scalar(select(User).where(User.email == data.email))
    row = db.scalar(select(RecoveryCode).where(RecoveryCode.user_id == user.id)) if user is not None else None
    given = hash_code(data.recovery_code)
    # 사용자나 코드가 없어도 비교는 한 번 한다. compare_digest는 같은 길이 문자열을 일정한 시간에 비교한다.
    matched = hmac.compare_digest(given, row.code_hash if row is not None else _DUMMY_HASH) and row is not None
    if not matched or user is None or user_service.is_withdrawn(user):
        # 실패한 시도도 횟수에 들어가야 하므로 기록을 먼저 저장한다.
        db.commit()
        raise InvalidRecoveryCodeError()

    attempt.success = True
    user.password_hash = hash_password(data.new_password)
    new_code, _ = issue(db, user)
    if user.role == UserRole.ADMIN:
        admin_log_service.record(
            db, user, AdminActionType.RESET_PASSWORD_BY_CODE, AdminTargetType.USER, user.id, target_user_id=user.id
        )
    db.execute(delete(PasswordResetAttempt).where(PasswordResetAttempt.created_at < _db_now(db) - ATTEMPT_RETENTION))
    db.commit()
    return new_code


def delete_for_user(db: Session, user_id: int) -> None:
    """탈퇴할 때 코드를 지운다(커밋은 호출한 쪽)."""
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user_id))


def _db_now(db: Session) -> datetime:
    # 저장된 created_at과 같은 기준으로 비교하도록 DB 시간을 쓴다. (메시지·사진 횟수 제한과 같은 방식)
    return db.scalar(select(func.now()))


def _check_rate_limit(db: Session, email_hash: str, ip: str) -> None:
    since = _db_now(db) - RESET_WINDOW
    for column, value, limit in (
        (PasswordResetAttempt.email_hash, email_hash, MAX_ATTEMPTS_PER_EMAIL),
        (PasswordResetAttempt.ip, ip, MAX_ATTEMPTS_PER_IP),
    ):
        count, oldest = db.execute(
            select(func.count(), func.min(PasswordResetAttempt.created_at)).where(
                column == value, PasswordResetAttempt.created_at > since
            )
        ).one()
        if count >= limit:
            # 가장 오래된 시도가 창 밖으로 나가는 시각까지 기다리면 한 번 더 할 수 있다.
            wait = (user_service.as_utc(oldest) - user_service.as_utc(since)).total_seconds()
            raise PasswordResetRateLimitError(retry_after=max(1, math.ceil(wait)))
