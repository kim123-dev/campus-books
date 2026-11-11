"""판매자 프로필: 개인정보 없음, 판매 중인 글만, 받은 후기와 매너 점수."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Review, User
from app.services import user_service


@pytest.fixture
def seller(make_auth_headers) -> dict:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


def user_id(client: TestClient, headers: dict) -> int:
    return client.get("/users/me", headers=headers).json()["id"]


def make_deal(client: TestClient, seller: dict, buyer: dict, create_post) -> int:
    """구매자와 거래를 하나 만들고 거래 번호를 돌려준다."""
    post = create_post(seller)
    conversation = client.post(f"/posts/{post['id']}/conversations", headers=buyer).json()
    client.post(f"/conversations/{conversation['id']}/messages", json={"content": "살게요"}, headers=buyer)
    client.patch(
        f"/posts/{post['id']}/status", json={"status": "SOLD", "buyer_id": user_id(client, buyer)}, headers=seller
    )
    return client.get(f"/conversations/{conversation['id']}", headers=buyer).json()["trade"]["trade_id"]


def review_seller(client: TestClient, seller: dict, make_auth_headers, create_post, ratings: list[str]) -> None:
    """구매자 여러 명이 판매자에게 후기를 하나씩 남긴다."""
    for index, rating in enumerate(ratings):
        buyer = make_auth_headers(f"buyer{index}@campus.ac.kr", f"구매자{index}")
        trade_id = make_deal(client, seller, buyer, create_post)
        response = client.post(f"/trades/{trade_id}/reviews", json={"rating": rating}, headers=buyer)
        assert response.status_code == 201, response.text


def test_profile_has_no_private_fields(client: TestClient, db_session: Session, seller: dict) -> None:
    # 정지 중이어도 프로필에 드러나지 않는다.
    user_service.suspend(db_session.get(User, user_id(client, seller)), 3)
    db_session.commit()

    body = client.get(f"/users/{user_id(client, seller)}/profile").json()

    assert body == {
        "id": user_id(client, seller),
        "nickname": "판매자",
        "manner": {"good": 0, "bad": 0, "total": 0, "good_ratio": None},
    }


def test_missing_and_withdrawn_users_are_404(client: TestClient, seller: dict) -> None:
    seller_id = user_id(client, seller)
    client.post("/users/me/withdraw", json={"password": "password123"}, headers=seller)

    for path in ("profile", "posts", "reviews"):
        assert client.get(f"/users/{seller_id}/{path}").status_code == 404
        assert client.get(f"/users/999/{path}").status_code == 404


def test_profile_posts_are_on_sale_or_reserved(client: TestClient, seller: dict, create_post) -> None:
    on_sale = create_post(seller, title="판매 중 글")
    reserved = create_post(seller, title="예약 중 글")
    sold = create_post(seller, title="판매 완료 글")
    client.patch(f"/posts/{reserved['id']}/status", json={"status": "RESERVED"}, headers=seller)
    client.patch(f"/posts/{sold['id']}/status", json={"status": "SOLD"}, headers=seller)

    body = client.get(f"/users/{user_id(client, seller)}/posts").json()

    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [reserved["id"], on_sale["id"]]
    assert "email" not in body["items"][0]["seller"]


@pytest.mark.parametrize(
    ("ratings", "expected"),
    [
        (["GOOD"], {"good": 1, "bad": 0, "total": 1, "good_ratio": None}),
        (["GOOD", "BAD"], {"good": 1, "bad": 1, "total": 2, "good_ratio": None}),
        (["GOOD", "GOOD", "BAD"], {"good": 2, "bad": 1, "total": 3, "good_ratio": 67}),
    ],
    ids=["1-review", "2-reviews", "3-reviews"],
)
def test_manner_ratio_needs_three_reviews(
    client: TestClient, seller: dict, make_auth_headers, create_post, ratings: list[str], expected: dict
) -> None:
    review_seller(client, seller, make_auth_headers, create_post, ratings)

    assert client.get(f"/users/{user_id(client, seller)}/profile").json()["manner"] == expected


def test_hidden_reviews_are_excluded(
    client: TestClient, db_session: Session, seller: dict, make_auth_headers, create_post
) -> None:
    review_seller(client, seller, make_auth_headers, create_post, ["GOOD", "GOOD", "BAD"])
    db_session.execute(update(Review).where(Review.rating == "BAD").values(hidden_at=user_service.utc_now()))
    db_session.commit()

    seller_id = user_id(client, seller)
    assert client.get(f"/users/{seller_id}/profile").json()["manner"] == {
        "good": 2,
        "bad": 0,
        "total": 2,
        "good_ratio": None,
    }
    reviews = client.get(f"/users/{seller_id}/reviews").json()
    assert reviews["total"] == 2
    assert {item["rating"] for item in reviews["items"]} == {"GOOD"}


def test_reviews_received_as_buyer_are_listed_too(
    client: TestClient, seller: dict, make_auth_headers, create_post
) -> None:
    buyer = make_auth_headers("buyer@campus.ac.kr", "구매자")
    trade_id = make_deal(client, seller, buyer, create_post)
    client.post(f"/trades/{trade_id}/reviews", json={"rating": "GOOD", "content": "입금 빨라요"}, headers=seller)

    items = client.get(f"/users/{user_id(client, buyer)}/reviews").json()["items"]

    assert [(i["reviewee_role"], i["reviewer_nickname"], i["content"]) for i in items] == [
        ("BUYER", "판매자", "입금 빨라요")
    ]
