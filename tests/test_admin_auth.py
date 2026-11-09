"""관리자 권한. 일반 사용자·비로그인은 /admin API를 쓸 수 없고, 요청을 조작해도 관리자가 될 수 없다."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import cli
from app.main import app
from app.models import User, UserRole
from tests.conftest import TestingSessionLocal

# /admin으로 시작하는 모든 API를 앱의 API 문서(OpenAPI)에서 찾는다. 나중에 추가한 관리자 API도 자동으로 검사된다.
ADMIN_ROUTES = sorted(
    (method.upper(), re.sub(r"\{[^}]+\}", "1", path))
    for path, operations in app.openapi()["paths"].items()
    if path.startswith("/admin")
    for method in operations
)


def call(client: TestClient, method: str, path: str, headers: dict | None = None):
    # 본문이 필요한 API도 권한 검사가 먼저이므로, 올바른 본문을 넣어 "본문 때문에 422"가 나지 않게 한다.
    body = {"action": "DISMISS"} if method == "POST" else None
    return client.request(method, path, json=body, headers=headers or {})


def find_keys(value, keys: set[str]) -> set[str]:
    """JSON 안 어디에든 keys 중 하나가 키로 있으면 모아 돌려준다."""
    found: set[str] = set()
    if isinstance(value, dict):
        found |= keys & set(value)
        for child in value.values():
            found |= find_keys(child, keys)
    elif isinstance(value, list):
        for child in value:
            found |= find_keys(child, keys)
    return found


def test_admin_routes_are_found() -> None:
    assert ("GET", "/admin/reports") in ADMIN_ROUTES
    assert ("POST", "/admin/reports/1/resolve") in ADMIN_ROUTES


# ---------- /admin API 접근 ----------


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
def test_admin_routes_require_login(client, method, path) -> None:
    assert call(client, method, path).status_code == 401


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
def test_admin_routes_forbid_normal_user(client, auth_headers, method, path) -> None:
    response = call(client, method, path, auth_headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "관리자만 사용할 수 있습니다."


def test_forbidden_comes_before_not_found(client, auth_headers) -> None:
    # 없는 신고 번호여도 403이다. 일반 사용자가 신고 번호로 신고가 있는지 알아낼 수 없다.
    response = client.post("/admin/reports/9999/resolve", json={"action": "DISMISS"}, headers=auth_headers)

    assert response.status_code == 403


def test_forbidden_comes_before_validation(client, auth_headers) -> None:
    response = client.post("/admin/reports/1/resolve", json={"action": "HACK"}, headers=auth_headers)

    assert response.status_code == 403


def test_admin_can_use_admin_routes(client, make_admin_headers) -> None:
    assert client.get("/admin/reports", headers=make_admin_headers()).status_code == 200


# ---------- role 조작 방지 ----------


@pytest.mark.parametrize("role", ["ADMIN", "USER", "admin"])
def test_signup_with_role_field_returns_422(client, db_session, role) -> None:
    body = {"email": "hacker@campus.ac.kr", "password": "password123", "nickname": "해커", "role": role}

    assert client.post("/auth/signup", json=body).status_code == 422
    assert db_session.scalar(select(User)) is None


def test_signup_with_other_unknown_field_returns_422(client) -> None:
    body = {"email": "a@campus.ac.kr", "password": "password123", "nickname": "가나", "is_admin": True}

    assert client.post("/auth/signup", json=body).status_code == 422


def test_new_user_is_normal_user(client, db_session, auth_headers) -> None:
    assert db_session.scalar(select(User)).role == UserRole.USER
    assert client.get("/admin/reports", headers=auth_headers).status_code == 403


@pytest.mark.parametrize("field", ["role", "suspended_until", "seller_id"])
def test_post_update_cannot_carry_user_fields(client, auth_headers, create_post, field) -> None:
    post = create_post(auth_headers)

    response = client.patch(f"/posts/{post['id']}", json={field: "ADMIN"}, headers=auth_headers)

    assert response.status_code == 422


def test_login_form_role_is_ignored(client, db_session, auth_headers) -> None:
    # 로그인은 form(username·password)만 읽는다. role을 함께 보내도 권한이 바뀌지 않는다.
    response = client.post(
        "/auth/login", data={"username": "seller@campus.ac.kr", "password": "password123", "role": "ADMIN"}
    )

    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/admin/reports", headers=headers).status_code == 403
    assert db_session.scalar(select(User)).role == UserRole.USER


# ---------- role 노출 범위 ----------


def test_me_shows_role(client, auth_headers, make_admin_headers) -> None:
    assert client.get("/users/me", headers=auth_headers).json()["role"] == "USER"
    assert client.get("/users/me", headers=make_admin_headers()).json()["role"] == "ADMIN"


def test_role_not_exposed_to_other_users(client, make_auth_headers, make_admin_headers, create_post) -> None:
    admin = make_admin_headers()
    buyer = make_auth_headers("buyer@campus.ac.kr", "구매자")
    post = create_post(admin)  # 관리자가 쓴 글도 판매자 정보에 role이 없어야 한다.
    conversation = client.post(f"/posts/{post['id']}/conversations", headers=buyer).json()
    admin_id = client.get("/users/me", headers=admin).json()["id"]
    client.post(f"/users/{admin_id}/block", headers=buyer)

    signup = client.post(
        "/auth/signup", json={"email": "new@campus.ac.kr", "password": "password123", "nickname": "새사람"}
    )
    responses = {
        "signup": signup.json(),
        "list": client.get("/posts", headers=buyer).json(),
        "detail": client.get(f"/posts/{post['id']}", headers=buyer).json(),
        "conversation": client.get(f"/conversations/{conversation['id']}", headers=buyer).json(),
        "conversations": client.get("/conversations", headers=buyer).json(),
        "blocks": client.get("/users/me/blocks", headers=buyer).json(),
    }
    for name, body in responses.items():
        assert find_keys(body, {"role", "suspended_until"}) == set(), name


# ---------- 관리자 지정 CLI ----------


def run_cli(*args: str) -> int:
    return cli.main(["make-admin", *args], session_factory=TestingSessionLocal)


def test_cli_make_admin(client, db_session, auth_headers, capsys) -> None:
    assert client.get("/admin/reports", headers=auth_headers).status_code == 403

    assert run_cli("Seller@Campus.ac.kr") == 0  # 대소문자는 가입 때처럼 무시한다

    assert "관리자로 지정했습니다" in capsys.readouterr().out
    db_session.expire_all()
    assert db_session.scalar(select(User)).role == UserRole.ADMIN
    # 이미 받은 토큰으로 바로 쓸 수 있다. (요청마다 DB의 role을 읽는다)
    assert client.get("/admin/reports", headers=auth_headers).status_code == 200


def test_cli_make_admin_twice_changes_nothing(client, auth_headers, capsys) -> None:
    run_cli("seller@campus.ac.kr")

    assert run_cli("seller@campus.ac.kr") == 0
    assert "이미 관리자" in capsys.readouterr().out


def test_cli_unknown_email_fails(client, db_session, capsys) -> None:
    assert run_cli("nobody@campus.ac.kr") == 1
    assert "가입한 사용자가 없습니다" in capsys.readouterr().err


def test_cli_requires_command_and_email() -> None:
    with pytest.raises(SystemExit):
        cli.main([], session_factory=TestingSessionLocal)
    with pytest.raises(SystemExit):
        cli.main(["make-admin"], session_factory=TestingSessionLocal)
