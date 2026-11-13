"""내 계정 관리: 닉네임 변경, 비밀번호 변경, 회원 탈퇴."""

import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AdminCannotWithdrawError,
    DuplicateNicknameError,
    NicknameChangeTooSoonError,
    SameNicknameError,
    WrongPasswordError,
)
from app.core.security import create_access_token, hash_password, verify_password
from app.models import NicknameChange, Post, Report, User, UserBlock, UserRole, Wishlist
from app.schemas.user import NicknameUpdate, PasswordChange, WithdrawRequest
from app.services import alert_service, image_storage, post_service, user_service

# 닉네임을 자주 바꾸면 거래 상대가 같은 사람인지 알아보기 어렵고, 신고를 피해 이름을 바꿀 수도 있다.
NICKNAME_CHANGE_INTERVAL = timedelta(days=30)


def nickname_changeable_at(db: Session, user: User, now: datetime | None = None) -> datetime | None:
    """닉네임을 다시 바꿀 수 있는 시각(UTC). 지금 바꿀 수 있으면 None. 가입 때 정한 닉네임은 바로 바꿀 수 있다."""
    last = db.scalar(
        select(NicknameChange.created_at)
        .where(NicknameChange.user_id == user.id)
        .order_by(NicknameChange.created_at.desc(), NicknameChange.id.desc())
        .limit(1)
    )
    if last is None:
        return None
    available = user_service.as_utc(last) + NICKNAME_CHANGE_INTERVAL
    return available if available > (now or user_service.utc_now()) else None


def change_nickname(db: Session, user: User, data: NicknameUpdate, now: datetime | None = None) -> User:
    """닉네임 변경. 순서: 409 다른 사람이 쓰는 닉네임 → 400 지금과 같음 → 400 30일 안에 이미 바꿈.
    401(로그인)·403(정지)·422(형식)는 라우터 의존성과 스키마가 먼저 걸러낸다.
    """
    now = now or user_service.utc_now()
    taken = db.scalar(select(User.id).where(User.nickname == data.nickname, User.id != user.id))
    if taken is not None:
        raise DuplicateNicknameError()
    if data.nickname == user.nickname:
        raise SameNicknameError()
    available = nickname_changeable_at(db, user, now)
    if available is not None:
        local = available.astimezone(user_service.KST)
        raise NicknameChangeTooSoonError(
            f"닉네임은 30일에 한 번만 바꿀 수 있습니다. {local.month}월 {local.day}일 {local:%H:%M}부터 바꿀 수 있어요."
        )

    # DB에는 시간대 없이 UTC로 저장한다. (정지 종료 시각과 같은 방식)
    db.add(NicknameChange(user_id=user.id, old_nickname=user.nickname, new_nickname=data.nickname, created_at=now.replace(tzinfo=None)))
    user.nickname = data.nickname
    try:
        db.commit()
    except IntegrityError:
        # 동시에 같은 닉네임으로 바꾸면 위 확인을 둘 다 통과할 수 있다. DB unique 제약이 마지막으로 막는다.
        db.rollback()
        raise DuplicateNicknameError() from None
    db.refresh(user)
    return user


def change_password(db: Session, user: User, data: PasswordChange) -> str:
    """비밀번호 변경. 현재 비밀번호가 틀리면 WrongPasswordError(400). 새 액세스 토큰을 돌려준다.

    토큰에는 비밀번호 지문이 들어 있어(security.password_fingerprint) 해시가 바뀌는 순간
    이전에 발급된 토큰은 모든 기기에서 401이 된다. 토큰 저장소나 DB 컬럼 없이 옛 토큰을 끊는
    가장 단순한 방법이고, 비밀번호를 바꾸는 흔한 이유(유출 의심)에도 맞는 안전한 쪽이다.
    지금 쓰는 기기는 로그아웃되지 않도록 새 토큰을 바로 발급해 준다.
    """
    _check_password(user, data.current_password)
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return create_access_token(user.id, user.password_hash)


def withdraw(db: Session, user: User, data: WithdrawRequest) -> None:
    """회원 탈퇴. 순서: 400 관리자 → 400 비밀번호 틀림.

    - 지운다: 내 글(사진 파일 포함), 내 찜, 내가 한·받은 차단, 찾는 교재 조건과 알림, 닉네임 변경 기록
    - 남긴다: 쪽지 대화방(상대 화면에는 "탈퇴한 사용자"), 신고 기록(내 id만 비운다)

    사용자 행은 지우지 않고 개인정보를 지운 "탈퇴 표시"로 남긴다. 대화방·쪽지가 사용자 id를
    NOT NULL 외래 키로 가리키고 있어, 행을 지우면 FK를 실제로 검사하는 운영 DB(PostgreSQL)에서
    삭제가 실패한다. 마이그레이션 도구 없이(create_all) 기존 테이블에도 그대로 동작하는 방법이다.
    SQLite는 FK 동작(CASCADE, SET NULL)을 실행하지 않으므로 딸린 행은 모두 여기서 직접 정리한다.
    """
    if user.role == UserRole.ADMIN:
        raise AdminCannotWithdrawError()
    _check_password(user, data.password)

    image_names = erase_account(db, user)
    db.commit()
    # 파일은 DB 커밋이 성공한 뒤에 지운다. (글 삭제와 같은 순서)
    image_storage.remove_files(image_names)


def erase_account(db: Session, user: User) -> list[str]:
    """탈퇴 처리의 본체(커밋 전). 본인 탈퇴와 관리자의 강제 탈퇴가 같은 규칙으로 지우도록 한 곳에 모았다.
    커밋 뒤에 지울 사진 파일 이름을 돌려준다.
    """
    # 글 삭제 규칙(대화방 연결 끊기, 다른 사람의 찜 삭제, 사진 행 삭제)은 글 삭제 기능과 같게 맞춘다.
    image_names: list[str] = []
    for post in db.scalars(select(Post).where(Post.seller_id == user.id)).all():
        image_names += post_service.delete_post_rows(db, post)
    db.execute(delete(Wishlist).where(Wishlist.user_id == user.id))
    # 예전 닉네임도 개인정보라 함께 지운다.
    db.execute(delete(NicknameChange).where(NicknameChange.user_id == user.id))
    alert_service.delete_for_user(db, user.id)
    db.execute(
        delete(UserBlock).where(or_(UserBlock.blocker_id == user.id, UserBlock.blocked_id == user.id))
    )
    # 신고는 관리자 확인을 위해 남기고 사람만 비운다. (관리 화면은 null을 "탈퇴한 사용자"로 보여준다)
    db.execute(update(Report).where(Report.reporter_id == user.id).values(reporter_id=None))
    db.execute(update(Report).where(Report.reported_user_id == user.id).values(reported_user_id=None))

    # 이메일·닉네임은 추측할 수 없는 값으로 바꿔 개인정보를 지우고, 같은 이메일·닉네임으로 다시 가입할 수 있게 한다.
    # (강제 탈퇴에서 재가입을 막을 때는 이메일 해시를 차단 목록에 따로 남긴다. email_ban_service)
    # 비밀번호 해시가 바뀌므로 이 사용자의 기존 토큰도 모두 401이 된다.
    token = secrets.token_hex(8)
    user.email = f"withdrawn-{token}@withdrawn.invalid"
    user.nickname = f"withdrawn-{token}"
    user.password_hash = user_service.WITHDRAWN_PASSWORD_HASH
    user.suspended_until = None
    return image_names


def _check_password(user: User, password: str) -> None:
    if not verify_password(password, user.password_hash):
        raise WrongPasswordError()
