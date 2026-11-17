"""앱(안드로이드)의 로그인 유지: 액세스 토큰(60분) + 갱신 토큰(30일, 쓸 때마다 교체).

- 웹은 지금처럼 /auth/login의 액세스 토큰만 쓴다. 이 모듈은 앱 전용 API(/auth/token·refresh·logout)만 쓴다.
- 갱신 토큰은 추측할 수 없는 임의 문자열이고, DB에는 SHA-256 해시만 둔다.
- 교체: 갱신하면 쓴 토큰은 다시 쓸 수 없게 표시하고 새 토큰을 준다.
- 재사용 감지: 이미 교체·폐기된 토큰이 다시 오면 누군가 훔쳐 쓴 것으로 보고 그 사용자의 갱신 토큰을 모두 폐기한다.
- 비밀번호 변경·재설정(본인 확인 질문, 서버 명령)·탈퇴(본인, 관리자)는 revoke_all로 모두 폐기한다.
  빠뜨린 경로가 생겨도 발급 당시 비밀번호 지문이 지금과 다르면 갱신을 거절한다.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import InvalidRefreshTokenError, SuspendedRefreshError
from app.core.security import create_access_token, password_fingerprint
from app.models import RefreshToken, User
from app.schemas.user import AppLoginForm, TokenPairResponse
from app.services import admin_dashboard_service, auth_service, user_service

# 갱신 토큰 유효 기간. 이 기간 안에 한 번이라도 앱을 열면(갱신하면) 다시 30일이 된다.
REFRESH_TOKEN_DAYS = 30


def login(db: Session, data: AppLoginForm, now: datetime | None = None) -> TokenPairResponse:
    """앱 로그인. 웹 로그인과 같은 검사(401 불일치 → 403 정지)를 거친 뒤 토큰 두 개를 준다."""
    user = auth_service.authenticate(db, data)
    response = _issue(db, user, data.device_name, now or user_service.utc_now())
    db.commit()
    return response


def refresh(db: Session, raw_token: str, now: datetime | None = None) -> TokenPairResponse:
    """갱신 토큰으로 새 토큰 두 개를 받는다. 실패는 모두 401(새 토큰 없음).
    순서: 없는 토큰 → 재사용(모두 폐기) → 만료 → 탈퇴·비밀번호 바뀜(모두 폐기) → 정지 중 → 교체.
    """
    now = now or user_service.utc_now()
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if row is None:
        raise InvalidRefreshTokenError()
    if row.rotated_at is not None or row.revoked_at is not None:
        _revoke_all_and_fail(db, row.user_id, now)
    if user_service.as_utc(row.expires_at) <= now:
        raise InvalidRefreshTokenError()

    user = user_service.get_user_by_id(db, row.user_id)  # 탈퇴한 계정은 None
    if user is None or row.password_fingerprint != password_fingerprint(user.password_hash):
        _revoke_all_and_fail(db, row.user_id, now)
    end = user_service.active_suspension_end(user, now)
    if end is not None:
        # 정지가 끝나면 다시 쓸 수 있도록 폐기하지는 않는다. (로그인도 정지 중에만 막는다)
        raise SuspendedRefreshError(user_service.suspension_message(end, now))

    # 같은 토큰으로 두 요청이 동시에 와도 하나만 교체에 성공하도록 조건을 UPDATE에 함께 건다.
    # 진 쪽은 "이미 교체된 토큰"을 쓴 것이므로 재사용으로 처리한다.
    claimed = db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == row.id, RefreshToken.rotated_at.is_(None), RefreshToken.revoked_at.is_(None))
        .values(rotated_at=now)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        _revoke_all_and_fail(db, row.user_id, now)
    response = _issue(db, user, row.device_name, now, replaces=row)
    db.commit()
    return response


def logout(db: Session, raw_token: str, now: datetime | None = None) -> None:
    """이 기기의 갱신 토큰만 폐기한다. 없거나 이미 폐기된 토큰이어도 조용히 성공(여러 번 눌러도 안전)."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw_token), RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now or user_service.utc_now())
    )
    db.commit()


def revoke_all(db: Session, user_id: int, now: datetime | None = None) -> None:
    """그 사용자의 갱신 토큰을 모두 폐기한다(커밋은 호출한 쪽). 비밀번호 변경·재설정·탈퇴에서 부른다."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now or user_service.utc_now())
    )


def hash_token(raw_token: str) -> str:
    # 토큰 자체가 추측할 수 없는 긴 임의 값이라 느린 해시(bcrypt)가 필요 없다. 빠른 조회를 위해 SHA-256.
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _revoke_all_and_fail(db: Session, user_id: int, now: datetime) -> None:
    revoke_all(db, user_id, now)
    db.commit()
    raise InvalidRefreshTokenError()


def _issue(
    db: Session, user: User, device_name: str | None, now: datetime, replaces: RefreshToken | None = None
) -> TokenPairResponse:
    raw = secrets.token_urlsafe(32)
    expires_at = now + timedelta(days=REFRESH_TOKEN_DAYS)
    row = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw),
        password_fingerprint=password_fingerprint(user.password_hash),
        device_name=device_name,
        expires_at=admin_dashboard_service.db_time(db, expires_at),
    )
    db.add(row)
    db.flush()
    if replaces is not None:
        replaces.replaced_by_id = row.id
    return TokenPairResponse(
        access_token=create_access_token(user.id, user.password_hash),
        expires_in=get_settings().ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_token=raw,
        refresh_expires_at=expires_at,
    )
