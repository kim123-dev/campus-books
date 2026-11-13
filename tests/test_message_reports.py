"""쪽지 한 건 신고: 참여자만, 내 메시지 불가, 중복 409, 신고 시점 사본, 관리자 화면·처리."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from app.models import Message, MessageReportSnapshot, Report

REPORT = {"reason": "ABUSE", "description": "욕설을 했어요"}


@pytest.fixture
def seller(make_auth_headers) -> dict:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def buyer(make_auth_headers) -> dict:
    return make_auth_headers("buyer@campus.ac.kr", "구매자")


@pytest.fixture
def room(client: TestClient, buyer: dict, seller: dict, create_post) -> int:
    post = create_post(seller)
    return client.post(f"/posts/{post['id']}/conversations", headers=buyer).json()["id"]


def send(client: TestClient, room_id: int, headers: dict, content: str) -> int:
    response = client.post(f"/conversations/{room_id}/messages", json={"content": content}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def report(client: TestClient, message_id: int, headers: dict | None, body: dict | None = None):
    return client.post(f"/messages/{message_id}/reports", json=body or REPORT, headers=headers or {})


def test_report_partner_message_saves_snapshot(client, db_session: Session, buyer, seller, room) -> None:
    message_id = send(client, room, seller, "나쁜 말")

    response = report(client, message_id, buyer)

    assert response.status_code == 201, response.text
    saved = db_session.get(Report, response.json()["id"])
    assert (saved.target_type, saved.target_id) == ("MESSAGE", message_id)
    assert saved.reported_user_id == client.get("/users/me", headers=seller).json()["id"]
    snapshot = db_session.scalar(select(MessageReportSnapshot))
    assert (snapshot.report_id, snapshot.message_id, snapshot.conversation_id, snapshot.content) == (
        saved.id, message_id, room, "나쁜 말",
    )
    assert snapshot.image_filename is None


def test_snapshot_keeps_content_after_sender_withdraws(client, db_session, buyer, seller, room, make_admin_headers) -> None:
    message_id = send(client, room, seller, "탈퇴 전 메시지")
    report(client, message_id, buyer)
    client.post("/users/me/withdraw", json={"password": "password123"}, headers=seller)

    admin = make_admin_headers()
    item = client.get("/admin/reports", headers=admin).json()["items"][0]

    assert item["message"]["content"] == "탈퇴 전 메시지"
    assert db_session.scalar(select(Message)).content == "탈퇴 전 메시지"  # 메시지도 지우지 않는다


def test_cannot_report_own_message(client, buyer, room) -> None:
    message_id = send(client, room, buyer, "내 메시지")

    response = report(client, message_id, buyer)

    assert response.status_code == 400
    assert response.json() == {"detail": "내가 보낸 메시지는 신고할 수 없습니다."}


def test_only_participants_can_report(client, seller, room, make_auth_headers) -> None:
    message_id = send(client, room, seller, "안녕하세요")
    stranger = make_auth_headers("stranger@campus.ac.kr", "제삼자")

    assert report(client, message_id, stranger).status_code == 403
    assert report(client, message_id, None).status_code == 401
    assert report(client, 9999, stranger).status_code == 404


def test_duplicate_report_is_409(client, buyer, seller, room) -> None:
    message_id = send(client, room, seller, "나쁜 말")
    report(client, message_id, buyer)

    assert report(client, message_id, buyer).status_code == 409


def test_invalid_reason_is_422(client, buyer, seller, room) -> None:
    message_id = send(client, room, seller, "나쁜 말")

    assert report(client, message_id, buyer, {"reason": "OTHER"}).status_code == 422


def test_message_hidden_by_leaving_is_404(client, buyer, seller, room) -> None:
    message_id = send(client, room, seller, "나가기 전 메시지")
    client.post(f"/conversations/{room}/leave", headers=buyer)

    assert report(client, message_id, buyer).status_code == 404


def test_report_rate_limit_is_shared(client, db_session, buyer, seller, room) -> None:
    # 쪽지 도배 제한(10초 5건)을 피하려고 판매자 메시지 6개는 DB에 바로 넣는다. 신고는 1시간 5건까지다.
    seller_id = client.get("/users/me", headers=seller).json()["id"]
    rows = [Message(conversation_id=room, sender_id=seller_id, content=f"메시지 {i}") for i in range(6)]
    db_session.add_all(rows)
    db_session.commit()

    statuses = [report(client, row.id, buyer).status_code for row in rows]

    assert statuses == [201] * 5 + [429]


def test_admin_list_shows_only_reported_message(client, buyer, seller, room, make_admin_headers) -> None:
    send(client, room, seller, "평범한 메시지")
    bad = send(client, room, seller, "나쁜 말")
    report(client, bad, buyer)

    item = client.get("/admin/reports", headers=make_admin_headers()).json()["items"][0]

    assert item["target_type"] == "MESSAGE"
    assert item["message"]["content"] == "나쁜 말"
    assert item["message"]["conversation_id"] == room and item["message"]["has_image"] is False
    assert "평범한 메시지" not in str(item)


def test_admin_can_dismiss_or_suspend_but_not_delete_post(client, db_session, buyer, seller, room, make_admin_headers) -> None:
    admin = make_admin_headers()
    first = report(client, send(client, room, seller, "나쁜 말 1"), buyer).json()["id"]
    second = report(client, send(client, room, seller, "나쁜 말 2"), buyer).json()["id"]

    delete = client.post(f"/admin/reports/{first}/resolve", json={"action": "DELETE_POST", "note": "삭제"}, headers=admin)
    assert delete.status_code == 400
    assert delete.json() == {"detail": "쪽지 신고에는 글 삭제를 할 수 없습니다."}

    suspend = client.post(
        f"/admin/reports/{first}/resolve", json={"action": "SUSPEND", "suspend_days": 3, "note": "욕설"}, headers=admin
    )
    assert suspend.status_code == 200, suspend.text
    dismiss = client.post(f"/admin/reports/{second}/resolve", json={"action": "DISMISS"}, headers=admin)
    assert dismiss.status_code == 200, dismiss.text


def test_report_target_type_has_no_check_constraint() -> None:
    # 신고 대상 종류(MESSAGE)를 늘려도 운영 DB(PostgreSQL)에 ALTER가 필요 없어야 한다.
    ddl = str(CreateTable(Report.__table__).compile(dialect=postgresql.dialect()))
    assert "CHECK" not in ddl.upper()
