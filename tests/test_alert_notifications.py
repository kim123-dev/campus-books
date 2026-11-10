"""찾는 교재 알림: 새 글·수정 글 매칭과 알림 목록 (/notifications)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AlertNotification, BookAlert
from tests.conftest import TEST_PASSWORD


@pytest.fixture
def seller(make_auth_headers: Callable[..., dict[str, str]]) -> dict[str, str]:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def buyer(make_auth_headers: Callable[..., dict[str, str]]) -> dict[str, str]:
    return make_auth_headers("buyer@campus.ac.kr", "구매자")


@pytest.fixture
def add_alert(client: TestClient) -> Callable[..., dict]:
    def _add(headers: dict, keyword: str, max_price: int | None = None) -> dict:
        response = client.post("/users/me/alerts", json={"keyword": keyword, "max_price": max_price}, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _add


def notifications(client: TestClient, headers: dict) -> list[dict]:
    response = client.get("/notifications", headers=headers)
    assert response.status_code == 200
    return response.json()["items"]


def unread(client: TestClient, headers: dict) -> int:
    return client.get("/notifications/unread-count", headers=headers).json()["unread_count"]


# ---------- 매칭 규칙 ----------


@pytest.mark.parametrize(
    ("keyword", "overrides"),
    [
        pytest.param("자료구조", {"book_title": "C언어로 쉽게 풀어쓴 자료구조"}, id="book-title-partial"),
        pytest.param("알고리", {"book_title": "다른 책", "course_name": "알고리즘"}, id="course-name-partial"),
        pytest.param("data struct", {"book_title": "Data Structures in C"}, id="ignore-case"),
        pytest.param("100%", {"book_title": "토익 100% 합격"}, id="percent-literal"),
        pytest.param("a_b", {"book_title": "책 a_b 개정판"}, id="underscore-literal"),
    ],
)
def test_new_post_matching_keyword_creates_notification(
    client, seller, buyer, add_alert, create_post, keyword: str, overrides: dict
) -> None:
    add_alert(buyer, keyword)
    post = create_post(seller, **overrides)
    items = notifications(client, buyer)
    assert [n["post"]["id"] for n in items] == [post["id"]]
    assert items[0]["keyword"] == keyword
    assert items[0]["read_at"] is None


@pytest.mark.parametrize(
    ("keyword", "overrides"),
    [
        pytest.param("팝니다", {"title": "자료구조 팝니다", "book_title": "전공책", "course_name": None}, id="title-only"),
        pytest.param("100%", {"book_title": "토익 1000제"}, id="percent-not-wildcard"),
        pytest.param("a_b", {"book_title": "책 axb 개정판"}, id="underscore-not-wildcard"),
        pytest.param("운영체제", {"book_title": "자료구조"}, id="no-match"),
    ],
)
def test_non_matching_post_creates_no_notification(
    client, seller, buyer, add_alert, create_post, keyword: str, overrides: dict
) -> None:
    add_alert(buyer, keyword)
    create_post(seller, **overrides)
    assert notifications(client, buyer) == []


def test_max_price_is_inclusive(client, seller, buyer, add_alert, create_post) -> None:
    add_alert(buyer, "자료구조", max_price=15000)
    at_limit = create_post(seller, book_title="자료구조", price=15000)
    create_post(seller, book_title="자료구조", price=15001)
    assert [n["post"]["id"] for n in notifications(client, buyer)] == [at_limit["id"]]


def test_no_max_price_matches_any_price(client, seller, buyer, add_alert, create_post) -> None:
    add_alert(buyer, "자료구조")
    create_post(seller, book_title="자료구조", price=9_000_000)
    assert len(notifications(client, buyer)) == 1


def test_own_post_is_excluded(client, seller, add_alert, create_post) -> None:
    add_alert(seller, "자료구조")
    create_post(seller, book_title="자료구조")
    assert notifications(client, seller) == []


def test_blocked_seller_post_is_excluded(client, seller, buyer, add_alert, create_post) -> None:
    seller_id = client.get("/users/me", headers=seller).json()["id"]
    client.post(f"/users/{seller_id}/block", headers=buyer)
    add_alert(buyer, "자료구조")
    create_post(seller, book_title="자료구조")
    assert notifications(client, buyer) == []


def test_blocking_later_hides_existing_notification(client, seller, buyer, add_alert, create_post) -> None:
    add_alert(buyer, "자료구조")
    create_post(seller, book_title="자료구조")
    assert unread(client, buyer) == 1
    seller_id = client.get("/users/me", headers=seller).json()["id"]
    client.post(f"/users/{seller_id}/block", headers=buyer)
    assert notifications(client, buyer) == []
    assert unread(client, buyer) == 0


def test_two_matching_alerts_create_one_notification(client, seller, buyer, add_alert, create_post) -> None:
    add_alert(buyer, "자료구조")
    add_alert(buyer, "C언어")
    create_post(seller, book_title="C언어로 쉽게 풀어쓴 자료구조")
    items = notifications(client, buyer)
    assert len(items) == 1
    assert items[0]["keyword"] == "자료구조"  # 먼저 등록한 조건


def test_each_matching_user_gets_notification(
    client, seller, buyer, add_alert, create_post, make_auth_headers
) -> None:
    third = make_auth_headers("third@campus.ac.kr", "세번째")
    add_alert(buyer, "자료구조")
    add_alert(third, "자료")
    create_post(seller, book_title="자료구조")
    assert len(notifications(client, buyer)) == 1
    assert len(notifications(client, third)) == 1


# ---------- 글 수정 ----------


def test_edit_that_newly_matches_creates_notification_once(client, seller, buyer, add_alert, create_post) -> None:
    add_alert(buyer, "운영체제")
    post = create_post(seller, book_title="자료구조")
    assert notifications(client, buyer) == []

    client.patch(f"/posts/{post['id']}", json={"book_title": "운영체제 공룡책"}, headers=seller)
    assert len(notifications(client, buyer)) == 1
    # 다시 수정해도 같은 글로 두 번 알리지 않는다.
    client.patch(f"/posts/{post['id']}", json={"course_name": "운영체제"}, headers=seller)
    assert len(notifications(client, buyer)) == 1


def test_price_drop_into_range_creates_notification(client, seller, buyer, add_alert, create_post) -> None:
    add_alert(buyer, "자료구조", max_price=10000)
    post = create_post(seller, book_title="자료구조", price=20000)
    assert notifications(client, buyer) == []
    client.patch(f"/posts/{post['id']}", json={"price": 9000}, headers=seller)
    assert len(notifications(client, buyer)) == 1


def test_title_only_edit_does_not_rematch(
    client, db_session: Session, seller, buyer, add_alert, create_post
) -> None:
    post = create_post(seller, book_title="자료구조")
    # 글을 쓴 뒤에 조건을 등록했다. 제목만 고치는 수정은 다시 매칭하지 않으므로 알림이 생기지 않는다.
    add_alert(buyer, "자료구조")
    client.patch(f"/posts/{post['id']}", json={"title": "제목만 수정"}, headers=seller)
    assert notifications(client, buyer) == []


def test_reserved_post_edit_does_not_notify(client, seller, buyer, add_alert, create_post) -> None:
    add_alert(buyer, "운영체제")
    post = create_post(seller, book_title="자료구조")
    client.patch(f"/posts/{post['id']}/status", json={"status": "RESERVED"}, headers=seller)

    edited = client.patch(f"/posts/{post['id']}", json={"book_title": "운영체제"}, headers=seller)
    assert edited.status_code == 200
    assert notifications(client, buyer) == []


# ---------- 목록·읽음·정리 ----------


def test_unread_count_and_read_all(client, seller, buyer, add_alert, create_post) -> None:
    add_alert(buyer, "자료구조")
    create_post(seller, book_title="자료구조 1판")
    create_post(seller, book_title="자료구조 2판")
    assert unread(client, buyer) == 2

    assert client.post("/notifications/read-all", headers=buyer).status_code == 204
    assert unread(client, buyer) == 0
    assert all(n["read_at"] is not None for n in notifications(client, buyer))


def test_list_shows_post_summary_newest_first(client, seller, buyer, add_alert, create_post) -> None:
    add_alert(buyer, "자료구조")
    first = create_post(seller, book_title="자료구조 1판", price=1000)
    second = create_post(seller, book_title="자료구조 2판", price=2000)
    items = notifications(client, buyer)
    assert [n["post"]["id"] for n in items] == [second["id"], first["id"]]
    assert items[0]["post"]["price"] == 2000
    assert items[0]["post"]["status"] == "ON_SALE"
    assert items[0]["post"]["thumbnail_url"] is None


def test_notifications_are_private(client, seller, buyer, add_alert, create_post) -> None:
    add_alert(buyer, "자료구조")
    create_post(seller, book_title="자료구조")
    assert notifications(client, seller) == []
    client.post("/notifications/read-all", headers=seller)
    assert unread(client, buyer) == 1


def test_deleting_post_removes_notifications(
    client, db_session: Session, seller, buyer, add_alert, create_post
) -> None:
    add_alert(buyer, "자료구조")
    post = create_post(seller, book_title="자료구조")
    assert client.delete(f"/posts/{post['id']}", headers=seller).status_code == 204
    assert notifications(client, buyer) == []
    assert db_session.scalar(select(func.count()).select_from(AlertNotification)) == 0


def test_deleting_alert_keeps_received_notifications(client, seller, buyer, add_alert, create_post) -> None:
    alert = add_alert(buyer, "자료구조")
    create_post(seller, book_title="자료구조")
    client.delete(f"/users/me/alerts/{alert['id']}", headers=buyer)
    assert [n["keyword"] for n in notifications(client, buyer)] == ["자료구조"]


def test_withdraw_removes_alerts_and_notifications(
    client, db_session: Session, seller, buyer, add_alert, create_post
) -> None:
    add_alert(buyer, "자료구조")
    create_post(seller, book_title="자료구조")
    client.post("/users/me/withdraw", json={"password": TEST_PASSWORD}, headers=buyer)
    assert db_session.scalar(select(func.count()).select_from(BookAlert)) == 0
    assert db_session.scalar(select(func.count()).select_from(AlertNotification)) == 0


def test_notifications_require_login(client: TestClient) -> None:
    assert client.get("/notifications").status_code == 401
    assert client.get("/notifications/unread-count").status_code == 401
    assert client.post("/notifications/read-all").status_code == 401
