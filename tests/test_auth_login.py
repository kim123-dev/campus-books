import base64
import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.exceptions import InvalidTokenError
from app.core.security import ALGORITHM, create_access_token, decode_access_token
from tests.conftest import SECURITY_QUESTION

LOGIN_URL = "/auth/login"
EMAIL = "student@campus.ac.kr"
PASSWORD = "password123"
INVALID_CREDENTIALS = {"detail": "이메일 또는 비밀번호가 올바르지 않습니다."}


# 로그인 테스트마다 가입된 사용자 한 명이 필요하다.
@pytest.fixture
def user_id(client: TestClient) -> int:
    response = client.post(
        "/auth/signup", json={"email": EMAIL, "password": PASSWORD, "nickname": "책벌레", "security_question": SECURITY_QUESTION}
    )
    return response.json()["id"]


# OAuth2 규격대로 JSON이 아닌 form(data=)으로 보낸다.
def login(client: TestClient, username: str = EMAIL, password: str = PASSWORD):
    return client.post(LOGIN_URL, data={"username": username, "password": password})


# ---------- 로그인 성공 ----------


def test_login_success_returns_bearer_token(client: TestClient, user_id: int) -> None:
    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    # 발급된 토큰을 풀면 가입한 사용자의 id가 나와야 한다.
    assert decode_access_token(body["access_token"]).user_id == user_id


def test_login_token_expiry_follows_settings(client: TestClient, user_id: int) -> None:
    token = login(client).json()["access_token"]

    payload = jwt.decode(token, get_settings().SECRET_KEY, algorithms=[ALGORITHM])
    expected = datetime.now(UTC) + timedelta(minutes=get_settings().ACCESS_TOKEN_EXPIRE_MINUTES)
    # 테스트 실행 시간 차이를 감안해 몇 초 오차는 허용한다.
    assert abs(payload["exp"] - expected.timestamp()) < 10


def test_login_ignores_email_case(client: TestClient, user_id: int) -> None:
    response = login(client, username="STUDENT@Campus.AC.KR")

    assert response.status_code == 200


# ---------- 로그인 실패 (401) ----------


def test_login_wrong_password_returns_401(client: TestClient, user_id: int) -> None:
    response = login(client, password="wrong-password")

    assert response.status_code == 401
    assert response.json() == INVALID_CREDENTIALS
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_login_unknown_email_returns_same_401(client: TestClient, user_id: int) -> None:
    response = login(client, username="nobody@campus.ac.kr")

    # 비밀번호가 틀린 경우와 메시지가 같아야 가입 여부를 알아낼 수 없다.
    assert response.status_code == 401
    assert response.json() == INVALID_CREDENTIALS


def test_login_password_over_72_bytes_returns_401_not_500(
    client: TestClient, user_id: int
) -> None:
    response = login(client, password="가" * 25)  # 75바이트

    assert response.status_code == 401


# ---------- 잘못된 입력 (422) ----------


@pytest.mark.parametrize(
    "data",
    [
        {"password": PASSWORD},
        {"username": EMAIL},
        {"username": EMAIL, "password": ""},
        {"username": "not-an-email", "password": PASSWORD},
    ],
    ids=["username-누락", "password-누락", "password-빈값", "username-이메일형식아님"],
)
def test_login_rejects_invalid_form(client: TestClient, data: dict[str, str]) -> None:
    response = client.post(LOGIN_URL, data=data)

    assert response.status_code == 422


def test_login_rejects_json_body(client: TestClient, user_id: int) -> None:
    # form 방식만 받으므로 JSON으로 보내면 필드를 찾지 못해 422가 된다.
    response = client.post(LOGIN_URL, json={"username": EMAIL, "password": PASSWORD})

    assert response.status_code == 422


# ---------- 토큰 검증 ----------
# 보호된 API(GET /users/me)는 3단계에서 만들기 때문에, 지금은 검증 함수를 직접 테스트한다.


def _b64url(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def test_decode_rejects_expired_token() -> None:
    token = create_access_token(1, expires_delta=timedelta(seconds=-1))

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_decode_rejects_tampered_payload() -> None:
    # 서명은 그대로 두고 payload의 sub만 다른 사용자로 바꿔치기한다.
    header, _, signature = create_access_token(1).split(".")
    exp = int((datetime.now(UTC) + timedelta(minutes=5)).timestamp())
    forged = f"{header}.{_b64url({'sub': '2', 'exp': exp})}.{signature}"

    with pytest.raises(InvalidTokenError):
        decode_access_token(forged)


def test_decode_rejects_token_signed_with_other_key() -> None:
    exp = datetime.now(UTC) + timedelta(minutes=5)
    token = jwt.encode({"sub": "1", "exp": exp}, "attacker-key", algorithm=ALGORITHM)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_decode_rejects_alg_none_token() -> None:
    # 서명 없이 alg를 none으로 바꾼 토큰은 허용 알고리즘 목록에 없어 거부되어야 한다.
    exp = int((datetime.now(UTC) + timedelta(minutes=5)).timestamp())
    token = f"{_b64url({'alg': 'none', 'typ': 'JWT'})}.{_b64url({'sub': '1', 'exp': exp})}."

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


@pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c"], ids=["빈값", "형식오류", "세그먼트만"])
def test_decode_rejects_malformed_token(token: str) -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)
