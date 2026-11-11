"""관리자 강제 탈퇴·재가입 차단·차단 해제.

- 강제 탈퇴는 본인 탈퇴와 같은 규칙으로 지우고, 기록에는 닉네임·이메일을 남기지 않는다.
- 재가입 차단은 이메일 원문 없이 HMAC 해시만 저장한다.
- 오류 순서: 422 → 404 → 409 → 400
"""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import AdminAction, BannedEmail, Post, User
from app.services import email_ban_service
from tests.admin_helpers import last_log, log_count, report_post, user_id
from tests.conftest import TEST_PASSWORD
from tests.test_post_images import make_image, upload

EMAIL = "bad@campus.ac.kr"


@pytest.fixture
def admin(make_admin_headers) -> dict:
    return make_admin_headers()


@pytest.fixture
def target(client, make_auth_headers) -> tuple[dict, int]:
    headers = make_auth_headers(EMAIL, "문제사용자")
    return headers, user_id(client, headers)


def withdraw(client, headers, uid, reason="사기 반복", **body):
    return client.post(f"/admin/users/{uid}/withdraw", json={"reason": reason, **body}, headers=headers)


def signup(client, email=EMAIL, nickname="새닉네임"):
    return client.post("/auth/signup", json={"email": email, "password": TEST_PASSWORD, "nickname": nickname})


def unban(client, headers, email=EMAIL, reason="소명 받아들임"):
    return client.post("/admin/email-bans/unban", json={"email": email, "reason": reason}, headers=headers)


# ---------- 강제 탈퇴 ----------


def test_force_withdraw_erases_account_like_self_withdraw(
    client, db_session, admin, target, create_post, image_dir: Path
) -> None:
    headers, uid = target
    post_id = create_post(headers)["id"]
    assert upload(client, post_id, headers, make_image()).status_code == 201

    response = withdraw(client, admin, uid)

    assert response.status_code == 200, response.text
    assert response.json() == {"email_banned": True, "deleted_posts": 1}
    # 토큰이 바로 끊기고, 글·사진이 지워지고, 개인정보가 사라진다.
    assert client.get("/users/me", headers=headers).status_code == 401
    assert client.get(f"/posts/{post_id}").status_code == 404
    assert list(image_dir.iterdir()) == []
    db_session.expire_all()
    user = db_session.get(User, uid)
    assert user.email.endswith("@withdrawn.invalid") and user.nickname.startswith("withdrawn-")
    assert db_session.scalars(select(Post)).all() == []


def test_log_has_no_nickname_or_email(client, db_session, admin, target) -> None:
    _, uid = target
    withdraw(client, admin, uid)

    entry = last_log(db_session)
    assert (entry.action, entry.target_type, entry.target_id, entry.target_user_id, entry.reason) == (
        "WITHDRAW_USER", "USER", uid, uid, "사기 반복",
    )
    assert entry.detail == {"email_banned": True, "deleted_posts": 0}
    log_text = client.get("/admin/actions", headers=admin).text
    assert "문제사용자" not in log_text and "bad@" not in log_text


def test_ban_stores_only_hash(client, db_session, admin, target) -> None:
    _, uid = target
    withdraw(client, admin, uid)

    bans = db_session.scalars(select(BannedEmail)).all()
    assert len(bans) == 1
    assert bans[0].email_hash == email_ban_service.hash_email(EMAIL)
    assert len(bans[0].email_hash) == 64 and "bad" not in bans[0].email_hash
    assert (bans[0].reason, bans[0].banned_by_id) == ("사기 반복", user_id(client, admin))


def test_hash_uses_secret_key_not_plain_sha256(monkeypatch) -> None:
    import hashlib

    assert email_ban_service.hash_email(EMAIL) != hashlib.sha256(EMAIL.encode()).hexdigest()
    before = email_ban_service.hash_email(EMAIL)
    monkeypatch.setattr(get_settings(), "EMAIL_HASH_KEY", "another-key-for-test")
    assert email_ban_service.hash_email(EMAIL) != before


def test_banned_email_cannot_sign_up_in_any_case(client, admin, target) -> None:
    _, uid = target
    withdraw(client, admin, uid)

    for email in (EMAIL, "BAD@Campus.ac.kr"):  # 대소문자만 바꿔도 막힌다
        response = signup(client, email)
        assert response.status_code == 400, email
        assert response.json()["detail"] == "이 이메일로는 가입할 수 없습니다."
    assert signup(client, "other@campus.ac.kr").status_code == 201


def test_withdraw_without_ban_allows_signup(client, db_session, admin, target) -> None:
    _, uid = target
    response = withdraw(client, admin, uid, ban_email=False)

    assert response.json()["email_banned"] is False
    assert db_session.scalars(select(BannedEmail)).all() == []
    assert last_log(db_session).detail["email_banned"] is False
    assert signup(client).status_code == 201


def test_duplicate_comes_before_ban(client, db_session, admin, make_auth_headers) -> None:
    # 차단된 이메일이 (차단 전부터) 다른 계정에 쓰이고 있으면 중복(409)이 먼저다.
    make_auth_headers("dup@campus.ac.kr", "중복")
    email_ban_service.ban(db_session, db_session.scalar(select(User).where(User.role == "ADMIN")), "dup@campus.ac.kr", "테스트")
    db_session.commit()

    assert signup(client, "dup@campus.ac.kr", "다른닉").status_code == 409


def test_pending_reports_stay_for_review(client, db_session, admin, target, make_auth_headers, create_post) -> None:
    # 본인 탈퇴와 같이 신고 기록은 남는다. (피신고자만 비워진다)
    headers, uid = target
    report_id = report_post(client, create_post(headers)["id"], make_auth_headers("r@campus.ac.kr", "신고자"))

    withdraw(client, admin, uid)

    reports = client.get("/admin/reports", headers=admin).json()["items"]
    assert [r["id"] for r in reports] == [report_id]
    assert reports[0]["reported_user"] is None


@pytest.mark.parametrize("body", [{}, {"reason": "  "}, {"reason": "x" * 501}, {"reason": "사유", "ban_email": "maybe"}])
def test_withdraw_validation(client, db_session, admin, target, body) -> None:
    _, uid = target
    assert client.post(f"/admin/users/{uid}/withdraw", json=body, headers=admin).status_code == 422
    assert log_count(db_session) == 0


def test_withdraw_error_order(client, db_session, admin, target, make_admin_headers) -> None:
    _, uid = target
    assert withdraw(client, admin, 9999).status_code == 404
    other_admin = make_admin_headers("admin2@campus.ac.kr", "관리자둘")
    for admin_id in (user_id(client, admin), user_id(client, other_admin)):
        response = withdraw(client, admin, admin_id)
        assert response.status_code == 400
        assert response.json()["detail"] == "관리자는 강제 탈퇴할 수 없습니다."
    assert withdraw(client, admin, uid).status_code == 200

    again = withdraw(client, admin, uid)

    assert again.status_code == 409
    assert list(db_session.scalars(select(AdminAction.action))) == ["WITHDRAW_USER"]


# ---------- 차단 목록·해제 ----------


def test_ban_list_shows_time_and_reason_only(client, admin, target) -> None:
    _, uid = target
    withdraw(client, admin, uid)

    body = client.get("/admin/email-bans", headers=admin).json()

    assert body["total"] == 1
    assert set(body["items"][0]) == {"id", "created_at", "reason"}
    assert body["items"][0]["reason"] == "사기 반복"


def test_unban_by_email_allows_signup_and_logs(client, db_session, admin, target) -> None:
    _, uid = target
    withdraw(client, admin, uid)
    ban_id = db_session.scalar(select(BannedEmail.id))

    response = unban(client, admin, "BAD@campus.ac.kr")

    assert response.status_code == 204, response.text
    assert signup(client).status_code == 201
    entry = last_log(db_session)
    assert (entry.action, entry.target_type, entry.target_id, entry.target_user_id, entry.reason) == (
        "UNBAN_EMAIL", "EMAIL_BAN", ban_id, None, "소명 받아들임",
    )
    assert "banned_at" in entry.detail
    assert "bad" not in str(entry.detail)


def test_unban_errors(client, db_session, admin, target) -> None:
    _, uid = target
    assert client.post("/admin/email-bans/unban", json={"email": EMAIL}, headers=admin).status_code == 422
    assert client.post("/admin/email-bans/unban", json={"email": "not-email", "reason": "사유"}, headers=admin).status_code == 422
    response = unban(client, admin)  # 차단된 적 없음

    assert response.status_code == 404
    assert response.json()["detail"] == "재가입 차단 목록에 없는 이메일입니다."
    withdraw(client, admin, uid)
    assert unban(client, admin).status_code == 204
    assert unban(client, admin).status_code == 404
    assert list(db_session.scalars(select(AdminAction.action))) == ["WITHDRAW_USER", "UNBAN_EMAIL"]
