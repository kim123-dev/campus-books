from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import UserNotFoundError
from app.models import User, UserRole

# 정지 안내 메시지는 한국 시간으로 보여준다. 한국은 서머타임이 없어 고정 +9시간으로 충분하고,
# Windows처럼 시간대 데이터가 없는 환경에서도 추가 패키지(tzdata) 없이 동작한다.
KST = timezone(timedelta(hours=9), "KST")


# 탈퇴한 계정의 password_hash 자리에 넣는 값. bcrypt 해시는 "$2"로 시작하므로 이 값과 겹칠 수 없고,
# 어떤 비밀번호로도 로그인되지 않는다. (security.verify_password가 False를 돌려준다)
WITHDRAWN_PASSWORD_HASH = "!withdrawn"
# 탈퇴한 사용자를 다른 사람 화면에 보여줄 때 쓰는 이름
WITHDRAWN_NICKNAME = "탈퇴한 사용자"


def is_withdrawn(user: User) -> bool:
    return user.password_hash == WITHDRAWN_PASSWORD_HASH


def display_nickname(user: User) -> str:
    """다른 사용자에게 보여줄 닉네임. 탈퇴했으면 "탈퇴한 사용자"."""
    return WITHDRAWN_NICKNAME if is_withdrawn(user) else user.nickname


# 없거나 탈퇴했으면 None을 돌려주고, 없을 때 어떤 에러로 볼지는 호출하는 쪽이 정한다.
# (인증에서는 401, 다른 기능에서는 404처럼 상황마다 의미가 다르기 때문)
def get_user_by_id(db: Session, user_id: int) -> User | None:
    user = db.get(User, user_id)
    return None if user is None or is_withdrawn(user) else user


# ---------- 이용 정지 ----------


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """DB에서 읽은 시각을 UTC 기준 시각으로 맞춘다. SQLite는 시간대 없이 돌려주지만 값은 UTC다."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def active_suspension_end(user: User, now: datetime | None = None) -> datetime | None:
    """정지 중이면 정지 종료 시각(UTC), 아니면 None.
    종료 시각이 지났으면 따로 풀어 주는 작업 없이 정지가 끝난 것으로 본다. (자동 해제)
    """
    if user.suspended_until is None:
        return None
    end = as_utc(user.suspended_until)
    return end if end > (now or utc_now()) else None


def suspension_message(end: datetime, now: datetime | None = None) -> str:
    """'11월 16일 14:00까지 이용이 정지되었습니다.' 해가 바뀌면 연도도 붙인다.
    날짜만 쓰면 그날 아침에 이미 풀렸다고 오해할 수 있어 시각까지 보여준다.
    """
    local = end.astimezone(KST)
    this_year = (now or utc_now()).astimezone(KST).year
    year = f"{local.year}년 " if local.year != this_year else ""
    return f"{year}{local.month}월 {local.day}일 {local:%H:%M}까지 이용이 정지되었습니다."


def suspend(user: User, days: int, now: datetime | None = None) -> datetime:
    """days일 동안 정지한다(커밋은 호출한 쪽에서). 실제로 정한 종료 시각(UTC)을 돌려준다.
    이미 더 늦게 끝나는 정지가 있으면 그대로 둔다. 새 신고 처리로 정지 기간이 줄어들지 않게 하기 위해서다.
    """
    new_end = (now or utc_now()) + timedelta(days=days)
    current_end = active_suspension_end(user, now)
    end = max(new_end, current_end) if current_end is not None else new_end
    # DB에는 시간대 없이 UTC로 저장한다. (SQLite·MySQL DATETIME 공통, 화면은 UTC로 읽는다)
    user.suspended_until = end.replace(tzinfo=None)
    return end


# ---------- 관리자 지정 (CLI 전용) ----------


def make_admin(db: Session, email: str) -> bool:
    """이메일로 찾은 사용자를 관리자로 지정한다. 새로 지정했으면 True, 이미 관리자면 False.
    가입·수정 API로는 role을 바꿀 수 없고, 서버에 접속할 수 있는 사람만 이 함수를 CLI로 실행한다.
    """
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise UserNotFoundError()
    if user.role == UserRole.ADMIN:
        return False
    user.role = UserRole.ADMIN
    db.commit()
    return True
