"""판매 완료 때 구매자 고르기, 구매자 변경, 거래 기록 보존."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Trade, User
from app.services import user_service

INVALID_BUYER = {"detail": "이 글로 쪽지를 주고받은 사람만 구매자로 고를 수 있습니다."}


@pytest.fixture
def seller(make_auth_headers) -> dict:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def buyer(make_auth_headers) -> dict:
    return make_auth_headers("buyer@campus.ac.kr", "구매자")


@pytest.fixture
def buyer2(make_auth_headers) -> dict:
    return make_auth_headers("buyer2@campus.ac.kr", "구매자2")


@pytest.fixture
def post(seller: dict, create_post) -> dict:
    return create_post(seller)


def user_id(client: TestClient, headers: dict) -> int:
    return client.get("/users/me", headers=headers).json()["id"]


def chat(client: TestClient, post_id: int, headers: dict, content: str | None = "구매하고 싶어요") -> dict:
    """대화방을 열고(content가 있으면) 쪽지 하나를 보낸다."""
    conversation = client.post(f"/posts/{post_id}/conversations", headers=headers).json()
    if content is not None:
        sent = client.post(
            f"/conversations/{conversation['id']}/messages", json={"content": content}, headers=headers
        )
        assert sent.status_code == 201, sent.text
    return conversation


def sell(client: TestClient, post_id: int, headers: dict, buyer_id: int | None = None):
    body: dict = {"status": "SOLD"}
    if buyer_id is not None:
        body["buyer_id"] = buyer_id
    return client.patch(f"/posts/{post_id}/status", json=body, headers=headers)


def read_buyer(client: TestClient, post_id: int, headers: dict):
    return client.get(f"/posts/{post_id}/buyer", headers=headers)


def put_buyer(client: TestClient, post_id: int, headers: dict, buyer_id: int | None):
    return client.put(f"/posts/{post_id}/buyer", json={"buyer_id": buyer_id}, headers=headers)


def trade_count(db_session: Session) -> int:
    return db_session.scalar(select(func.count()).select_from(Trade))


# ---------- 후보 ----------


def test_candidates_are_chat_partners_who_sent_a_message(
    client: TestClient, seller: dict, buyer: dict, buyer2: dict, make_auth_headers, post: dict
) -> None:
    silent = make_auth_headers("silent@campus.ac.kr", "말없음")
    chat(client, post["id"], buyer)
    chat(client, post["id"], buyer2)
    chat(client, post["id"], silent, content=None)  # 방만 열고 아무 말도 하지 않았다.

    body = read_buyer(client, post["id"], seller).json()

    # 최근 대화순, 이메일은 없다.
    assert body == {
        "buyer": None,
        "candidates": [
            {"id": user_id(client, buyer2), "nickname": "구매자2"},
            {"id": user_id(client, buyer), "nickname": "구매자"},
        ],
        "changeable": False,
    }


def test_candidates_exclude_blocked_both_ways_and_withdrawn(
    client: TestClient, seller: dict, buyer: dict, buyer2: dict, make_auth_headers, post: dict
) -> None:
    gone = make_auth_headers("gone@campus.ac.kr", "탈퇴예정")
    for headers in (buyer, buyer2, gone):
        chat(client, post["id"], headers)
    client.post(f"/users/{user_id(client, buyer)}/block", headers=seller)  # 판매자가 차단
    client.post(f"/users/{user_id(client, seller)}/block", headers=buyer2)  # 구매자가 판매자를 차단
    client.post("/users/me/withdraw", json={"password": "password123"}, headers=gone)

    assert read_buyer(client, post["id"], seller).json()["candidates"] == []


def test_suspended_user_is_still_a_candidate(
    client: TestClient, db_session: Session, seller: dict, buyer: dict, post: dict
) -> None:
    chat(client, post["id"], buyer)
    user = db_session.get(User, user_id(client, buyer))
    user_service.suspend(user, 7)
    db_session.commit()

    assert [c["nickname"] for c in read_buyer(client, post["id"], seller).json()["candidates"]] == ["구매자"]


def test_only_seller_can_read_buyer(client: TestClient, buyer: dict, post: dict) -> None:
    assert read_buyer(client, post["id"], buyer).status_code == 403
    assert read_buyer(client, post["id"], {}).status_code == 401
    assert read_buyer(client, 999, buyer).status_code == 404


# ---------- 판매 완료 ----------


def test_sold_with_buyer_records_trade(
    client: TestClient, db_session: Session, seller: dict, buyer: dict, post: dict
) -> None:
    conversation = chat(client, post["id"], buyer)
    buyer_id = user_id(client, buyer)

    response = sell(client, post["id"], seller, buyer_id)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "SOLD"
    trade = db_session.scalar(select(Trade))
    assert (trade.post_id, trade.conversation_id, trade.buyer_id, trade.book_title_snapshot) == (
        post["id"],
        conversation["id"],
        buyer_id,
        post["book_title"],
    )
    body = read_buyer(client, post["id"], seller).json()
    assert body["buyer"] == {"id": buyer_id, "nickname": "구매자"}
    assert body["changeable"] is True


def test_sold_without_buyer_records_nothing(
    client: TestClient, db_session: Session, seller: dict, buyer: dict, post: dict
) -> None:
    chat(client, post["id"], buyer)

    assert sell(client, post["id"], seller).status_code == 200
    assert trade_count(db_session) == 0


def test_buyer_must_be_a_candidate(
    client: TestClient, db_session: Session, seller: dict, buyer: dict, post: dict
) -> None:
    # 대화하지 않은 사람, 판매자 자신은 고를 수 없다. 실패하면 상태도 바뀌지 않는다.
    for target in (user_id(client, buyer), user_id(client, seller)):
        response = sell(client, post["id"], seller, target)
        assert response.status_code == 400
        assert response.json() == INVALID_BUYER
    assert client.get(f"/posts/{post['id']}").json()["status"] == "ON_SALE"
    assert trade_count(db_session) == 0


def test_buyer_only_with_sold(client: TestClient, seller: dict, buyer: dict, post: dict) -> None:
    chat(client, post["id"], buyer)

    response = client.patch(
        f"/posts/{post['id']}/status", json={"status": "RESERVED", "buyer_id": user_id(client, buyer)}, headers=seller
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "구매자는 판매 완료로 바꿀 때만 고를 수 있습니다."}


def test_sold_retry_is_idempotent_but_other_buyer_conflicts(
    client: TestClient, db_session: Session, seller: dict, buyer: dict, buyer2: dict, post: dict
) -> None:
    chat(client, post["id"], buyer)
    chat(client, post["id"], buyer2)
    buyer_id = user_id(client, buyer)
    sell(client, post["id"], seller, buyer_id)

    assert sell(client, post["id"], seller, buyer_id).status_code == 200  # 같은 요청 재시도
    assert sell(client, post["id"], seller).status_code == 200  # 구매자 없이 SOLD → SOLD
    conflict = sell(client, post["id"], seller, user_id(client, buyer2))
    assert conflict.status_code == 409
    assert db_session.scalar(select(Trade.buyer_id)) == buyer_id


def test_cannot_add_buyer_after_sold_without_one(client: TestClient, seller: dict, buyer: dict, post: dict) -> None:
    chat(client, post["id"], buyer)
    sell(client, post["id"], seller)

    assert sell(client, post["id"], seller, user_id(client, buyer)).status_code == 409
    response = put_buyer(client, post["id"], seller, user_id(client, buyer))
    assert response.status_code == 409
    assert response.json() == {"detail": "구매자를 고르지 않고 판매 완료한 글은 나중에 구매자를 지정할 수 없습니다."}


# ---------- 구매자 변경 ----------


def test_change_buyer_to_other_candidate_keeps_trade_time(
    client: TestClient, db_session: Session, seller: dict, buyer: dict, buyer2: dict, post: dict
) -> None:
    chat(client, post["id"], buyer)
    conversation2 = chat(client, post["id"], buyer2)
    sell(client, post["id"], seller, user_id(client, buyer))
    # 거래 시각을 과거로 돌려, 바꾼 뒤에도 그대로인지(후기 기간이 늘어나지 않는지) 본다.
    past = datetime(2026, 1, 1)
    db_session.execute(update(Trade).values(created_at=past))
    db_session.commit()

    response = put_buyer(client, post["id"], seller, user_id(client, buyer2))

    assert response.status_code == 200, response.text
    assert response.json()["buyer"] == {"id": user_id(client, buyer2), "nickname": "구매자2"}
    db_session.expire_all()
    trade = db_session.scalar(select(Trade))
    assert (trade.buyer_id, trade.conversation_id) == (user_id(client, buyer2), conversation2["id"])
    assert trade.created_at.replace(tzinfo=None) == past


def test_change_buyer_to_none_removes_trade(
    client: TestClient, db_session: Session, seller: dict, buyer: dict, post: dict
) -> None:
    chat(client, post["id"], buyer)
    sell(client, post["id"], seller, user_id(client, buyer))

    response = put_buyer(client, post["id"], seller, None)

    assert response.status_code == 200
    assert response.json()["buyer"] is None
    assert response.json()["changeable"] is False
    assert trade_count(db_session) == 0
    assert client.get(f"/posts/{post['id']}").json()["status"] == "SOLD"


def test_change_buyer_rules(client: TestClient, seller: dict, buyer: dict, make_auth_headers, post: dict) -> None:
    stranger = make_auth_headers("stranger@campus.ac.kr", "제삼자")
    chat(client, post["id"], buyer)

    # 판매 완료 전에는 바꿀 수 없다.
    assert put_buyer(client, post["id"], seller, user_id(client, buyer)).status_code == 400
    sell(client, post["id"], seller, user_id(client, buyer))
    # 대화하지 않은 사람으로는 바꿀 수 없다.
    response = put_buyer(client, post["id"], seller, user_id(client, stranger))
    assert response.status_code == 400
    assert response.json() == INVALID_BUYER
    # 판매자만 바꿀 수 있다.
    assert put_buyer(client, post["id"], buyer, None).status_code == 403
    # 본문에 buyer_id가 꼭 있어야 한다. (빠뜨린 요청을 "선택 안 함"으로 오해하지 않게)
    assert client.put(f"/posts/{post['id']}/buyer", json={}, headers=seller).status_code == 422


# ---------- 글 삭제 ----------


def test_deleting_post_keeps_trade(
    client: TestClient, db_session: Session, seller: dict, buyer: dict, post: dict
) -> None:
    chat(client, post["id"], buyer)
    sell(client, post["id"], seller, user_id(client, buyer))

    assert client.delete(f"/posts/{post['id']}", headers=seller).status_code == 204

    db_session.expire_all()
    trade = db_session.scalar(select(Trade))
    assert trade.post_id is None
    assert trade.book_title_snapshot == post["book_title"]
