"""관리자 대시보드: 가입자·글·신고 수. 쿼리는 데이터 양과 상관없이 3번이다. (사용자 + 글 + 미처리 신고)"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Post, PostStatus, Report, ReportStatus, User, UserRole
from app.schemas.admin import (
    AdminDashboardResponse,
    DashboardPeriodCounts,
    DashboardPostCounts,
    DashboardUserCounts,
)
from app.services import user_service

# "최근 7일"은 오늘을 포함한 7일이다.
RECENT_DAYS = 7


def get_dashboard(db: Session) -> AdminDashboardResponse:
    now = user_service.utc_now()
    today = now.astimezone(user_service.KST).date()
    # "오늘"은 한국 시간 자정부터다. DB에는 UTC로 저장되므로 경계 시각을 UTC로 바꿔 범위로 센다.
    # 날짜 함수로 묶지 않는 이유: SQLite와 PostgreSQL의 날짜·시간대 함수가 달라 같은 SQL로 셀 수 없다.
    today_start = db_time(db, kst_midnight(today))
    recent_start = db_time(db, kst_midnight(today - timedelta(days=RECENT_DAYS - 1)))
    now_db = db_time(db, now)

    active = User.password_hash != user_service.WITHDRAWN_PASSWORD_HASH
    users = db.execute(
        select(
            _count_if(active),
            _count_if(active & (User.created_at >= today_start)),
            _count_if(active & (User.created_at >= recent_start)),
            _count_if(active & (User.suspended_until > now_db)),
            _count_if(active & (User.role == UserRole.ADMIN)),
            _count_if(~active),
        )
    ).one()
    posts = db.execute(
        select(
            func.count(),
            _count_if(Post.status == PostStatus.ON_SALE),
            _count_if(Post.status == PostStatus.RESERVED),
            _count_if(Post.status == PostStatus.SOLD),
            _count_if(Post.created_at >= today_start),
            _count_if(Post.created_at >= recent_start),
        ).select_from(Post)
    ).one()
    pending = db.scalar(select(func.count()).select_from(Report).where(Report.status == ReportStatus.PENDING))

    return AdminDashboardResponse(
        today=today,
        users=DashboardUserCounts(total=users[0], suspended=users[3], admins=users[4], withdrawn=users[5]),
        posts=DashboardPostCounts(total=posts[0], on_sale=posts[1], reserved=posts[2], sold=posts[3]),
        signups=DashboardPeriodCounts(today=users[1], last_7_days=users[2]),
        new_posts=DashboardPeriodCounts(today=posts[4], last_7_days=posts[5]),
        pending_reports=pending or 0,
    )


def _count_if(condition):
    # 조건에 맞는 행 수. 한 SELECT 안에서 여러 개수를 함께 세어 쿼리 수를 늘리지 않는다.
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


def kst_midnight(day: date) -> datetime:
    """한국 날짜의 자정을 UTC 시각으로."""
    return datetime(day.year, day.month, day.day, tzinfo=user_service.KST).astimezone(UTC)


def db_time(db: Session, value: datetime) -> datetime:
    """DB의 시각 컬럼과 비교할 값. SQLite는 시간대 없는 UTC 문자열로 저장하므로 시간대를 떼어 같은 형식으로 맞춘다."""
    if db.get_bind().dialect.name == "sqlite":
        return value.astimezone(UTC).replace(tzinfo=None)
    return value
