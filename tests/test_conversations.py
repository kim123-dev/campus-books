import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Conversation
from app.services import conversation_service

OWN_POST = {"detail": "본인 글에는 문의할 수 없습니다."}
SOLD_POST = {"detail": "판매 완료된 글에는 새로 문의할 수 없습니다."}
NOT_PARTICIPANT = {"detail": "대화에 참여한 사용자만 볼 수 있습니다."}
NOT_FOUND = {"detail": "대화방을 찾을 수 없습니다."}


@pytest.fixture
def seller(make_auth_headers) -> dict:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def buyer(make_auth_headers) -> dict:
    return make_auth_headers("buyer@campus.ac.kr", "구매자")


@pytest.fixture
def stranger(make_auth_headers) -> dict:
    return make_auth_headers("stranger@campus.ac.kr", "제삼자")


@pytest.fixture
def post(seller: dict, create_post) -> dict:
    return create_post(seller)


def start(client: TestClient, post_id: int, headers: dict | None):
    return client.post(f"/posts/{post_id}/conversations", headers=headers or {})


@pytest.fixture
def conversation(client: TestClient, buyer: dict, post: dict) -> dict:
    response = start(client, post["id"], buyer)
    assert response.status_code == 201, response.text
    return response.json()


def send(client: TestClient, conversation_id: int, headers: dict, content: str = "안녕하세요"):
    response = client.post(
        f"/conversations/{conversation_id}/messages", json={"content": content}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def conversation_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Conversation))


# ---------- 문의 시작 ----------


def test_start_creates_conversation(client: TestClient, buyer: dict, post: dict) -> None:
    response = start(client, post["id"], buyer)

    assert response.status_code == 201
    body = response.json()
    assert body["post"] == {"id": post["id"], "title": post["title"], "status": "ON_SALE"}
    assert body["partner"] == {"id": post["seller"]["id"], "nickname": "판매자", "withdrawn": False}
    assert body["my_role"] == "BUYER"
    assert body["last_message"] is None
    assert body["unread_count"] == 0
    assert body["last_message_at"] is not None


def test_start_twice_returns_same_conversation(
    client: TestClient, buyer: dict, post: dict, conversation: dict, db_session: Session
) -> None:
    response = start(client, post["id"], buyer)

    assert response.status_code == 200
    assert response.json()["id"] == conversation["id"]
    assert conversation_count(db_session) == 1


def test_different_buyers_get_different_conversations(
    client: TestClient, buyer: dict, stranger: dict, post: dict, conversation: dict
) -> None:
    response = start(client, post["id"], stranger)

    assert response.status_code == 201
    assert response.json()["id"] != conversation["id"]


def test_start_on_own_post_is_rejected(
    client: TestClient, seller: dict, post: dict, db_session: Session
) -> None:
    response = start(client, post["id"], seller)

    assert response.status_code == 400
    assert response.json() == OWN_POST
    assert conversation_count(db_session) == 0


def test_start_on_missing_post_is_404(client: TestClient, buyer: dict) -> None:
    response = start(client, 9999, buyer)

    assert response.status_code == 404
    assert response.json() == {"detail": "게시글을 찾을 수 없습니다."}


def test_start_without_login_is_401(client: TestClient, post: dict) -> None:
    assert start(client, post["id"], None).status_code == 401


def test_start_with_invalid_token_is_401(client: TestClient, post: dict) -> None:
    assert start(client, post["id"], {"Authorization": "Bearer broken"}).status_code == 401


def test_start_on_sold_post_is_rejected(
    client: TestClient, seller: dict, buyer: dict, post: dict, db_session: Session
) -> None:
    client.patch(f"/posts/{post['id']}/status", json={"status": "SOLD"}, headers=seller)

    response = start(client, post["id"], buyer)

    assert response.status_code == 400
    assert response.json() == SOLD_POST
    assert conversation_count(db_session) == 0


def test_existing_conversation_is_returned_after_sold(
    client: TestClient, seller: dict, buyer: dict, post: dict, conversation: dict
) -> None:
    # 판매 완료 전에 시작한 대화는 거래 마무리를 위해 계속 쓸 수 있다.
    client.patch(f"/posts/{post['id']}/status", json={"status": "SOLD"}, headers=seller)

    response = start(client, post["id"], buyer)

    assert response.status_code == 200
    assert response.json()["id"] == conversation["id"]
    assert response.json()["post"]["status"] == "SOLD"
    send(client, conversation["id"], buyer, "거래 감사합니다")


def test_start_on_reserved_post_is_allowed(
    client: TestClient, seller: dict, buyer: dict, post: dict
) -> None:
    client.patch(f"/posts/{post['id']}/status", json={"status": "RESERVED"}, headers=seller)

    assert start(client, post["id"], buyer).status_code == 201


def test_db_rejects_duplicate_conversation(
    db_session: Session, post: dict, conversation: dict
) -> None:
    # API 검사를 거치지 않는 경우(동시 요청)를 대비한 unique 제약을 확인한다.
    existing = db_session.get(Conversation, conversation["id"])
    db_session.add(
        Conversation(post_id=post["id"], buyer_id=existing.buyer_id, seller_id=existing.seller_id)
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_concurrent_start_returns_existing(
    client: TestClient, buyer: dict, post: dict, conversation: dict, monkeypatch, db_session: Session
) -> None:
    # 다른 요청이 방을 막 만든 순간을 흉내 낸다: 처음 찾을 때는 없다고 나오고, INSERT에서 unique에 걸린다.
    original = conversation_service._find_conversation
    calls = {"count": 0}

    def find_misses_first_time(db, post_id, buyer_id):
        calls["count"] += 1
        return None if calls["count"] == 1 else original(db, post_id, buyer_id)

    monkeypatch.setattr(conversation_service, "_find_conversation", find_misses_first_time)

    response = start(client, post["id"], buyer)

    assert response.status_code == 200
    assert response.json()["id"] == conversation["id"]
    assert conversation_count(db_session) == 1


# ---------- 대화방 정보 ----------


def test_read_conversation_as_buyer_and_seller(
    client: TestClient, buyer: dict, seller: dict, conversation: dict
) -> None:
    as_buyer = client.get(f"/conversations/{conversation['id']}", headers=buyer).json()
    as_seller = client.get(f"/conversations/{conversation['id']}", headers=seller).json()

    assert as_buyer["my_role"] == "BUYER"
    assert as_buyer["partner"]["nickname"] == "판매자"
    assert as_seller["my_role"] == "SELLER"
    assert as_seller["partner"]["nickname"] == "구매자"


def test_read_conversation_by_stranger_is_403(
    client: TestClient, stranger: dict, conversation: dict
) -> None:
    response = client.get(f"/conversations/{conversation['id']}", headers=stranger)

    assert response.status_code == 403
    assert response.json() == NOT_PARTICIPANT


def test_read_missing_conversation_is_404(client: TestClient, buyer: dict) -> None:
    response = client.get("/conversations/9999", headers=buyer)

    assert response.status_code == 404
    assert response.json() == NOT_FOUND


def test_read_conversation_without_login_is_401(client: TestClient, conversation: dict) -> None:
    assert client.get(f"/conversations/{conversation['id']}").status_code == 401


# ---------- 개인정보 비노출 ----------


def test_responses_do_not_expose_email_or_password(
    client: TestClient, buyer: dict, seller: dict, conversation: dict
) -> None:
    send(client, conversation["id"], buyer)
    responses = [
        client.post(f"/posts/{conversation['post']['id']}/conversations", headers=buyer),
        client.get("/conversations", headers=buyer),
        client.get("/conversations", headers=seller),
        client.get(f"/conversations/{conversation['id']}", headers=seller),
        client.get(f"/conversations/{conversation['id']}/messages", headers=seller),
    ]

    for response in responses:
        assert response.status_code == 200
        assert "campus.ac.kr" not in response.text
        assert "email" not in response.text
        assert "password" not in response.text
    partner = responses[2].json()["items"][0]["partner"]
    assert set(partner) == {"id", "nickname", "withdrawn"}


# ---------- 목록 ----------


def test_list_is_empty_without_conversations(client: TestClient, buyer: dict) -> None:
    body = client.get("/conversations", headers=buyer).json()

    assert body == {"items": [], "total": 0, "page": 1, "size": 20}


def test_list_shows_conversation_to_both_sides_only(
    client: TestClient, buyer: dict, seller: dict, stranger: dict, conversation: dict
) -> None:
    assert [c["id"] for c in client.get("/conversations", headers=buyer).json()["items"]] == [
        conversation["id"]
    ]
    assert [c["id"] for c in client.get("/conversations", headers=seller).json()["items"]] == [
        conversation["id"]
    ]
    assert client.get("/conversations", headers=stranger).json()["total"] == 0


def test_list_without_login_is_401(client: TestClient) -> None:
    assert client.get("/conversations").status_code == 401


def test_list_shows_last_message(
    client: TestClient, buyer: dict, seller: dict, conversation: dict
) -> None:
    send(client, conversation["id"], buyer, "첫 메시지")
    send(client, conversation["id"], seller, "답장입니다")

    as_buyer = client.get("/conversations", headers=buyer).json()["items"][0]
    as_seller = client.get("/conversations", headers=seller).json()["items"][0]

    assert as_buyer["last_message"]["content"] == "답장입니다"
    assert as_buyer["last_message"]["is_mine"] is False
    assert as_seller["last_message"]["is_mine"] is True


def test_list_is_sorted_by_latest_message(
    client: TestClient, buyer: dict, seller: dict, create_post
) -> None:
    # 같은 초 안에서도 메시지 순서대로 정렬되는지 확인한다.
    first = start(client, create_post(seller, title="첫 글")["id"], buyer).json()
    second = start(client, create_post(seller, title="둘째 글")["id"], buyer).json()
    third = start(client, create_post(seller, title="셋째 글")["id"], buyer).json()

    send(client, second["id"], buyer)
    send(client, first["id"], buyer)

    ids = [c["id"] for c in client.get("/conversations", headers=seller).json()["items"]]
    # 메시지가 있는 방이 최신 메시지순으로 먼저, 메시지 없는 방은 뒤에 온다.
    assert ids[:2] == [first["id"], second["id"]]
    assert set(ids) == {first["id"], second["id"], third["id"]}

    send(client, second["id"], seller)
    ids = [c["id"] for c in client.get("/conversations", headers=buyer).json()["items"]]
    assert ids[:2] == [second["id"], first["id"]]


def test_list_pagination(client: TestClient, buyer: dict, seller: dict, create_post) -> None:
    for i in range(5):
        start(client, create_post(seller, title=f"글 {i}")["id"], buyer)

    page1 = client.get("/conversations", params={"page": 1, "size": 2}, headers=buyer).json()
    page3 = client.get("/conversations", params={"page": 3, "size": 2}, headers=buyer).json()
    beyond = client.get("/conversations", params={"page": 4, "size": 2}, headers=buyer).json()

    assert page1["total"] == 5 and len(page1["items"]) == 2
    assert len(page3["items"]) == 1
    assert beyond["items"] == [] and beyond["total"] == 5
    all_ids = {
        c["id"]
        for page in (1, 2, 3)
        for c in client.get(
            "/conversations", params={"page": page, "size": 2}, headers=buyer
        ).json()["items"]
    }
    assert len(all_ids) == 5


@pytest.mark.parametrize("params", [{"page": 0}, {"size": 0}, {"size": 101}, {"page": "abc"}])
def test_list_rejects_invalid_paging(client: TestClient, buyer: dict, params: dict) -> None:
    assert client.get("/conversations", params=params, headers=buyer).status_code == 422


# ---------- 글이 삭제되면 대화방은 남는다 ----------


def test_conversation_survives_post_deletion(
    client: TestClient, buyer: dict, seller: dict, post: dict, conversation: dict, db_session: Session
) -> None:
    send(client, conversation["id"], buyer, "아직 있나요?")

    assert client.delete(f"/posts/{post['id']}", headers=seller).status_code == 204
    db_session.expire_all()  # 세션에 남은 글 캐시를 비워 실제 DB 상태를 읽게 한다.

    listed = client.get("/conversations", headers=buyer).json()["items"][0]
    assert listed["id"] == conversation["id"]
    assert listed["post"] is None
    assert listed["partner"]["nickname"] == "판매자"

    messages = client.get(f"/conversations/{conversation['id']}/messages", headers=seller).json()
    assert [m["content"] for m in messages["items"]] == ["아직 있나요?"]
    # 글이 없어도 참여자는 계속 대화할 수 있다.
    send(client, conversation["id"], seller, "글은 내렸지만 아직 있어요")


def test_stranger_still_blocked_after_post_deletion(
    client: TestClient, seller: dict, stranger: dict, post: dict, conversation: dict, db_session: Session
) -> None:
    client.delete(f"/posts/{post['id']}", headers=seller)
    db_session.expire_all()

    assert client.get(f"/conversations/{conversation['id']}", headers=stranger).status_code == 403


def test_list_query_count_does_not_grow_with_conversations(
    client: TestClient, buyer: dict, make_auth_headers, create_post, db_session: Session
) -> None:
    # 판매자·글·메시지가 서로 다른 방 4개를 만든다.
    for i in range(4):
        seller_headers = make_auth_headers(f"s{i}@campus.ac.kr", f"판매자{i}")
        room = start(client, create_post(seller_headers, title=f"글 {i}")["id"], buyer).json()
        send(client, room["id"], seller_headers, f"답장 {i}")
    db_session.expire_all()  # 세션 캐시를 비워, 실제로 DB 조회가 일어나게 한다.

    statements: list[str] = []

    def record(conn, cursor, statement, *args) -> None:
        statements.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        response = client.get("/conversations", headers=buyer)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    items = response.json()["items"]
    assert len(items) == 4
    assert all(item["last_message"] and item["unread_count"] == 1 for item in items)
    # 로그인 사용자 1 + 개수 1 + 방·글·상대 JOIN 1 + 마지막 메시지 1 + 안 읽은 개수 1. 방이 늘어도 그대로여야 한다.
    assert len(statements) == 5


# ---------- 안 읽은 개수 (헤더 배지) ----------


def unread_total(client: TestClient, headers: dict | None):
    return client.get("/conversations/unread-count", headers=headers or {})


def test_unread_count_without_login_is_401(client: TestClient) -> None:
    assert unread_total(client, None).status_code == 401


def test_unread_count_is_zero_without_conversations(client: TestClient, buyer: dict) -> None:
    # /conversations/{conversation_id}와 경로가 겹치지 않는지도 함께 확인한다. (겹치면 422)
    response = unread_total(client, buyer)

    assert response.status_code == 200
    assert response.json() == {"unread_count": 0}


def test_unread_count_sums_all_conversations(
    client: TestClient, buyer: dict, seller: dict, stranger: dict, post: dict, conversation: dict
) -> None:
    other = start(client, post["id"], stranger).json()
    send(client, conversation["id"], buyer, "1")
    send(client, other["id"], stranger, "1")
    send(client, other["id"], stranger, "2")

    assert unread_total(client, seller).json() == {"unread_count": 3}
    # 내가 보낸 메시지는 세지 않는다.
    assert unread_total(client, buyer).json() == {"unread_count": 0}
    # 남의 대화방 메시지는 세지 않는다.
    assert unread_total(client, stranger).json() == {"unread_count": 0}


def test_unread_count_drops_after_reading(
    client: TestClient, buyer: dict, seller: dict, stranger: dict, post: dict, conversation: dict
) -> None:
    other = start(client, post["id"], stranger).json()
    send(client, conversation["id"], buyer, "1")
    send(client, other["id"], stranger, "1")

    client.get(f"/conversations/{conversation['id']}/messages", headers=seller)

    assert unread_total(client, seller).json() == {"unread_count": 1}
