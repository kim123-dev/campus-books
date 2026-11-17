"""앱(안드로이드) 로그인 유지: /auth/token(로그인), /auth/refresh(교체·재사용 감지), /auth/logout,
비밀번호 변경·재설정(질문, 서버 명령)·탈퇴(본인, 관리자) 뒤 갱신 거절, /auth/security-questions."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import cli
from app.core.security import hash_password
from app.models import RefreshToken, User
from app.schemas.security_question import PRESET_QUESTIONS
from app.services import token_service, user_service
from tests.conftest import SECURITY_QUESTION, TEST_PASSWORD, TestingSessionLocal

EMAIL = "student@campus.ac.kr"
EXPIRED = {"detail": "로그인이 만료되었습니다. 다시 로그인해 주세요."}


@pytest.fixture
def student(make_auth_headers) -> dict:
    return make_auth_headers(EMAIL, "책벌레")


def app_login(client: TestClient, email: str = EMAIL, password: str = TEST_PASSWORD, **extra):
    return client.post("/auth/token", data={"username": email, "password": password, **extra})


def tokens(client: TestClient, email: str = EMAIL, **extra) -> dict:
    response = app_login(client, email, **extra)
    assert response.status_code == 200, response.text
    return response.json()


def refresh(client: TestClient, refresh_token: str):
    return client.post("/auth/refresh", json={"refresh_token": refresh_token})


def bearer(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def active_count(db: Session) -> int:
    db.expire_all()
    return len(db.scalars(select(RefreshToken).where(RefreshToken.revoked_at.is_(None))).all())


def set_suspension(db: Session, delta: timedelta | None) -> None:
    user = db.scalar(select(User).where(User.email == EMAIL))
    user.suspended_until = None if delta is None else (user_service.utc_now() + delta).replace(tzinfo=None)
    db.commit()


# ---------- 로그인 ----------


def test_app_login_returns_both_tokens(client, student, db_session) -> None:
    body = tokens(client, device_name="Galaxy S24")

    assert set(body) == {"access_token", "token_type", "expires_in", "refresh_token", "refresh_expires_at"}
    assert body["token_type"] == "bearer" and body["expires_in"] == 60 * 60
    assert client.get("/users/me", headers=bearer(body["access_token"])).status_code == 200
    row = db_session.scalar(select(RefreshToken))
    # 원문은 저장하지 않고 해시만 저장한다.
    assert row.token_hash == token_service.hash_token(body["refresh_token"]) != body["refresh_token"]
    assert row.device_name == "Galaxy S24"


def test_app_login_uses_same_checks_as_web_login(client, student, db_session) -> None:
    assert app_login(client, password="wrong-password").status_code == 401
    assert app_login(client, email="nobody@campus.ac.kr").status_code == 401
    assert app_login(client, device_name="가" * 101).status_code == 422
    set_suspension(db_session, timedelta(days=1))
    assert app_login(client).status_code == 403
    assert active_count(db_session) == 0  # 실패한 로그인은 토큰을 남기지 않는다.


def test_web_login_is_unchanged(client, student) -> None:
    body = client.post("/auth/login", data={"username": EMAIL, "password": TEST_PASSWORD}).json()
    assert set(body) == {"access_token", "token_type"}


# ---------- 갱신 ----------


def test_refresh_rotates_token(client, student, db_session) -> None:
    first = tokens(client)
    response = refresh(client, first["refresh_token"])

    assert response.status_code == 200
    second = response.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert client.get("/users/me", headers=bearer(second["access_token"])).status_code == 200
    # 새 토큰으로 다시 갱신할 수 있다.
    assert refresh(client, second["refresh_token"]).status_code == 200
    old = db_session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_service.hash_token(first["refresh_token"])))
    assert old.rotated_at is not None and old.replaced_by_id is not None


def test_reused_token_revokes_all_of_users_tokens(client, student, make_auth_headers, db_session) -> None:
    make_auth_headers("other@campus.ac.kr", "다른사람")
    other = tokens(client, "other@campus.ac.kr")
    phone = tokens(client)
    tablet = tokens(client)
    rotated = refresh(client, phone["refresh_token"]).json()

    # 이미 교체된 토큰이 다시 온다 = 훔친 토큰으로 본다.
    reused = refresh(client, phone["refresh_token"])
    assert reused.status_code == 401 and reused.json() == EXPIRED
    # 그 사용자의 모든 갱신 토큰(교체로 받은 새 토큰, 다른 기기 토큰)이 폐기된다.
    assert refresh(client, rotated["refresh_token"]).status_code == 401
    assert refresh(client, tablet["refresh_token"]).status_code == 401
    # 다른 사용자는 영향 없다.
    assert refresh(client, other["refresh_token"]).status_code == 200


def test_unknown_or_expired_token_is_401(client, student, db_session) -> None:
    assert refresh(client, "not-a-real-token").json() == EXPIRED
    body = tokens(client)
    db_session.execute(
        update(RefreshToken).values(expires_at=(user_service.utc_now() - timedelta(seconds=1)).replace(tzinfo=None))
    )
    db_session.commit()
    assert refresh(client, body["refresh_token"]).status_code == 401


@pytest.mark.parametrize("body", [{}, {"refresh_token": ""}, {"refresh_token": "x" * 201}, {"refresh_token": "a", "extra": 1}])
def test_invalid_refresh_body_is_422(client, body) -> None:
    assert client.post("/auth/refresh", json=body).status_code == 422


def test_suspended_user_cannot_refresh_until_suspension_ends(client, student, db_session) -> None:
    body = tokens(client)
    set_suspension(db_session, timedelta(days=1))

    response = refresh(client, body["refresh_token"])
    assert response.status_code == 401
    assert response.json()["detail"].endswith("까지 이용이 정지되었습니다.")
    # 정지 중에는 새 토큰을 주지 않지만 폐기하지도 않는다. 정지가 끝나면 다시 쓸 수 있다.
    assert active_count(db_session) == 1
    set_suspension(db_session, None)
    assert refresh(client, body["refresh_token"]).status_code == 200


# ---------- 비밀번호 변경·재설정·탈퇴 ----------


def test_password_change_revokes_refresh_tokens(client, student, db_session) -> None:
    body = tokens(client)
    changed = client.put(
        "/users/me/password",
        json={"current_password": TEST_PASSWORD, "new_password": "newpassword456"},
        headers=student,
    )
    assert changed.status_code == 200, changed.text

    assert refresh(client, body["refresh_token"]).json() == EXPIRED
    assert active_count(db_session) == 0


def test_password_reset_by_question_revokes_refresh_tokens(client, student, db_session) -> None:
    body = tokens(client)
    verified = client.post("/auth/password-reset/verify", json={"email": EMAIL, "answer": SECURITY_QUESTION["answer"]})
    reset_token = verified.json()["reset_token"]
    assert client.post("/auth/password-reset", json={"reset_token": reset_token, "new_password": "newpassword456"}).status_code == 204

    assert refresh(client, body["refresh_token"]).status_code == 401
    assert active_count(db_session) == 0


def test_cli_reset_password_revokes_refresh_tokens(client, student, db_session, capsys) -> None:
    body = tokens(client)
    assert cli.main(["reset-password", EMAIL], session_factory=TestingSessionLocal) == 0

    assert refresh(client, body["refresh_token"]).status_code == 401
    assert active_count(db_session) == 0


def test_withdraw_revokes_refresh_tokens(client, student, db_session) -> None:
    body = tokens(client)
    assert client.post("/users/me/withdraw", json={"password": TEST_PASSWORD}, headers=student).status_code == 204
    assert refresh(client, body["refresh_token"]).status_code == 401
    assert active_count(db_session) == 0


def test_admin_withdraw_revokes_refresh_tokens(client, student, make_admin_headers, db_session) -> None:
    body = tokens(client)
    uid = client.get("/users/me", headers=student).json()["id"]
    response = client.post(f"/admin/users/{uid}/withdraw", json={"reason": "사기 반복"}, headers=make_admin_headers())
    assert response.status_code in (200, 204), response.text
    assert refresh(client, body["refresh_token"]).status_code == 401
    assert active_count(db_session) == 0


def test_password_hash_change_without_revoke_is_still_rejected(client, student, db_session) -> None:
    """폐기를 빠뜨린 경로가 생겨도 발급 당시 비밀번호 지문이 달라 갱신이 거절된다(그리고 모두 폐기)."""
    body = tokens(client)
    user = db_session.scalar(select(User).where(User.email == EMAIL))
    user.password_hash = hash_password("changed-elsewhere")
    db_session.commit()

    assert refresh(client, body["refresh_token"]).status_code == 401
    assert active_count(db_session) == 0


# ---------- 로그아웃 ----------


def test_logout_revokes_only_this_device(client, student, db_session) -> None:
    phone = tokens(client)
    tablet = tokens(client)
    assert client.post("/auth/logout", json={"refresh_token": phone["refresh_token"]}).status_code == 204
    # 여러 번, 또는 없는 토큰으로 불러도 204
    assert client.post("/auth/logout", json={"refresh_token": phone["refresh_token"]}).status_code == 204
    assert client.post("/auth/logout", json={"refresh_token": "unknown"}).status_code == 204

    assert active_count(db_session) == 1
    assert refresh(client, tablet["refresh_token"]).status_code == 200


# ---------- 본인 확인 질문 목록 ----------


def test_security_questions_list_matches_presets(client) -> None:
    response = client.get("/auth/security-questions")
    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["key"]: item["text"] for item in items} == PRESET_QUESTIONS
    # 목록의 key로 가입할 수 있다.
    signup = client.post(
        "/auth/signup",
        json={
            "email": "new@campus.ac.kr",
            "password": TEST_PASSWORD,
            "nickname": "새사람",
            "security_question": {"question_key": items[0]["key"], "answer": "동네 문구점"},
        },
    )
    assert signup.status_code == 201, signup.text
