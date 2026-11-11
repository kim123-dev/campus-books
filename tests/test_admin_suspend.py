"""관리자 직접 정지·정지 해제: 사유 필수, 오류 순서(422→404→409→400), 기간 규칙, 관리 기록, 동시 처리."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AdminAction, User
from app.services import user_service
from tests.admin_helpers import last_log, log_count, user_id


@pytest.fixture
def admin(make_admin_headers) -> dict:
    return make_admin_headers()


@pytest.fixture
def target(client, make_auth_headers) -> tuple[dict, int]:
    headers = make_auth_headers("target@campus.ac.kr", "대상자")
    return headers, user_id(client, headers)


def suspend(client, headers, uid, days=3, reason="광고 반복"):
    return client.post(f"/admin/users/{uid}/suspend", json={"days": days, "reason": reason}, headers=headers)


def unsuspend(client, headers, uid, reason="오해였음"):
    return client.post(f"/admin/users/{uid}/unsuspend", json={"reason": reason}, headers=headers)


def set_suspension(db, uid: int, days: float | None) -> None:
    user = db.get(User, uid)
    user.suspended_until = None if days is None else (user_service.utc_now() + timedelta(days=days)).replace(tzinfo=None)
    db.commit()


# ---------- 정지 ----------


def test_suspend_blocks_user_and_logs(client, db_session, admin, target, create_post) -> None:
    headers, uid = target

    response = suspend(client, admin, uid, days=7)

    assert response.status_code == 200, response.text
    end = user_service.as_utc(db_session.get(User, uid).suspended_until)
    assert timedelta(days=6, hours=23) < end - user_service.utc_now() <= timedelta(days=7)
    # 정지된 사용자는 글을 쓸 수 없다. (기존 정지 규칙)
    assert client.post("/posts", json={"title": "글", "book_title": "책", "condition": "GOOD", "price": 1}, headers=headers).status_code == 403
    entry = last_log(db_session)
    assert (entry.action, entry.target_type, entry.target_id, entry.target_user_id, entry.reason) == (
        "SUSPEND", "USER", uid, uid, "광고 반복",
    )
    assert entry.detail["days"] == 7
    assert "previous_until" not in entry.detail


def test_suspend_never_shortens_longer_suspension(client, db_session, admin, target) -> None:
    _, uid = target
    set_suspension(db_session, uid, 30)
    before = db_session.get(User, uid).suspended_until

    response = suspend(client, admin, uid, days=1)

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(User, uid).suspended_until == before
    assert user_service.as_utc(before) == user_service.as_utc(datetime.fromisoformat(response.json()["suspended_until"]))
    assert "previous_until" in last_log(db_session).detail


def test_suspend_extends_shorter_suspension(client, db_session, admin, target) -> None:
    _, uid = target
    set_suspension(db_session, uid, 1)

    suspend(client, admin, uid, days=10)

    db_session.expire_all()
    left = user_service.as_utc(db_session.get(User, uid).suspended_until) - user_service.utc_now()
    assert left > timedelta(days=9)


@pytest.mark.parametrize(
    "body",
    [
        {"days": 3},  # 사유 없음
        {"days": 3, "reason": "   "},  # 공백만
        {"days": 3, "reason": "x" * 501},
        {"days": 0, "reason": "사유"},
        {"days": 366, "reason": "사유"},
        {"reason": "사유"},  # 일수 없음
        {"days": 3, "reason": "사유", "role": "ADMIN"},  # 모르는 필드
    ],
)
def test_suspend_validation(client, db_session, admin, target, body) -> None:
    _, uid = target
    response = client.post(f"/admin/users/{uid}/suspend", json=body, headers=admin)

    assert response.status_code == 422
    assert log_count(db_session) == 0


def test_validation_comes_before_not_found(client, admin) -> None:
    assert client.post("/admin/users/9999/suspend", json={"days": 3}, headers=admin).status_code == 422
    assert suspend(client, admin, 9999).status_code == 404


def test_cannot_suspend_withdrawn_user(client, db_session, admin, target) -> None:
    headers, uid = target
    client.post("/users/me/withdraw", json={"password": "password123"}, headers=headers)

    response = suspend(client, admin, uid)

    assert response.status_code == 409
    assert response.json()["detail"] == "이미 탈퇴한 사용자입니다."
    assert log_count(db_session) == 0


def test_cannot_suspend_admin_or_self(client, db_session, admin, make_admin_headers) -> None:
    other_admin = make_admin_headers("admin2@campus.ac.kr", "관리자둘")

    for uid in (user_id(client, admin), user_id(client, other_admin)):
        response = suspend(client, admin, uid)
        assert response.status_code == 400
        assert response.json()["detail"] == "관리자는 정지할 수 없습니다."
    assert log_count(db_session) == 0


# ---------- 정지 해제 ----------


def test_unsuspend_restores_user_and_logs(client, db_session, admin, target, post_payload) -> None:
    headers, uid = target
    suspend(client, admin, uid)

    response = unsuspend(client, admin, uid)

    assert response.status_code == 200, response.text
    assert response.json() == {"suspended_until": None}
    db_session.expire_all()
    assert db_session.get(User, uid).suspended_until is None
    assert client.post("/posts", json=post_payload, headers=headers).status_code == 201
    entry = last_log(db_session)
    assert (entry.action, entry.target_user_id, entry.reason) == ("UNSUSPEND", uid, "오해였음")
    assert "previous_until" in entry.detail


def test_unsuspend_requires_active_suspension(client, db_session, admin, target) -> None:
    _, uid = target
    assert unsuspend(client, admin, uid).status_code == 409  # 정지된 적 없음
    set_suspension(db_session, uid, -1)  # 이미 끝난 정지
    response = unsuspend(client, admin, uid)

    assert response.status_code == 409
    assert response.json()["detail"] == "정지 중인 사용자가 아닙니다."
    assert log_count(db_session) == 0


def test_unsuspend_errors(client, db_session, admin, target) -> None:
    headers, uid = target
    assert client.post(f"/admin/users/{uid}/unsuspend", json={}, headers=admin).status_code == 422
    assert unsuspend(client, admin, 9999).status_code == 404
    client.post("/users/me/withdraw", json={"password": "password123"}, headers=headers)
    assert unsuspend(client, admin, uid).status_code == 409


def test_second_unsuspend_fails_and_logs_once(client, db_session, admin, target) -> None:
    # 두 관리자가 연달아 풀면 두 번째는 409이고 기록은 한 줄만 남는다.
    _, uid = target
    suspend(client, admin, uid)
    assert unsuspend(client, admin, uid).status_code == 200
    assert unsuspend(client, admin, uid).status_code == 409
    db_session.expire_all()
    actions = list(db_session.scalars(select(AdminAction.action)))
    assert actions.count("UNSUSPEND") == 1


def test_detail_shows_history_newest_first(client, admin, target) -> None:
    _, uid = target
    suspend(client, admin, uid, reason="첫 정지")
    unsuspend(client, admin, uid, reason="풀어줌")

    history = client.get(f"/admin/users/{uid}", headers=admin).json()["suspensions"]

    assert [(h["action"], h["reason"]) for h in history] == [("UNSUSPEND", "풀어줌"), ("SUSPEND", "첫 정지")]
