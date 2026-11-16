"""안 쓴 후기 알림(GET /notifications/reviews): 저장하지 않고 거래·후기에서 계산한다.

후기 작성 API가 받아 주는 거래만 나와야 한다: 기간 안, 아직 안 씀, 상대 탈퇴 아님, 내가 정지 중 아님(차단은 상관없음).
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Trade, User
from app.services import trade_service, user_service


@pytest.fixture
def seller(make_auth_headers) -> dict:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def buyer(make_auth_headers) -> dict:
    return make_auth_headers("buyer@campus.ac.kr", "구매자")


def user_id(client: TestClient, headers: dict) -> int:
    return client.get("/users/me", headers=headers).json()["id"]


@pytest.fixture
def deal(client: TestClient, seller: dict, buyer: dict, create_post) -> dict:
    """구매자가 쪽지를 보내고, 판매자가 그 구매자를 골라 판매 완료한 거래."""
    post = create_post(seller, title="자료구조 교재 팝니다")
    conversation = client.post(f"/posts/{post['id']}/conversations", headers=buyer).json()
    client.post(f"/conversations/{conversation['id']}/messages", json={"content": "살게요"}, headers=buyer)
    sold = client.patch(
        f"/posts/{post['id']}/status", json={"status": "SOLD", "buyer_id": user_id(client, buyer)}, headers=seller
    )
    assert sold.status_code == 200, sold.text
    trade = client.get(f"/conversations/{conversation['id']}", headers=buyer).json()["trade"]
    return {"post": post, "conversation": conversation, "trade_id": trade["trade_id"]}


def reminders(client: TestClient, headers: dict) -> list[dict]:
    response = client.get("/notifications/reviews", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == len(body["items"])
    return body["items"]


def write(client: TestClient, trade_id: int, headers: dict):
    return client.post(f"/trades/{trade_id}/reviews", json={"rating": "GOOD"}, headers=headers)


def age_trade(db_session: Session, age: timedelta) -> None:
    db_session.execute(update(Trade).values(created_at=user_service.utc_now() - age))
    db_session.commit()


def test_both_parties_get_reminder_right_after_sale(
    client: TestClient, seller: dict, buyer: dict, deal: dict
) -> None:
    for_seller = reminders(client, seller)
    for_buyer = reminders(client, buyer)

    assert len(for_seller) == len(for_buyer) == 1
    item = for_seller[0]
    assert item["trade_id"] == deal["trade_id"]
    assert item["conversation_id"] == deal["conversation"]["id"]
    assert item["partner_nickname"] == "구매자"
    assert item["post_title"] == "자료구조 교재 팝니다"
    assert item["book_title"] == deal["post"]["book_title"]
    assert item["days_left"] == 14
    assert {"deadline", "created_at"} <= item.keys()
    assert for_buyer[0]["partner_nickname"] == "판매자"


def test_writing_removes_only_my_reminder(client: TestClient, seller: dict, buyer: dict, deal: dict) -> None:
    assert write(client, deal["trade_id"], buyer).status_code == 201

    assert reminders(client, buyer) == []
    assert len(reminders(client, seller)) == 1


def test_days_left_counts_down_and_disappears_after_period(
    client: TestClient, db_session: Session, seller: dict, deal: dict
) -> None:
    # 11일 지나면 3일 남음 (화면은 3일 이하에서 D-3 배지)
    age_trade(db_session, timedelta(days=11))
    assert reminders(client, seller)[0]["days_left"] == 3
    # 마감 몇 시간 전도 1일로 올림
    age_trade(db_session, trade_service.REVIEW_PERIOD - timedelta(hours=2))
    assert reminders(client, seller)[0]["days_left"] == 1
    # 기간이 지나면 후기 작성도 400이고 알림도 없다.
    age_trade(db_session, trade_service.REVIEW_PERIOD + timedelta(minutes=1))
    assert reminders(client, seller) == []
    assert write(client, deal["trade_id"], seller).status_code == 400


def test_revert_to_on_sale_removes_reminders(client: TestClient, seller: dict, buyer: dict, deal: dict) -> None:
    reverted = client.patch(f"/posts/{deal['post']['id']}/status", json={"status": "ON_SALE"}, headers=seller)
    assert reverted.status_code == 200, reverted.text

    assert reminders(client, seller) == []
    assert reminders(client, buyer) == []


def test_deleted_post_keeps_reminder_with_book_title(
    client: TestClient, seller: dict, buyer: dict, deal: dict
) -> None:
    assert client.delete(f"/posts/{deal['post']['id']}", headers=seller).status_code == 204

    item = reminders(client, buyer)[0]
    assert item["post_title"] is None
    assert item["book_title"] == deal["post"]["book_title"]


def test_withdrawn_partner_is_excluded(client: TestClient, seller: dict, buyer: dict, deal: dict) -> None:
    client.post("/users/me/withdraw", json={"password": "password123"}, headers=buyer)

    assert reminders(client, seller) == []
    # 후기 작성 API도 같은 거래를 거절한다.
    assert write(client, deal["trade_id"], seller).status_code == 404


def test_suspended_user_gets_no_reminder(
    client: TestClient, db_session: Session, seller: dict, buyer: dict, deal: dict
) -> None:
    user_service.suspend(db_session.get(User, user_id(client, buyer)), 3)
    db_session.commit()

    # 정지 중에도 목록은 부를 수 있지만(읽기), 후기를 쓸 수 없으므로 비어 있다.
    assert reminders(client, buyer) == []
    assert write(client, deal["trade_id"], buyer).status_code == 403
    # 정지된 사람에게 후기를 쓰는 것은 되므로 상대에게는 남는다.
    assert len(reminders(client, seller)) == 1


def test_block_does_not_hide_reminder(client: TestClient, seller: dict, buyer: dict, deal: dict) -> None:
    # 차단 관계여도 후기는 쓸 수 있으므로(설계 결정 21번) 알림도 그대로다.
    client.post(f"/users/{user_id(client, buyer)}/block", headers=seller)

    assert len(reminders(client, seller)) == 1
    assert len(reminders(client, buyer)) == 1


def test_only_my_trades_newest_first(
    client: TestClient, db_session: Session, seller: dict, buyer: dict, deal: dict, make_auth_headers, create_post
) -> None:
    other = make_auth_headers("other@campus.ac.kr", "다른구매자")
    post = create_post(seller, title="두 번째 글")
    conversation = client.post(f"/posts/{post['id']}/conversations", headers=other).json()
    client.post(f"/conversations/{conversation['id']}/messages", json={"content": "저요"}, headers=other)
    client.patch(f"/posts/{post['id']}/status", json={"status": "SOLD", "buyer_id": user_id(client, other)}, headers=seller)
    # 첫 거래를 하루 전으로 옮겨 순서를 확실히 한다.
    db_session.execute(
        update(Trade).where(Trade.id == deal["trade_id"]).values(created_at=user_service.utc_now() - timedelta(days=1))
    )
    db_session.commit()

    assert [r["partner_nickname"] for r in reminders(client, seller)] == ["다른구매자", "구매자"]
    assert [r["partner_nickname"] for r in reminders(client, buyer)] == ["판매자"]
    assert [r["partner_nickname"] for r in reminders(client, other)] == ["판매자"]


def test_requires_login(client: TestClient) -> None:
    assert client.get("/notifications/reviews").status_code == 401
