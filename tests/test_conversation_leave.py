"""대화방 나가기: 내 목록에서만 숨김, 상대에게는 그대로, 새 메시지가 오면 다시 나타나되 이전 내용은 숨김."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import pytest

from app.models import Message


@pytest.fixture
def seller(make_auth_headers) -> dict:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def buyer(make_auth_headers) -> dict:
    return make_auth_headers("buyer@campus.ac.kr", "구매자")


@pytest.fixture
def post(seller: dict, create_post) -> dict:
    return create_post(seller)


@pytest.fixture
def room(client: TestClient, buyer: dict, seller: dict, post: dict) -> int:
    room_id = client.post(f"/posts/{post['id']}/conversations", headers=buyer).json()["id"]
    send(client, room_id, buyer, "아직 판매 중인가요?")
    send(client, room_id, seller, "네 판매 중입니다")
    return room_id


def send(client: TestClient, room_id: int, headers: dict, content: str) -> dict:
    response = client.post(f"/conversations/{room_id}/messages", json={"content": content}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def leave(client: TestClient, room_id: int, headers: dict | None):
    return client.post(f"/conversations/{room_id}/leave", headers=headers or {})


def room_ids(client: TestClient, headers: dict) -> list[int]:
    return [item["id"] for item in client.get("/conversations", headers=headers).json()["items"]]


def contents(client: TestClient, room_id: int, headers: dict) -> list[str]:
    return [m["content"] for m in client.get(f"/conversations/{room_id}/messages", headers=headers).json()["items"]]


def unread(client: TestClient, headers: dict) -> int:
    return client.get("/conversations/unread-count", headers=headers).json()["unread_count"]


def test_leave_hides_room_only_for_me(client, buyer, seller, room) -> None:
    assert leave(client, room, buyer).status_code == 204

    assert room_ids(client, buyer) == []
    assert client.get("/conversations", headers=buyer).json()["total"] == 0
    # 상대 화면에는 방과 메시지가 그대로 있다.
    assert room_ids(client, seller) == [room]
    assert contents(client, room, seller) == ["아직 판매 중인가요?", "네 판매 중입니다"]


def test_messages_are_not_deleted(client, db_session: Session, buyer, room) -> None:
    leave(client, room, buyer)

    assert db_session.scalar(select(func.count()).select_from(Message)) == 2


def test_leave_marks_unread_as_read(client, buyer, room) -> None:
    assert unread(client, buyer) == 1

    leave(client, room, buyer)

    assert unread(client, buyer) == 0


def test_new_message_from_partner_brings_room_back_without_old_messages(client, buyer, seller, room) -> None:
    leave(client, room, buyer)

    send(client, room, seller, "혹시 아직 필요하세요?")

    assert room_ids(client, buyer) == [room]
    item = client.get("/conversations", headers=buyer).json()["items"][0]
    assert item["last_message"]["content"] == "혹시 아직 필요하세요?"
    assert item["unread_count"] == 1
    assert unread(client, buyer) == 1
    # 나가기 전 메시지는 계속 숨긴다.
    assert contents(client, room, buyer) == ["혹시 아직 필요하세요?"]


def test_cursor_queries_also_hide_old_messages(client, buyer, seller, room) -> None:
    leave(client, room, buyer)
    new = send(client, room, seller, "새 메시지")

    before = client.get(f"/conversations/{room}/messages", params={"before_id": new["id"]}, headers=buyer).json()
    after = client.get(f"/conversations/{room}/messages", params={"after_id": 1}, headers=buyer).json()

    assert before["items"] == [] and before["has_more"] is False
    assert [m["content"] for m in after["items"]] == ["새 메시지"]


def test_inquiring_again_reopens_empty_room(client, buyer, post, room) -> None:
    leave(client, room, buyer)

    response = client.post(f"/posts/{post['id']}/conversations", headers=buyer)

    assert response.status_code == 200 and response.json()["id"] == room
    assert response.json()["last_message"] is None
    assert room_ids(client, buyer) == [room]
    assert contents(client, room, buyer) == []


def test_my_own_new_message_brings_room_back(client, buyer, room) -> None:
    leave(client, room, buyer)

    send(client, room, buyer, "다시 연락드려요")

    assert room_ids(client, buyer) == [room]
    assert contents(client, room, buyer) == ["다시 연락드려요"]


def test_leaving_again_hides_newer_messages_too(client, buyer, seller, room) -> None:
    leave(client, room, buyer)
    send(client, room, seller, "두 번째")
    leave(client, room, buyer)

    assert room_ids(client, buyer) == []
    send(client, room, seller, "세 번째")
    assert contents(client, room, buyer) == ["세 번째"]


def test_leave_is_idempotent(client, buyer, room) -> None:
    assert leave(client, room, buyer).status_code == 204
    assert leave(client, room, buyer).status_code == 204
    assert room_ids(client, buyer) == []


def test_leave_errors(client, buyer, room, make_auth_headers) -> None:
    stranger = make_auth_headers("stranger@campus.ac.kr", "제삼자")

    assert leave(client, room, None).status_code == 401
    assert leave(client, room, stranger).status_code == 403
    assert leave(client, 9999, buyer).status_code == 404


def test_both_can_leave_and_room_stays_for_admin_evidence(client, buyer, seller, room, db_session) -> None:
    leave(client, room, buyer)
    leave(client, room, seller)

    assert room_ids(client, buyer) == [] and room_ids(client, seller) == []
    assert db_session.scalar(select(func.count()).select_from(Message)) == 2
