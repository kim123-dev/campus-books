import base64
import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.security import ALGORITHM, create_access_token
from tests.conftest import SECURITY_QUESTION

ME_URL = "/users/me"
EMAIL = "student@campus.ac.kr"
PASSWORD = "password123"
NOT_AUTHENTICATED = {"detail": "로그인이 필요합니다."}
INVALID_TOKEN = {"detail": "인증 정보가 유효하지 않거나 만료되었습니다."}


# 가입 후 실제 로그인 API로 토큰을 받아, 발급부터 사용까지 전체 흐름을 검증한다.
@pytest.fixture
def user_id(client: TestClient) -> int:
    response = client.post(
        "/auth/signup", json={"email": EMAIL, "password": PASSWORD, "nickname": "책벌레", "security_question": SECURITY_QUESTION}
    )
    return response.json()["id"]


@pytest.fixture
def token(client: TestClient, user_id: int) -> str:
    response = client.post("/auth/login", data={"username": EMAIL, "password": PASSWORD})
    return response.json()["access_token"]


def get_me(client: TestClient, token: str | None = None, scheme: str = "Bearer"):
    headers = {} if token is None else {"Authorization": f"{scheme} {token}"}
    return client.get(ME_URL, headers=headers)


def _b64url(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def assert_401(response, expected_body: dict) -> None:
    assert response.status_code == 401
    assert response.json() == expected_body
    assert response.headers["WWW-Authenticate"] == "Bearer"


# ---------- 정상 ----------


def test_me_returns_current_user(client: TestClient, user_id: int, token: str) -> None:
    response = get_me(client, token)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == user_id
    assert body["email"] == EMAIL
    assert body["nickname"] == "책벌레"
    # role·정지 상태는 내 정보에만 있다. (다른 사용자 응답에는 없음: test_admin_auth.py)
    assert set(body) == {"id", "email", "nickname", "created_at", "role", "suspended_until", "nickname_changeable_at",
        "security_question", "security_question_changeable_at", "password_reset_notice"}
    assert (body["role"], body["suspended_until"]) == ("USER", None)


def test_me_never_exposes_password(client: TestClient, token: str) -> None:
    body = get_me(client, token).json()

    assert "password" not in body
    assert "password_hash" not in body


# ---------- 토큰 없음 ----------


def test_me_without_token_returns_401(client: TestClient) -> None:
    assert_401(get_me(client), NOT_AUTHENTICATED)


def test_me_with_non_bearer_scheme_returns_401(client: TestClient, token: str) -> None:
    # Bearer가 아닌 방식은 토큰이 없는 것으로 본다.
    assert_401(get_me(client, token, scheme="Basic"), NOT_AUTHENTICATED)


# ---------- 만료 ----------


def test_me_with_expired_token_returns_401(client: TestClient, user_id: int) -> None:
    expired = create_access_token(user_id, expires_delta=timedelta(seconds=-1))

    assert_401(get_me(client, expired), INVALID_TOKEN)


# ---------- 변조 ----------


def test_me_with_tampered_payload_returns_401(client: TestClient, token: str) -> None:
    # 서명은 그대로 두고 sub만 다른 사용자로 바꿔치기한다.
    header, _, signature = token.split(".")
    exp = int((datetime.now(UTC) + timedelta(minutes=5)).timestamp())
    forged = f"{header}.{_b64url({'sub': '2', 'exp': exp})}.{signature}"

    assert_401(get_me(client, forged), INVALID_TOKEN)


def test_me_with_token_signed_by_other_key_returns_401(
    client: TestClient, user_id: int
) -> None:
    exp = datetime.now(UTC) + timedelta(minutes=5)
    forged = jwt.encode({"sub": str(user_id), "exp": exp}, "attacker-key", algorithm=ALGORITHM)

    assert_401(get_me(client, forged), INVALID_TOKEN)


def test_me_with_alg_none_token_returns_401(client: TestClient, user_id: int) -> None:
    exp = int((datetime.now(UTC) + timedelta(minutes=5)).timestamp())
    forged = f"{_b64url({'alg': 'none', 'typ': 'JWT'})}.{_b64url({'sub': str(user_id), 'exp': exp})}."

    assert_401(get_me(client, forged), INVALID_TOKEN)


@pytest.mark.parametrize("bad_token", ["not-a-jwt", "a.b.c"], ids=["형식오류", "세그먼트만"])
def test_me_with_malformed_token_returns_401(client: TestClient, bad_token: str) -> None:
    assert_401(get_me(client, bad_token), INVALID_TOKEN)


# ---------- 없는 사용자 ----------


def test_me_with_token_for_missing_user_returns_401(client: TestClient, user_id: int) -> None:
    # 서명은 정상이지만 DB에 없는 사용자(탈퇴 등)의 토큰
    token_for_missing = create_access_token(999)

    assert_401(get_me(client, token_for_missing), INVALID_TOKEN)


# ---------- Swagger 연동 ----------


def test_openapi_registers_oauth2_password_flow(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    # 이 설정이 있어야 /docs에 Authorize 버튼이 나타나고 /auth/login으로 로그인한다.
    scheme = schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]
    assert scheme["flows"]["password"]["tokenUrl"] == "/auth/login"
    assert {"OAuth2PasswordBearer": []} in schema["paths"][ME_URL]["get"]["security"]
