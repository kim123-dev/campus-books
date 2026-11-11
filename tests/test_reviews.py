"""거래 후기: 작성 권한, 한 번만, 기간, 정지·차단·탈퇴, 쪽지 화면의 후기 상태, 구매자 변경 잠금."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Review, Trade, User
from app.schemas.review import MAX_REVIEW_LENGTH
from app.services import trade_service, user_service


@pytest.fixture
def seller(make_auth_headers) -> dict:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def buyer(make_auth_headers) -> dict:
    return make_auth_headers("buyer@campus.ac.kr", "구매자")


@pytest.fixture
def stranger(make_auth_headers) -> dict:
    return make_auth_headers("stranger@campus.ac.kr", "제삼자")


def user_id(client: TestClient, headers: dict) -> int:
    return client.get("/users/me", headers=headers).json()["id"]


@pytest.fixture
def deal(client: TestClient, seller: dict, buyer: dict, create_post) -> dict:
    """구매자가 쪽지를 보내고, 판매자가 그 구매자를 골라 판매 완료한 거래."""
    post = create_post(seller)
    conversation = client.post(f"/posts/{post['id']}/conversations", headers=buyer).json()
    client.post(f"/conversations/{conversation['id']}/messages", json={"content": "살게요"}, headers=buyer)
    sold = client.patch(
        f"/posts/{post['id']}/status", json={"status": "SOLD", "buyer_id": user_id(client, buyer)}, headers=seller
    )
    assert sold.status_code == 200, sold.text
    trade = client.get(f"/conversations/{conversation['id']}", headers=buyer).json()["trade"]
    return {"post": post, "conversation": conversation, "trade_id": trade["trade_id"]}


def write(client: TestClient, trade_id: int, headers: dict, rating: str = "GOOD", content: str | None = "친절해요"):
    body: dict = {"rating": rating}
    if content is not None:
        body["content"] = content
    return client.post(f"/trades/{trade_id}/reviews", json=body, headers=headers)


def trade_state(client: TestClient, deal: dict, headers: dict) -> dict | None:
    return client.get(f"/conversations/{deal['conversation']['id']}", headers=headers).json()["trade"]


# ---------- 작성 ----------


def test_both_parties_write_once(client: TestClient, seller: dict, buyer: dict, deal: dict) -> None:
    by_buyer = write(client, deal["trade_id"], buyer, "GOOD", "  약속 시간 잘 지켜요  ")
    by_seller = write(client, deal["trade_id"], seller, "BAD", None)

    assert by_buyer.status_code == 201, by_buyer.text
    body = by_buyer.json()
    assert (body["rating"], body["content"], body["reviewer_nickname"], body["reviewee_role"]) == (
        "GOOD",
        "약속 시간 잘 지켜요",
        "구매자",
        "SELLER",  # 구매자가 쓴 후기는 판매자가 "판매자로서" 받은 후기다.
    )
    assert body["book_title"] == deal["post"]["book_title"]
    assert by_seller.status_code == 201
    assert by_seller.json()["reviewee_role"] == "BUYER"
    assert by_seller.json()["content"] is None

    again = write(client, deal["trade_id"], buyer)
    assert again.status_code == 409
    assert again.json() == {"detail": "이미 이 거래의 후기를 남겼습니다."}


def test_third_party_and_missing_trade(client: TestClient, stranger: dict, deal: dict) -> None:
    assert write(client, deal["trade_id"], stranger).status_code == 403
    assert write(client, 999, stranger).status_code == 404
    assert write(client, deal["trade_id"], {}).status_code == 401


@pytest.mark.parametrize(
    "body",
    [{}, {"rating": "SOSO"}, {"rating": "GOOD", "content": "가" * (MAX_REVIEW_LENGTH + 1)}, {"rating": "GOOD", "x": 1}],
    ids=["no-rating", "bad-rating", "too-long", "extra-field"],
)
def test_validation(client: TestClient, buyer: dict, deal: dict, body: dict) -> None:
    assert client.post(f"/trades/{deal['trade_id']}/reviews", json=body, headers=buyer).status_code == 422


def test_review_period(client: TestClient, db_session: Session, buyer: dict, deal: dict) -> None:
    # 거래 시각을 기간 바로 밖으로 옮긴다.
    past = user_service.utc_now() - trade_service.REVIEW_PERIOD - timedelta(minutes=1)
    db_session.execute(update(Trade).values(created_at=past))
    db_session.commit()

    response = write(client, deal["trade_id"], buyer)

    assert response.status_code == 400
    assert response.json() == {"detail": "후기는 거래 후 14일 안에만 남길 수 있습니다."}
    assert trade_state(client, deal, buyer)["can_write"] is False


def test_suspended_user_cannot_write(
    client: TestClient, db_session: Session, buyer: dict, seller: dict, deal: dict
) -> None:
    user_service.suspend(db_session.get(User, user_id(client, buyer)), 3)
    db_session.commit()

    assert write(client, deal["trade_id"], buyer).status_code == 403
    # 정지된 사람에게 후기를 쓰는 것은 된다.
    assert write(client, deal["trade_id"], seller).status_code == 201


def test_blocked_relation_can_still_write(client: TestClient, seller: dict, buyer: dict, deal: dict) -> None:
    client.post(f"/users/{user_id(client, buyer)}/block", headers=seller)

    assert write(client, deal["trade_id"], buyer, "BAD", "응답이 늦었어요").status_code == 201
    assert write(client, deal["trade_id"], seller).status_code == 201


def test_withdrawn_partner(client: TestClient, db_session: Session, seller: dict, buyer: dict, deal: dict) -> None:
    write(client, deal["trade_id"], buyer, "GOOD", "좋은 거래")
    client.post("/users/me/withdraw", json={"password": "password123"}, headers=buyer)

    # 탈퇴한 사람에게는 쓸 수 없다.
    response = write(client, deal["trade_id"], seller)
    assert response.status_code == 404
    assert response.json() == {"detail": "탈퇴한 사용자에게는 후기를 남길 수 없습니다."}
    assert trade_state(client, deal, seller)["can_write"] is False
    # 탈퇴한 사람이 쓴 후기는 남고 "탈퇴한 사용자"로 보인다.
    reviews = client.get(f"/users/{user_id(client, seller)}/reviews").json()["items"]
    assert [(r["reviewer_nickname"], r["content"]) for r in reviews] == [("탈퇴한 사용자", "좋은 거래")]


def test_review_survives_post_deletion(client: TestClient, seller: dict, buyer: dict, deal: dict) -> None:
    client.delete(f"/posts/{deal['post']['id']}", headers=seller)

    # 글이 지워져도 대화방으로 거래를 찾아 쓸 수 있고, 교재명은 사본으로 남는다.
    state = trade_state(client, deal, buyer)
    assert state is not None and state["can_write"] is True
    assert write(client, deal["trade_id"], buyer).json()["book_title"] == deal["post"]["book_title"]


# ---------- 쪽지 화면의 후기 상태 ----------


def test_conversation_trade_state(client: TestClient, buyer: dict, deal: dict) -> None:
    before = trade_state(client, deal, buyer)
    assert (before["trade_id"], before["written"], before["can_write"]) == (deal["trade_id"], False, True)

    write(client, deal["trade_id"], buyer)

    after = trade_state(client, deal, buyer)
    assert (after["written"], after["can_write"]) == (True, False)


def test_no_trade_state_without_buyer(client: TestClient, seller: dict, buyer: dict, create_post) -> None:
    post = create_post(seller)
    conversation = client.post(f"/posts/{post['id']}/conversations", headers=buyer).json()
    client.patch(f"/posts/{post['id']}/status", json={"status": "SOLD"}, headers=seller)

    assert client.get(f"/conversations/{conversation['id']}", headers=buyer).json()["trade"] is None


# ---------- 후기가 있으면 구매자를 바꿀 수 없다 ----------


@pytest.mark.parametrize("writer", ["buyer", "seller"])
@pytest.mark.parametrize("new_buyer", ["none", "same"])
def test_buyer_change_locked_after_any_review(
    client: TestClient, db_session: Session, request, seller: dict, deal: dict, writer: str, new_buyer: str
) -> None:
    write(client, deal["trade_id"], request.getfixturevalue(writer))
    buyer_id = None if new_buyer == "none" else db_session.scalar(select(Trade.buyer_id))

    response = client.put(f"/posts/{deal['post']['id']}/buyer", json={"buyer_id": buyer_id}, headers=seller)

    assert response.status_code == 409
    assert response.json() == {"detail": "후기가 남은 거래는 구매자를 바꿀 수 없습니다."}
    assert client.get(f"/posts/{deal['post']['id']}/buyer", headers=seller).json()["changeable"] is False
    assert db_session.scalar(select(Review.id)) is not None
