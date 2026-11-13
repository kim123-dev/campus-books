"""비밀번호 재설정: 본인 확인 질문(로그인하지 않은 상태)과 서버 명령(관리자 비밀번호 분실).

질문 방식의 흐름: 이메일 → 그 계정의 질문 → 답 + 새 비밀번호.
질문이 하나뿐이라 맞혀 보기를 엄격하게 막는다.
- 이메일당: 최근 24시간에 5번 틀리면 마지막으로 틀린 때부터 24시간 잠근다. 잠긴 동안의 시도는 세지 않는다
  (세면 잠금이 끝없이 늘어난다). 성공하면 그 전의 실패는 더 세지 않는다.
- IP당: 질문 받기와 재설정 시도를 합쳐 1시간 30회.
- 가입 여부를 숨긴다: 없는 이메일, 질문을 등록하지 않은 계정, 탈퇴한 계정, 관리자 계정에도 이메일마다 늘 같은
  "그럴듯한 질문"(준비된 질문 중 하나)을 보여주고, 재설정 실패는 이유와 상관없이 같은 400이며 bcrypt 비교도 한 번 한다.
  직접 만든 질문은 흉내 낼 수 없어 계정이 있다는 것이 드러나지만, 회원가입이 이미 중복 이메일을 409로 알려 주므로
  (README 설계 결정 1번) 새로 드러나는 것은 없다.
- 시도 기록(password_reset_attempts)에는 이메일 원문 대신 재가입 차단과 같은 HMAC 해시만 남긴다.
  질문 받기는 이메일 칸을 비워(email_hash="") IP 횟수에만 들어가게 한다.
"""

import math
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import (
    InvalidSecurityAnswerError,
    PasswordResetLockedError,
    PasswordResetRateLimitError,
    UserNotFoundError,
)
from app.core.security import hash_password
from app.models import (
    AdminActionType,
    AdminTargetType,
    PasswordResetAttempt,
    PasswordResetMethod,
    PasswordResetNotice,
    User,
    UserRole,
)
from app.schemas.security_question import PRESET_QUESTIONS, PasswordResetNoticeResponse
from app.schemas.user import PasswordResetRequest
from app.services import admin_log_service, email_ban_service, security_question_service, user_service

LOCK_WINDOW = timedelta(hours=24)
MAX_FAILURES_PER_EMAIL = 5
IP_WINDOW = timedelta(hours=1)
MAX_REQUESTS_PER_IP = 30
# 시도 기록은 횟수를 세는 데만 쓴다. 24시간 잠금을 셀 수 있도록 이틀 동안 두고, 재설정할 때마다 함께 정리한다.
ATTEMPT_RETENTION = timedelta(days=2)
# 질문 받기 기록은 이메일 칸을 비운다. 이메일당 실패 횟수에 들어가지 않고 IP 횟수에만 들어간다.
LOOKUP_EMAIL_HASH = ""
_PRESET_LIST = list(PRESET_QUESTIONS.values())
SERVER_PASSWORD_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
SERVER_PASSWORD_LENGTH = 16


def get_question(db: Session, email: str, ip: str) -> str:
    """재설정 1단계: 그 계정의 질문. 순서: 429 IP 횟수 → 질문(쓸 수 없는 계정이면 그럴듯한 질문)."""
    _check_ip_limit(db, ip)
    db.add(PasswordResetAttempt(email_hash=LOOKUP_EMAIL_HASH, ip=ip, success=False))
    db.commit()

    user = _find_user(db, email)
    row = security_question_service.get_row(db, user.id) if _can_use_question(user) else None
    return security_question_service.question_text(row) if row is not None else _decoy_question(email)


def reset_with_answer(db: Session, data: PasswordResetRequest, ip: str) -> None:
    """재설정 2단계. 순서: 422 형식(스키마) → 429 IP 횟수 → 429 이메일 잠금 → 400 이메일·답 불일치.

    - 비밀번호 해시가 바뀌므로 이 계정의 기존 토큰은 모두 401이 된다. (토큰의 비밀번호 지문)
    - 정지된 계정도 재설정할 수 있다. 정지는 그대로라 로그인은 여전히 403이다.
    - 성공하면 관리 기록을 남기고, 다음 로그인 때 보여줄 안내를 만든다.
    """
    email_hash = email_ban_service.hash_email(data.email)
    _check_ip_limit(db, ip)
    _check_email_lock(db, email_hash)

    attempt = PasswordResetAttempt(email_hash=email_hash, ip=ip, success=False)
    db.add(attempt)
    user = _find_user(db, data.email)
    row = security_question_service.get_row(db, user.id) if _can_use_question(user) else None
    # 질문이 없어도 비교는 한 번 한다. (응답 시간으로 가입 여부를 알 수 없게)
    matched = security_question_service.verify_answer(
        data.answer, row.answer_hash if row is not None else security_question_service.dummy_hash()
    )
    if row is None or not matched:
        # 실패한 시도도 횟수에 들어가야 하므로 기록을 저장한 뒤 실패를 알린다.
        db.commit()
        raise InvalidSecurityAnswerError()

    attempt.success = True
    _apply_reset(db, user, data.new_password, PasswordResetMethod.QUESTION)
    db.execute(delete(PasswordResetAttempt).where(PasswordResetAttempt.created_at < _db_now(db) - ATTEMPT_RETENTION))
    db.commit()


def reset_by_server(db: Session, email: str) -> str:
    """서버 명령으로 재설정. 임의의 새 비밀번호를 만들어 돌려준다(화면에 한 번만 보여주고 어디에도 기록하지 않는다).
    서버에 접속할 수 있는 사람만 쓸 수 있으므로 관리자 계정에도 쓸 수 있다. 관리 기록과 다음 로그인 안내를 남긴다.
    """
    user = _find_user(db, email.strip().lower())
    if user is None:
        raise UserNotFoundError()
    # 옮겨 적기 쉽게 헷갈리는 글자(0·O·1·l·I)를 뺀 16자(약 93비트). 로그인한 뒤 바로 바꾸도록 안내한다.
    password = "".join(secrets.choice(SERVER_PASSWORD_ALPHABET) for _ in range(SERVER_PASSWORD_LENGTH))
    _apply_reset(db, user, password, PasswordResetMethod.SERVER)
    db.commit()
    return password


def pending_notice(db: Session, user: User) -> PasswordResetNoticeResponse | None:
    """아직 확인하지 않은 가장 최근 재설정 안내."""
    notice = db.scalar(
        select(PasswordResetNotice)
        .where(PasswordResetNotice.user_id == user.id, PasswordResetNotice.seen_at.is_(None))
        .order_by(PasswordResetNotice.reset_at.desc(), PasswordResetNotice.id.desc())
        .limit(1)
    )
    if notice is None:
        return None
    return PasswordResetNoticeResponse(reset_at=notice.reset_at, method=notice.method.value)


def dismiss_notices(db: Session, user: User) -> None:
    """안내를 확인했다. 질문 변경 7일 제한의 기준이라 행은 지우지 않고 확인 시각만 적는다."""
    db.execute(
        update(PasswordResetNotice)
        .where(PasswordResetNotice.user_id == user.id, PasswordResetNotice.seen_at.is_(None))
        .values(seen_at=func.now())
    )
    db.commit()


# ---------- 내부 함수 ----------


def _find_user(db: Session, email: str) -> User | None:
    # 탈퇴한 계정은 이메일이 지워져 있어 여기서 찾을 수 없다. (없는 이메일과 같은 응답)
    return db.scalar(select(User).where(User.email == email))


def _can_use_question(user: User | None) -> bool:
    return user is not None and not user_service.is_withdrawn(user) and user.role != UserRole.ADMIN


def _decoy_question(email: str) -> str:
    """쓸 수 없는 계정에 보여줄 질문. 이메일의 HMAC으로 골라, 같은 이메일에는 늘 같은 질문이 나온다.
    키(EMAIL_HASH_KEY)를 모르면 어떤 이메일에 어떤 질문이 나올지 계산할 수 없다.
    """
    index = int(email_ban_service.hash_email(email), 16) % len(_PRESET_LIST)
    return _PRESET_LIST[index]


def _apply_reset(db: Session, user: User, new_password: str, method: PasswordResetMethod) -> None:
    """비밀번호를 바꾸고 안내·관리 기록을 남긴다(커밋은 호출한 쪽)."""
    user.password_hash = hash_password(new_password)
    db.add(PasswordResetNotice(user_id=user.id, method=method))
    action = (
        AdminActionType.RESET_PASSWORD_BY_QUESTION
        if method == PasswordResetMethod.QUESTION
        else AdminActionType.RESET_PASSWORD_BY_SERVER
    )
    # 관리자가 한 조치가 아니므로 관리자 칸은 비운다. 화면은 조치 종류로 "본인 확인 질문"·"서버 명령"이라고 보여준다.
    admin_log_service.record(db, None, action, AdminTargetType.USER, user.id, target_user_id=user.id)


def _db_now(db: Session) -> datetime:
    # 저장된 created_at과 같은 기준으로 비교하도록 DB 시간을 쓴다. (메시지·사진 횟수 제한과 같은 방식)
    return db.scalar(select(func.now()))


def _check_ip_limit(db: Session, ip: str) -> None:
    since = _db_now(db) - IP_WINDOW
    count, oldest = db.execute(
        select(func.count(), func.min(PasswordResetAttempt.created_at)).where(
            PasswordResetAttempt.ip == ip, PasswordResetAttempt.created_at > since
        )
    ).one()
    if count >= MAX_REQUESTS_PER_IP:
        # 가장 오래된 요청이 창 밖으로 나가는 시각까지 기다리면 한 번 더 할 수 있다.
        wait = (user_service.as_utc(oldest) - user_service.as_utc(since)).total_seconds()
        raise PasswordResetRateLimitError(retry_after=max(1, math.ceil(wait)))


def _check_email_lock(db: Session, email_hash: str) -> None:
    now = _db_now(db)
    # 성공한 뒤의 실패만 센다. 시각은 초 단위로만 저장되는 DB(SQLite)가 있어 같은 초의 앞뒤를 가릴 수 없으므로,
    # 늘 커지는 id로 순서를 가린다.
    last_success_id = db.scalar(
        select(func.max(PasswordResetAttempt.id)).where(
            PasswordResetAttempt.email_hash == email_hash, PasswordResetAttempt.success.is_(True)
        )
    )
    count, latest = db.execute(
        select(func.count(), func.max(PasswordResetAttempt.created_at)).where(
            PasswordResetAttempt.email_hash == email_hash,
            PasswordResetAttempt.success.is_(False),
            PasswordResetAttempt.created_at > now - LOCK_WINDOW,
            PasswordResetAttempt.id > (last_success_id or 0),
        )
    ).one()
    if count >= MAX_FAILURES_PER_EMAIL:
        # 잠긴 동안에는 기록하지 않으므로, 가장 최근 실패가 5번째 실패다. 그때부터 24시간.
        wait = (user_service.as_utc(latest) + LOCK_WINDOW - user_service.as_utc(now)).total_seconds()
        raise PasswordResetLockedError(retry_after=max(1, math.ceil(wait)))
