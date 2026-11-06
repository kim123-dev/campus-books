from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models import User

SIGNUP_URL = "/auth/signup"


# 테스트마다 바꾸고 싶은 필드만 덮어쓸 수 있게 기본 요청값을 둔다.
def signup(client: TestClient, **overrides: Any):
    payload = {"email": "student@campus.ac.kr", "password": "password123", "nickname": "책벌레"}
    payload.update(overrides)
    return client.post(SIGNUP_URL, json=payload)


# ---------- 정상 가입 ----------


def test_signup_success(client: TestClient) -> None:
    response = signup(client)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] >= 1
    assert body["email"] == "student@campus.ac.kr"
    assert body["nickname"] == "책벌레"
    assert "created_at" in body
    # 비밀번호 관련 값은 응답에 절대 포함되면 안 된다.
    assert "password" not in body
    assert "password_hash" not in body


def test_signup_stores_bcrypt_hash_not_plain_password(
    client: TestClient, db_session: Session
) -> None:
    signup(client)

    user = db_session.scalar(select(User).where(User.email == "student@campus.ac.kr"))
    assert user is not None
    assert user.password_hash != "password123"
    assert user.password_hash.startswith("$2b$")  # bcrypt 해시 형식
    assert verify_password("password123", user.password_hash)


def test_signup_normalizes_email_and_nickname(client: TestClient) -> None:
    response = signup(client, email="Student@Campus.AC.KR", nickname="  책벌레  ")

    assert response.status_code == 201
    assert response.json()["email"] == "student@campus.ac.kr"
    assert response.json()["nickname"] == "책벌레"


# ---------- 중복 (409) ----------


def test_signup_duplicate_email_returns_409(client: TestClient) -> None:
    signup(client)

    response = signup(client, nickname="다른닉네임")

    assert response.status_code == 409
    assert response.json() == {"detail": "이미 사용 중인 이메일입니다."}


def test_signup_duplicate_email_ignores_case(client: TestClient) -> None:
    signup(client)

    response = signup(client, email="STUDENT@campus.ac.kr", nickname="다른닉네임")

    assert response.status_code == 409
    assert response.json() == {"detail": "이미 사용 중인 이메일입니다."}


def test_signup_duplicate_nickname_returns_409(client: TestClient) -> None:
    signup(client)

    response = signup(client, email="other@campus.ac.kr")

    assert response.status_code == 409
    assert response.json() == {"detail": "이미 사용 중인 닉네임입니다."}


# ---------- 잘못된 입력 (422) ----------


@pytest.mark.parametrize(
    ("length", "expected_status"),
    [(7, 422), (8, 201), (64, 201), (65, 422)],
    ids=["7자-거부", "8자-허용", "64자-허용", "65자-거부"],
)
def test_signup_password_length_boundary(
    client: TestClient, length: int, expected_status: int
) -> None:
    response = signup(client, password="a" * length)

    assert response.status_code == expected_status


def test_signup_rejects_password_over_72_bytes(client: TestClient) -> None:
    # 25자라 글자 수 제한은 통과하지만 75바이트라 bcrypt 한도를 넘는다.
    response = signup(client, password="가" * 25)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "not-an-email"},
        {"email": ""},
        {"nickname": "a"},
        {"nickname": "   "},
        {"nickname": "a" * 31},
    ],
    ids=["이메일-형식오류", "이메일-빈값", "닉네임-1자", "닉네임-공백만", "닉네임-31자"],
)
def test_signup_rejects_invalid_input(client: TestClient, overrides: dict[str, str]) -> None:
    response = signup(client, **overrides)

    assert response.status_code == 422


@pytest.mark.parametrize("missing_field", ["email", "password", "nickname"])
def test_signup_rejects_missing_field(client: TestClient, missing_field: str) -> None:
    payload = {"email": "student@campus.ac.kr", "password": "password123", "nickname": "책벌레"}
    del payload[missing_field]

    response = client.post(SIGNUP_URL, json=payload)

    assert response.status_code == 422
