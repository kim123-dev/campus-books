"""이용 정지: 로그인 403, 이미 받은 토큰의 쓰기 403, 읽기·차단은 허용, 기간이 지나면 자동 해제."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.services import user_service
from tests.conftest import TEST_PASSWORD
from tests.test_post_images import make_image

SELLER = "seller@campus.ac.kr"
BUYER = "buyer@campus.ac.kr"


@pytest.fixture
def seller(make_auth_headers) -> dict:
    return make_auth_headers(SELLER, "판매자")


@pytest.fixture
def buyer(make_auth_headers) -> dict:
    return make_auth_headers(BUYER, "구매자")


@pytest.fixture
def other_post(make_auth_headers, create_post) -> dict:
    """정지된 사람이 남의 글에 찜·문의·신고를 하는 경우를 보기 위한 다른 사람의 글."""
    return create_post(make_auth_headers("other@campus.ac.kr", "다른사람"), title="다른 사람 글")


def set_suspension(db: Session, email: str, end: datetime | None) -> None:
    """정지 종료 시각을 직접 넣는다. DB에는 시간대 없이 UTC로 저장한다. (user_service.suspend와 같은 방식)"""
    user = db.scalar(select(User).where(User.email == email))
    user.suspended_until = end.astimezone(UTC).replace(tzinfo=None) if end is not None else None
    db.commit()


def suspend_for(db: Session, email: str, delta: timedelta) -> None:
    set_suspension(db, email, user_service.utc_now() + delta)


def login(client: TestClient, email: str, password: str = TEST_PASSWORD):
    return client.post("/auth/login", data={"username": email, "password": password})


# ---------- 로그인 ----------


def test_suspended_user_login_returns_403_with_end_time(client, db_session, seller) -> None:
    # 한국 시간 2099년 11월 16일 14:00 = UTC 05:00. 해가 다르므로 연도가 붙는다.
    set_suspension(db_session, SELLER, datetime(2099, 11, 16, 5, 0, tzinfo=UTC))

    response = login(client, SELLER)

    assert response.status_code == 403
    assert response.json()["detail"] == "2099년 11월 16일 14:00까지 이용이 정지되었습니다."
    assert "access_token" not in response.json()


def test_wrong_password_does_not_reveal_suspension(client, db_session, seller) -> None:
    # 비밀번호를 모르는 사람은 정지 사실을 알 수 없고, 평소와 같은 401을 받는다.
    suspend_for(db_session, SELLER, timedelta(days=3))

    response = login(client, SELLER, "wrong-password")

    assert response.status_code == 401
    assert "정지" not in response.json()["detail"]


def test_login_works_again_after_suspension_ends(client, db_session, seller) -> None:
    suspend_for(db_session, SELLER, timedelta(seconds=-1))

    response = login(client, SELLER)

    assert response.status_code == 200
    assert "access_token" in response.json()


# ---------- 정지 안내 문구 ----------


def test_message_uses_korea_time_without_year_in_same_year() -> None:
    now = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
    end = datetime(2026, 11, 16, 15, 30, tzinfo=UTC)  # 한국 시간 11월 17일 00:30

    assert user_service.suspension_message(end, now) == "11월 17일 00:30까지 이용이 정지되었습니다."


def test_message_adds_year_when_year_changes_in_korea_time() -> None:
    now = datetime(2026, 12, 25, 0, 0, tzinfo=UTC)
    end = datetime(2026, 12, 31, 16, 0, tzinfo=UTC)  # 한국 시간으로는 이미 2027년 1월 1일

    assert user_service.suspension_message(end, now) == "2027년 1월 1일 01:00까지 이용이 정지되었습니다."


# ---------- 쓰기는 403 (정지 전에 받은 토큰으로도) ----------


def write_requests(post_id: int, other_post_id: int, buyer_id: int) -> list[tuple[str, str, dict]]:
    """정지 중에 막히는 쓰기 요청. (메서드, 경로, 요청 옵션)"""
    return [
        ("POST", "/posts", {"json": {"title": "x"}}),
        ("PATCH", f"/posts/{post_id}", {"json": {"price": 1000}}),
        ("PATCH", f"/posts/{post_id}/status", {"json": {"status": "RESERVED"}}),
        ("DELETE", f"/posts/{post_id}", {}),
        ("POST", f"/posts/{post_id}/images", {"files": {"file": ("a.png", make_image("PNG"), "image/png")}}),
        ("DELETE", f"/posts/{post_id}/images/1", {}),
        ("POST", f"/posts/{other_post_id}/wishlist", {}),
        ("DELETE", f"/posts/{other_post_id}/wishlist", {}),
        ("POST", f"/posts/{other_post_id}/conversations", {}),
        ("POST", "/conversations/1/messages", {"json": {"content": "안녕하세요"}}),
        ("POST", f"/posts/{other_post_id}/reports", {"json": {"reason": "FRAUD"}}),
        ("POST", f"/users/{buyer_id}/reports", {"json": {"reason": "ABUSE"}}),
    ]


def test_all_write_requests_return_403_with_old_token(
    client, db_session, seller, buyer, create_post, other_post
) -> None:
    post = create_post(seller)
    buyer_id = client.get("/users/me", headers=buyer).json()["id"]
    suspend_for(db_session, SELLER, timedelta(days=7))

    for method, path, options in write_requests(post["id"], other_post["id"], buyer_id):
        response = client.request(method, path, headers=seller, **options)
        assert response.status_code == 403, (method, path, response.text)
        assert response.json()["detail"].endswith("까지 이용이 정지되었습니다."), (method, path)


def test_suspension_check_comes_before_validation(client, db_session, seller) -> None:
    # 빈 본문(422 대상)이어도 정지 안내가 먼저 나온다. 고쳐서 다시 보내도 어차피 막히기 때문이다.
    suspend_for(db_session, SELLER, timedelta(days=1))

    response = client.post("/posts", json={}, headers=seller)

    assert response.status_code == 403


def test_nothing_changes_when_suspended(client, db_session, seller, create_post) -> None:
    post = create_post(seller, price=15000)
    suspend_for(db_session, SELLER, timedelta(days=1))

    client.patch(f"/posts/{post['id']}", json={"price": 1000}, headers=seller)
    client.delete(f"/posts/{post['id']}", headers=seller)

    assert client.get(f"/posts/{post['id']}").json()["price"] == 15000


def test_message_send_in_existing_conversation_returns_403(client, db_session, seller, buyer, create_post) -> None:
    post = create_post(seller)
    conversation = client.post(f"/posts/{post['id']}/conversations", headers=buyer).json()
    suspend_for(db_session, BUYER, timedelta(days=1))

    response = client.post(
        f"/conversations/{conversation['id']}/messages", json={"content": "아직 있나요?"}, headers=buyer
    )

    assert response.status_code == 403
    # 대화 내용은 계속 볼 수 있다.
    assert client.get(f"/conversations/{conversation['id']}/messages", headers=buyer).status_code == 200


# ---------- 읽기와 차단은 허용 ----------


def test_reads_are_allowed_when_suspended(client, db_session, seller, create_post) -> None:
    post = create_post(seller)
    suspend_for(db_session, SELLER, timedelta(days=1))

    for path in [
        "/posts",
        f"/posts/{post['id']}",
        "/users/me/posts",
        "/users/me/wishlist",
        "/users/me/blocks",
        "/conversations",
        "/conversations/unread-count",
    ]:
        assert client.get(path, headers=seller).status_code == 200, path


def test_me_shows_suspension_end(client, db_session, seller) -> None:
    suspend_for(db_session, SELLER, timedelta(days=3))

    body = client.get("/users/me", headers=seller).json()

    assert body["suspended_until"] is not None
    end = datetime.fromisoformat(body["suspended_until"].replace("Z", "+00:00"))
    assert timedelta(days=2) < user_service.as_utc(end) - user_service.utc_now() <= timedelta(days=3)


def test_block_and_unblock_are_allowed_when_suspended(client, db_session, seller, buyer) -> None:
    # 정지된 사람도 원치 않는 연락은 막을 수 있어야 한다.
    buyer_id = client.get("/users/me", headers=buyer).json()["id"]
    suspend_for(db_session, SELLER, timedelta(days=1))

    assert client.post(f"/users/{buyer_id}/block", headers=seller).status_code == 201
    assert client.delete(f"/users/{buyer_id}/block", headers=seller).status_code == 204


# ---------- 자동 해제 ----------


def test_suspension_ends_automatically(client, db_session, seller, create_post) -> None:
    post = create_post(seller)
    suspend_for(db_session, SELLER, timedelta(days=1))
    assert client.patch(f"/posts/{post['id']}", json={"price": 1000}, headers=seller).status_code == 403

    # 종료 시각이 지나면 따로 풀어 주지 않아도 같은 토큰으로 바로 쓸 수 있다.
    suspend_for(db_session, SELLER, timedelta(seconds=-1))

    assert client.patch(f"/posts/{post['id']}", json={"price": 1000}, headers=seller).status_code == 200
    me = client.get("/users/me", headers=seller).json()
    assert me["suspended_until"] is None  # 지난 정지는 null로 보여준다


def test_active_suspension_end_boundary() -> None:
    now = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    user = User(email="x@campus.ac.kr", password_hash="x", nickname="x")

    user.suspended_until = None
    assert user_service.active_suspension_end(user, now) is None
    user.suspended_until = now.replace(tzinfo=None)  # 끝나는 바로 그 시각에는 이미 풀린 것으로 본다
    assert user_service.active_suspension_end(user, now) is None
    user.suspended_until = (now + timedelta(seconds=1)).replace(tzinfo=None)
    assert user_service.active_suspension_end(user, now) == now + timedelta(seconds=1)


def test_suspend_from_expired_starts_fresh() -> None:
    # 지난 정지는 남은 기간으로 치지 않는다. 새 정지는 지금부터 센다.
    now = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    user = User(email="x@campus.ac.kr", password_hash="x", nickname="x")
    user.suspended_until = (now - timedelta(days=10)).replace(tzinfo=None)

    end = user_service.suspend(user, 3, now)

    assert end == now + timedelta(days=3)
