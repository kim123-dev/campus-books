"""강제 탈퇴한 이메일의 재가입 차단.

이메일 원문은 저장하지 않는다. 소문자로 맞춘 이메일을 EMAIL_HASH_KEY로 HMAC-SHA256 한 값만 저장하고,
가입할 때 같은 방법으로 만든 해시가 목록에 있는지 본다. 키 없이 해시만으로는 이메일을 알아낼 수 없고,
흔한 이메일을 대입해 맞춰 보는 것도 키가 있어야 가능하다. (일반 SHA-256이면 키 없이 대입할 수 있다)
"""

import hashlib
import hmac

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import EmailBanNotFoundError
from app.models import AdminActionType, AdminTargetType, BannedEmail, User
from app.schemas.admin import AdminEmailBanItem, AdminEmailUnbanRequest
from app.services import admin_log_service, user_service


def hash_email(email: str) -> str:
    """가입·로그인과 같은 규칙(앞뒤 공백 제거, 소문자)으로 맞춘 뒤 해시한다."""
    normalized = email.strip().lower().encode()
    return hmac.new(get_settings().email_hash_key, normalized, hashlib.sha256).hexdigest()


def is_banned(db: Session, email: str) -> bool:
    return db.scalar(select(BannedEmail.id).where(BannedEmail.email_hash == hash_email(email))) is not None


def ban(db: Session, admin: User, email: str, reason: str) -> None:
    """차단 목록에 넣는다(커밋은 호출한 쪽). 이미 있으면 그대로 둔다."""
    email_hash = hash_email(email)
    if db.scalar(select(BannedEmail.id).where(BannedEmail.email_hash == email_hash)) is None:
        db.add(BannedEmail(email_hash=email_hash, reason=reason, banned_by_id=admin.id))


def unban(db: Session, admin: User, data: AdminEmailUnbanRequest) -> None:
    """관리자가 입력한 이메일의 차단을 푼다. 목록에 없으면 404. 기록에는 이메일을 남기지 않는다."""
    banned = db.scalar(select(BannedEmail).where(BannedEmail.email_hash == hash_email(data.email)))
    if banned is None:
        raise EmailBanNotFoundError()
    detail = {"banned_at": user_service.as_utc(banned.created_at).isoformat()}
    # 두 관리자가 동시에 풀어도 한쪽만 성공하고 기록도 한 줄만 남도록, 지운 행 수를 확인한다.
    result = db.execute(delete(BannedEmail).where(BannedEmail.id == banned.id).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise EmailBanNotFoundError()
    admin_log_service.record(
        db, admin, AdminActionType.UNBAN_EMAIL, AdminTargetType.EMAIL_BAN, banned.id, reason=data.reason, detail=detail
    )
    db.commit()


def list_bans(db: Session, page: int, size: int) -> tuple[list[AdminEmailBanItem], int]:
    """차단 목록(최신순). 이메일을 알 수 없으므로 번호·차단 시각·사유만 보여준다."""
    total = db.scalar(select(func.count()).select_from(BannedEmail)) or 0
    rows = db.scalars(
        select(BannedEmail)
        .order_by(BannedEmail.created_at.desc(), BannedEmail.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return [AdminEmailBanItem(id=b.id, created_at=b.created_at, reason=b.reason) for b in rows], total
