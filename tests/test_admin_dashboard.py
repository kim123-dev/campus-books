"""관리자 대시보드: 가입자·글 수, 한국 시간 기준 오늘·최근 7일 경계, 미처리 신고 수, 쿼리 수."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import Post, User
from app.services import user_service
from tests.admin_helpers import count_queries, report_post

# 한국 시간 2026-11-11 12:00. 오늘은 UTC 11-10 15:00부터, 최근 7일은 UTC 11-04 15:00부터다.
NOW = datetime(2026, 11, 11, 3, 0, tzinfo=UTC)


def utc(*args) -> datetime:
    # SQLite는 시각을 시간대 없는 UTC로 저장한다.
    return datetime(*args)


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch) -> None:
    monkeypatch.setattr(user_service, "utc_now", lambda: NOW)


@pytest.fixture
def admin(make_admin_headers, db_session) -> dict:
    headers = make_admin_headers()
    set_user_created(db_session, "admin@campus.ac.kr", utc(2026, 1, 1))
    return headers


def set_user_created(db, email: str, when: datetime) -> User:
    user = db.scalar(select(User).where(User.email == email))
    user.created_at = when
    db.commit()
    return user


def dashboard(client, headers) -> dict:
    response = client.get("/admin/dashboard", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_empty_dashboard(client, admin) -> None:
    body = dashboard(client, admin)

    assert body == {
        "today": "2026-11-11",
        "users": {"total": 1, "suspended": 0, "admins": 1, "withdrawn": 0},
        "posts": {"total": 0, "on_sale": 0, "reserved": 0, "sold": 0},
        "signups": {"today": 0, "last_7_days": 0},
        "new_posts": {"today": 0, "last_7_days": 0},
        "pending_reports": 0,
    }


def test_signups_use_korean_day_boundaries(client, db_session, admin, make_auth_headers) -> None:
    cases = {
        "today@campus.ac.kr": utc(2026, 11, 10, 15, 0, 0),  # 한국 11-11 00:00 → 오늘
        "late@campus.ac.kr": utc(2026, 11, 10, 14, 59, 59),  # 한국 11-10 23:59:59 → 어제(7일 안)
        "six@campus.ac.kr": utc(2026, 11, 4, 15, 0, 0),  # 한국 11-05 00:00 → 7일 안의 첫날
        "seven@campus.ac.kr": utc(2026, 11, 4, 14, 59, 59),  # 한국 11-04 → 7일 밖
    }
    for i, (email, when) in enumerate(cases.items()):
        make_auth_headers(email, f"사용자{i}")
        set_user_created(db_session, email, when)

    body = dashboard(client, admin)

    assert body["users"]["total"] == 5
    assert body["signups"] == {"today": 1, "last_7_days": 3}


def test_post_counts_by_status_and_period(client, db_session, admin, auth_headers, create_post) -> None:
    ids = [create_post(auth_headers)["id"] for _ in range(4)]
    client.patch(f"/posts/{ids[1]}/status", json={"status": "RESERVED"}, headers=auth_headers)
    client.patch(f"/posts/{ids[2]}/status", json={"status": "SOLD"}, headers=auth_headers)
    for post_id, when in zip(ids, [utc(2026, 11, 11, 2), utc(2026, 11, 10, 14), utc(2026, 11, 6), utc(2026, 10, 1)]):
        db_session.get(Post, post_id).created_at = when
    db_session.commit()

    body = dashboard(client, admin)

    assert body["posts"] == {"total": 4, "on_sale": 2, "reserved": 1, "sold": 1}
    assert body["new_posts"] == {"today": 1, "last_7_days": 3}


def test_suspended_withdrawn_and_pending_reports(client, db_session, admin, make_auth_headers, create_post) -> None:
    seller = make_auth_headers("seller@campus.ac.kr", "판매자")
    reporter = make_auth_headers("reporter@campus.ac.kr", "신고자")
    leaver = make_auth_headers("leaver@campus.ac.kr", "탈퇴자")
    report_post(client, create_post(seller)["id"], reporter)
    report_post(client, create_post(seller)["id"], reporter)
    seller_user = db_session.scalar(select(User).where(User.email == "seller@campus.ac.kr"))
    seller_user.suspended_until = utc(2026, 11, 12)  # 아직 정지 중
    reporter_user = db_session.scalar(select(User).where(User.email == "reporter@campus.ac.kr"))
    reporter_user.suspended_until = utc(2026, 11, 10)  # 이미 끝난 정지
    db_session.commit()
    client.post("/users/me/withdraw", json={"password": "password123"}, headers=leaver)

    body = dashboard(client, admin)

    assert body["users"] == {"total": 3, "suspended": 1, "admins": 1, "withdrawn": 1}
    assert body["pending_reports"] == 2


def test_query_count_is_fixed(client, admin, auth_headers, create_post, make_auth_headers) -> None:
    few = count_queries(client, "/admin/dashboard", admin)
    for i in range(3):
        make_auth_headers(f"u{i}@campus.ac.kr", f"사용자{i}")
        create_post(auth_headers)

    # 관리자 확인 1 + 사용자 1 + 글 1 + 미처리 신고 1
    assert count_queries(client, "/admin/dashboard", admin) == few == 4


def test_dashboard_has_no_email(client, admin, auth_headers) -> None:
    assert "@" not in client.get("/admin/dashboard", headers=admin).text
