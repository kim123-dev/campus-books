"""비밀번호 재설정: 본인 확인 질문(로그인하지 않은 상태)과 서버 명령(관리자 비밀번호 분실).

질문 방식의 흐름: 이메일 → 그 계정의 질문 → 답 확인(맞으면 10분짜리 일회용 확인증) → 확인증 + 새 비밀번호.
답이 맞는지 새 비밀번호를 정하기 전에 알 수 있게 단계를 나눴다. 질문이 하나뿐이라 맞혀 보기를 엄격하게 막는다.
- 이메일당: 최근 24시간에 5번 틀리면 마지막으로 틀린 때부터 24시간 잠근다. 잠긴 동안의 시도는 세지 않는다
  (세면 잠금이 끝없이 늘어난다). 답이 맞으면 그 전의 실패는 더 세지 않는다. 틀릴 때마다 남은 횟수를 알려준다.
  없는 이메일도 같은 해시로 똑같이 세므로 남은 횟수로 가입 여부를 알 수 없다.
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
    InvalidResetTokenError,
    InvalidSecurityAnswerError,
    PasswordResetLockedError,
    PasswordResetRateLimitError,
    UserNotFoundError,
)
from app.core.security import (
    RESET_TOKEN_MINUTES,
    create_password_reset_token,
    decode_password_reset_token,
    hash_password,
    password_fingerprint,
)
from app.models import (
    AdminActionType,
    AdminTargetType,
    PasswordResetAttempt,
    PasswordResetMethod,
    PasswordResetNotice,
    User,
    UserRole,
)
from app.schemas.security_question import PRESET_QUESTIONS, PasswordResetNoticeResponse, PasswordResetVerifyResponse
from app.schemas.user import PasswordResetRequest, PasswordResetVerifyRequest
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


def verify_answer(db: Session, data: PasswordResetVerifyRequest, ip: str) -> PasswordResetVerifyResponse:
    """재설정 2단계: 답 확인. 순서: 422 형식(스키마) → 429 IP 횟수 → 429 이메일 잠금 → 400 이메일·답 불일치.

    - 맞으면 10분짜리 일회용 확인증을 준다. 비밀번호는 아직 바꾸지 않는다.
    - 틀리면 "남은 시도 N번"을 붙인 400. 5번째로 틀리면 바로 429(잠금)와 남은 시간을 알려준다.
    - 없는 이메일·질문 없는 계정·탈퇴·관리자도 같은 방식으로 세고, bcrypt 비교도 한 번 해 응답과 시간이 같다.
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
        count, latest, now = _email_failures(db, email_hash)
        remaining = MAX_FAILURES_PER_EMAIL - count
        if remaining <= 0:
            _raise_locked(latest, now)
        raise InvalidSecurityAnswerError(f"이메일 또는 답이 맞지 않습니다. 남은 시도 {remaining}번 (24시간 기준)")

    attempt.success = True
    db.execute(delete(PasswordResetAttempt).where(PasswordResetAttempt.created_at < _db_now(db) - ATTEMPT_RETENTION))
    db.commit()
    return PasswordResetVerifyResponse(
        reset_token=create_password_reset_token(user.id, user.password_hash),
        expires_in=RESET_TOKEN_MINUTES * 60,
    )


def reset_with_token(db: Session, data: PasswordResetRequest) -> None:
    """재설정 3단계: 확인증 + 새 비밀번호. 확인증이 없거나·만료·위조·이미 씀이면 모두 같은 400.

    - 확인증에는 발급 당시 비밀번호 지문이 있다. 비밀번호가 바뀌면 지문이 달라지므로 한 번만 쓸 수 있다.
    - 그사이 탈퇴했거나 관리자가 된 계정에도 쓸 수 없다.
    - 비밀번호 해시가 바뀌므로 이 계정의 기존 토큰은 모두 401이 된다. 정지는 그대로다.
    - 성공하면 관리 기록을 남기고, 다음 로그인 때 보여줄 안내를 만든다.
    """
    token = decode_password_reset_token(data.reset_token)
    user = db.get(User, token.user_id)
    if (
        not _can_use_question(user)
        or token.password_fingerprint != password_fingerprint(user.password_hash)
        or security_question_service.get_row(db, user.id) is None
    ):
        raise InvalidResetTokenError()
    _apply_reset(db, user, data.new_password, PasswordResetMethod.QUESTION)
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


def _email_failures(db: Session, email_hash: str) -> tuple[int, datetime | None, datetime]:
    """최근 24시간 안, 마지막으로 답을 맞힌 뒤의 실패 횟수와 가장 최근 실패 시각."""
    now = _db_now(db)
    # 시각은 초 단위로만 저장되는 DB(SQLite)가 있어 같은 초의 앞뒤를 가릴 수 없으므로, 늘 커지는 id로 순서를 가린다.
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
    return count, latest, now


def _check_email_lock(db: Session, email_hash: str) -> None:
    count, latest, now = _email_failures(db, email_hash)
    if count >= MAX_FAILURES_PER_EMAIL:
        _raise_locked(latest, now)


def _raise_locked(latest: datetime, now: datetime) -> None:
    # 잠긴 동안에는 기록하지 않으므로, 가장 최근 실패가 5번째 실패다. 그때부터 24시간.
    wait = max(1, math.ceil((user_service.as_utc(latest) + LOCK_WINDOW - user_service.as_utc(now)).total_seconds()))
    raise PasswordResetLockedError(
        retry_after=wait,
        message=f"답을 {MAX_FAILURES_PER_EMAIL}번 틀려 이 이메일로는 비밀번호를 재설정할 수 없어요. {_wait_text(wait)} 뒤에 다시 시도해 주세요.",
    )


def _wait_text(seconds: int) -> str:
    minutes = math.ceil(seconds / 60)
    hours, minutes = divmod(minutes, 60)
    if hours and minutes:
        return f"{hours}시간 {minutes}분"
    return f"{hours}시간" if hours else f"{minutes}분"
