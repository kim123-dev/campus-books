"""찾는 교재 조건 등록·목록·삭제 (/users/me/alerts)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MAX_ALERTS_PER_USER, User

URL = "/users/me/alerts"


@pytest.fixture
def me(make_auth_headers: Callable[..., dict[str, str]]) -> dict[str, str]:
    return make_auth_headers("me@campus.ac.kr", "찾는사람")


def test_create_list_and_delete(client: TestClient, me: dict) -> None:
    created = client.post(URL, json={"keyword": "  자료구조  ", "max_price": 15000}, headers=me)
    assert created.status_code == 201
    body = created.json()
    assert body["keyword"] == "자료구조"  # 앞뒤 공백 제거
    assert body["max_price"] == 15000

    listed = client.get(URL, headers=me).json()
    assert listed["max_count"] == MAX_ALERTS_PER_USER
    assert [a["keyword"] for a in listed["items"]] == ["자료구조"]

    assert client.delete(f"{URL}/{body['id']}", headers=me).status_code == 204
    assert client.get(URL, headers=me).json()["items"] == []


def test_max_price_is_optional(client: TestClient, me: dict) -> None:
    response = client.post(URL, json={"keyword": "운영체제"}, headers=me)
    assert response.status_code == 201
    assert response.json()["max_price"] is None


def test_eleventh_alert_returns_400(client: TestClient, me: dict) -> None:
    for i in range(MAX_ALERTS_PER_USER):
        assert client.post(URL, json={"keyword": f"교재{i}"}, headers=me).status_code == 201
    response = client.post(URL, json={"keyword": "하나더"}, headers=me)
    assert response.status_code == 400
    assert str(MAX_ALERTS_PER_USER) in response.json()["detail"]


def test_duplicate_keyword_ignoring_case_returns_409(client: TestClient, me: dict) -> None:
    client.post(URL, json={"keyword": "Data Structures"}, headers=me)
    response = client.post(URL, json={"keyword": "data structures", "max_price": 1000}, headers=me)
    assert response.status_code == 409


def test_same_keyword_by_different_users_is_allowed(
    client: TestClient, me: dict, make_auth_headers: Callable[..., dict[str, str]]
) -> None:
    other = make_auth_headers("other@campus.ac.kr", "다른사람")
    assert client.post(URL, json={"keyword": "자료구조"}, headers=me).status_code == 201
    assert client.post(URL, json={"keyword": "자료구조"}, headers=other).status_code == 201


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"keyword": "자"}, id="one-char"),
        pytest.param({"keyword": "   "}, id="blank"),
        pytest.param({"keyword": "가" * 101}, id="too-long"),
        pytest.param({"keyword": "자료구조", "max_price": -1}, id="negative-price"),
        pytest.param({"keyword": "자료구조", "max_price": "1000"}, id="price-as-string"),
        pytest.param({"keyword": "자료구조", "user_id": 1}, id="unknown-field"),
    ],
)
def test_invalid_input_returns_422(client: TestClient, me: dict, payload: dict) -> None:
    assert client.post(URL, json=payload, headers=me).status_code == 422


def test_cannot_delete_others_alert(
    client: TestClient, me: dict, make_auth_headers: Callable[..., dict[str, str]]
) -> None:
    other = make_auth_headers("other@campus.ac.kr", "다른사람")
    alert_id = client.post(URL, json={"keyword": "자료구조"}, headers=other).json()["id"]
    assert client.delete(f"{URL}/{alert_id}", headers=me).status_code == 404
    assert client.delete(f"{URL}/99999", headers=me).status_code == 404
    assert len(client.get(URL, headers=other).json()["items"]) == 1


def test_requires_login(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={"keyword": "자료구조"}).status_code == 401
    assert client.delete(f"{URL}/1").status_code == 401


def test_suspended_user_cannot_create_but_can_list(client: TestClient, db_session: Session, me: dict) -> None:
    user = db_session.scalar(select(User).where(User.email == "me@campus.ac.kr"))
    user.suspended_until = (datetime.now(UTC) + timedelta(days=1)).replace(tzinfo=None)
    db_session.commit()
    assert client.post(URL, json={"keyword": "자료구조"}, headers=me).status_code == 403
    assert client.get(URL, headers=me).status_code == 200
