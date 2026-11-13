"""판매 완료 → 판매 중 되돌리기 (PATCH /posts/{id}/status, SOLD → ON_SALE).

되돌리면 거래 기록을 지워 대화 화면의 "후기 남기기"가 사라지고, 후기가 하나라도 있으면 409로 막는다.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AlertNotification, Trade
from tests.test_trades import chat, user_id

HAS_REVIEWS = {"detail": "후기가 이미 있어 되돌릴 수 없어요."}


@pytest.fixture
def seller(make_auth_headers: Callable[..., dict[str, str]]) -> dict[str, str]:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def buyer(make_auth_headers: Callable[..., dict[str, str]]) -> dict[str, str]:
    return make_auth_headers("buyer@campus.ac.kr", "구매자")


def set_status(client: TestClient, post_id: int, headers: dict, status: str, buyer_id: int | None = None):
    body: dict = {"status": status}
    if buyer_id is not None:
        body["buyer_id"] = buyer_id
    return client.patch(f"/posts/{post_id}/status", json=body, headers=headers)


@pytest.fixture
def sold_deal(client: TestClient, seller: dict, buyer: dict, create_post) -> dict:
    """구매자와 쪽지를 주고받은 뒤 그 구매자를 골라 판매 완료한 글."""
    post = create_post(seller, book_title="운영체제")
    conversation = chat(client, post["id"], buyer)
    sold = set_status(client, post["id"], seller, "SOLD", user_id(client, buyer))
    assert sold.status_code == 200, sold.text
    return {"post": post, "conversation": conversation}


def trade_count(db: Session, post_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Trade).where(Trade.post_id == post_id))


def conversation_trade(client: TestClient, conversation_id: int, headers: dict):
    return client.get(f"/conversations/{conversation_id}", headers=headers).json()["trade"]


def test_seller_reverts_sold_without_reviews(
    client: TestClient, db_session: Session, seller: dict, buyer: dict, sold_deal: dict
) -> None:
    post_id = sold_deal["post"]["id"]
    conversation_id = sold_deal["conversation"]["id"]
    assert conversation_trade(client, conversation_id, buyer) is not None  # 되돌리기 전에는 후기 줄이 있다.

    response = set_status(client, post_id, seller, "ON_SALE")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ON_SALE"
    assert trade_count(db_session, post_id) == 0
    # 거래 기록이 지워져 양쪽 대화 화면에서 "후기 남기기" 줄이 사라진다.
    assert conversation_trade(client, conversation_id, buyer) is None
    assert conversation_trade(client, conversation_id, seller) is None
    # 구매자 정보도 "선택 안 함"으로 돌아간다.
    assert client.get(f"/posts/{post_id}/buyer", headers=seller).json()["buyer"] is None


def test_revert_sold_without_buyer(client: TestClient, db_session: Session, seller: dict, create_post) -> None:
    # 구매자를 고르지 않고 판매 완료한 글은 지울 거래 기록이 없어도 되돌릴 수 있다.
    post = create_post(seller)
    assert set_status(client, post["id"], seller, "SOLD").status_code == 200

    response = set_status(client, post["id"], seller, "ON_SALE")

    assert response.status_code == 200
    assert response.json()["status"] == "ON_SALE"
    assert trade_count(db_session, post["id"]) == 0


def test_only_seller_can_revert(
    client: TestClient, db_session: Session, buyer: dict, make_auth_headers, sold_deal: dict
) -> None:
    post_id = sold_deal["post"]["id"]
    stranger = make_auth_headers("stranger@campus.ac.kr", "다른사람")

    for headers in (buyer, stranger):
        response = set_status(client, post_id, headers, "ON_SALE")
        assert response.status_code == 403
    assert client.get(f"/posts/{post_id}").json()["status"] == "SOLD"
    assert trade_count(db_session, post_id) == 1


def test_revert_without_login_returns_401(client: TestClient, sold_deal: dict) -> None:
    assert client.patch(f"/posts/{sold_deal['post']['id']}/status", json={"status": "ON_SALE"}).status_code == 401


def test_sold_can_only_go_back_to_on_sale(client: TestClient, db_session: Session, seller: dict, sold_deal: dict) -> None:
    post_id = sold_deal["post"]["id"]

    response = set_status(client, post_id, seller, "RESERVED")

    assert response.status_code == 400
    assert response.json() == {"detail": "판매 완료된 글은 판매 중으로만 되돌릴 수 있습니다."}
    assert trade_count(db_session, post_id) == 1


@pytest.mark.parametrize("status", ["ON_SALE", "RESERVED"])
def test_not_sold_post_does_not_revert(
    client: TestClient, db_session: Session, seller: dict, create_post, status: str
) -> None:
    # 판매 완료가 아닌 글은 기존 규칙대로: ON_SALE로 다시 보내면 그대로(200), 지울 거래도 없다.
    post = create_post(seller)
    set_status(client, post["id"], seller, status)

    response = set_status(client, post["id"], seller, "ON_SALE")

    assert response.status_code == 200
    assert response.json()["status"] == "ON_SALE"
    assert trade_count(db_session, post["id"]) == 0


@pytest.mark.parametrize("reviewer", ["buyer", "seller"])
def test_revert_with_review_returns_409(
    client: TestClient, db_session: Session, seller: dict, buyer: dict, sold_deal: dict, reviewer: str
) -> None:
    post_id = sold_deal["post"]["id"]
    conversation_id = sold_deal["conversation"]["id"]
    headers = buyer if reviewer == "buyer" else seller
    trade_id = conversation_trade(client, conversation_id, headers)["trade_id"]
    review = client.post(f"/trades/{trade_id}/reviews", json={"rating": "GOOD", "content": "좋아요"}, headers=headers)
    assert review.status_code == 201, review.text

    response = set_status(client, post_id, seller, "ON_SALE")

    assert response.status_code == 409
    assert response.json() == HAS_REVIEWS
    # 아무것도 바뀌지 않는다: 상태, 거래 기록, 후기 줄 모두 그대로.
    assert client.get(f"/posts/{post_id}").json()["status"] == "SOLD"
    assert trade_count(db_session, post_id) == 1
    assert conversation_trade(client, conversation_id, buyer) is not None


def test_reverted_post_shows_as_on_sale_in_list_search_and_wishlist(
    client: TestClient, seller: dict, buyer: dict, create_post
) -> None:
    # 판매 완료된 글은 새로 찜할 수 없으므로, 판매 중일 때 찜해 둔 글을 판매 완료했다가 되돌린다.
    post_id = create_post(seller, book_title="운영체제")["id"]
    assert client.post(f"/posts/{post_id}/wishlist", headers=buyer).status_code in (200, 201)
    chat(client, post_id, buyer)
    assert set_status(client, post_id, seller, "SOLD", user_id(client, buyer)).status_code == 200
    assert set_status(client, post_id, seller, "ON_SALE").status_code == 200

    def status_in(items: list[dict]) -> str:
        return next(item["status"] for item in items if item["id"] == post_id)

    assert status_in(client.get("/posts").json()["items"]) == "ON_SALE"
    assert status_in(client.get("/posts", params={"q": "운영체제"}).json()["items"]) == "ON_SALE"
    assert [item["id"] for item in client.get("/posts", params={"status": "ON_SALE"}).json()["items"]] == [post_id]
    wishlist = client.get("/users/me/wishlist", headers=buyer).json()["items"]
    assert status_in(wishlist) == "ON_SALE"
    assert client.get("/posts", params={"status": "SOLD"}).json()["items"] == []


def test_revert_does_not_resend_book_alerts(
    client: TestClient, db_session: Session, seller: dict, buyer: dict, create_post
) -> None:
    alert = client.post("/users/me/alerts", json={"keyword": "운영체제"}, headers=buyer)
    assert alert.status_code == 201, alert.text
    post = create_post(seller, book_title="운영체제")
    sent_before = db_session.scalar(select(func.count()).select_from(AlertNotification))
    assert sent_before == 1  # 새 글이라 한 번 보냈다.

    set_status(client, post["id"], seller, "SOLD")
    assert set_status(client, post["id"], seller, "ON_SALE").status_code == 200

    assert db_session.scalar(select(func.count()).select_from(AlertNotification)) == sent_before
    assert len(client.get("/notifications", headers=buyer).json()["items"]) == 1


def test_can_sell_again_after_revert(client: TestClient, db_session: Session, seller: dict, buyer: dict, sold_deal: dict) -> None:
    # 되돌린 뒤 다시 판매 완료하면 새 거래가 기록되어 후기를 남길 수 있다.
    post_id = sold_deal["post"]["id"]
    set_status(client, post_id, seller, "ON_SALE")

    response = set_status(client, post_id, seller, "SOLD", user_id(client, buyer))

    assert response.status_code == 200
    assert trade_count(db_session, post_id) == 1
    assert conversation_trade(client, sold_deal["conversation"]["id"], buyer) is not None
