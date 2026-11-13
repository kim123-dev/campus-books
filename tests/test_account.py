"""비밀번호 변경(PUT /users/me/password)과 회원 탈퇴(POST /users/me/withdraw)."""

import io
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Report, UserBlock, Wishlist
from tests.conftest import SECURITY_QUESTION, TEST_PASSWORD

NEW_PASSWORD = "newpassword456"


def login(client: TestClient, email: str, password: str):
    return client.post("/auth/login", data={"username": email, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), (200, 80, 40)).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def seller(make_auth_headers: Callable[..., dict[str, str]]) -> dict[str, str]:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def buyer(make_auth_headers: Callable[..., dict[str, str]]) -> dict[str, str]:
    return make_auth_headers("buyer@campus.ac.kr", "구매자")


# ---------- 비밀번호 변경 ----------


def test_change_password_with_wrong_current_returns_400(client: TestClient, seller: dict) -> None:
    response = client.put(
        "/users/me/password",
        json={"current_password": "wrong-password", "new_password": NEW_PASSWORD},
        headers=seller,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "현재 비밀번호가 올바르지 않습니다."
    # 틀렸으면 아무것도 바뀌지 않는다.
    assert login(client, "seller@campus.ac.kr", TEST_PASSWORD).status_code == 200


def test_change_password_then_login_with_new_password(client: TestClient, seller: dict) -> None:
    response = client.put(
        "/users/me/password",
        json={"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD},
        headers=seller,
    )
    assert response.status_code == 200
    new_token = response.json()["access_token"]

    assert login(client, "seller@campus.ac.kr", TEST_PASSWORD).status_code == 401
    assert login(client, "seller@campus.ac.kr", NEW_PASSWORD).status_code == 200
    # 변경 전 토큰은 무효, 응답으로 받은 새 토큰은 그대로 쓸 수 있다.
    assert client.get("/users/me", headers=seller).status_code == 401
    assert client.get("/users/me", headers=bearer(new_token)).status_code == 200


def test_change_password_uses_signup_rules(client: TestClient, seller: dict) -> None:
    response = client.put(
        "/users/me/password",
        json={"current_password": TEST_PASSWORD, "new_password": "short"},
        headers=seller,
    )
    assert response.status_code == 422


# ---------- 회원 탈퇴 ----------


def test_withdraw_with_wrong_password_returns_400(client: TestClient, seller: dict) -> None:
    response = client.post("/users/me/withdraw", json={"password": "wrong-password"}, headers=seller)
    assert response.status_code == 400
    assert client.get("/users/me", headers=seller).status_code == 200


def test_withdraw_then_login_returns_401(client: TestClient, seller: dict) -> None:
    response = client.post("/users/me/withdraw", json={"password": TEST_PASSWORD}, headers=seller)
    assert response.status_code == 204

    assert login(client, "seller@campus.ac.kr", TEST_PASSWORD).status_code == 401
    assert client.get("/users/me", headers=seller).status_code == 401


def test_admin_cannot_withdraw(client: TestClient, make_admin_headers: Callable[..., dict[str, str]]) -> None:
    admin = make_admin_headers()
    response = client.post("/users/me/withdraw", json={"password": TEST_PASSWORD}, headers=admin)
    assert response.status_code == 400
    assert response.json()["detail"] == "관리자 계정은 탈퇴할 수 없습니다."


def test_withdraw_deletes_posts_and_image_files(
    client: TestClient, seller: dict, create_post: Callable[..., dict], image_dir: Path
) -> None:
    post = create_post(seller)
    upload = client.post(
        f"/posts/{post['id']}/images",
        headers=seller,
        files={"file": ("book.jpg", jpeg(), "image/jpeg")},
    )
    assert upload.status_code == 201, upload.text
    assert len(list(image_dir.glob("*"))) == 2  # 원본 + 썸네일

    client.post("/users/me/withdraw", json={"password": TEST_PASSWORD}, headers=seller)

    assert list(image_dir.glob("*")) == []
    assert client.get(f"/posts/{post['id']}").status_code == 404


def test_withdraw_keeps_conversation_and_shows_withdrawn_partner(
    client: TestClient, seller: dict, buyer: dict, create_post: Callable[..., dict]
) -> None:
    post = create_post(seller)
    conversation_id = client.post(f"/posts/{post['id']}/conversations", headers=buyer).json()["id"]
    client.post(f"/conversations/{conversation_id}/messages", json={"content": "구매 가능할까요?"}, headers=buyer)
    client.post(f"/conversations/{conversation_id}/messages", json={"content": "네 가능해요"}, headers=seller)

    client.post("/users/me/withdraw", json={"password": TEST_PASSWORD}, headers=seller)

    detail = client.get(f"/conversations/{conversation_id}", headers=buyer).json()
    assert detail["partner"]["nickname"] == "탈퇴한 사용자"
    assert detail["partner"]["withdrawn"] is True
    assert detail["post"] is None  # 글은 지워졌다.
    assert detail["can_send"] is False
    listed = client.get("/conversations", headers=buyer).json()["items"]
    assert listed[0]["partner"]["nickname"] == "탈퇴한 사용자"
    # 대화 기록은 남는다.
    messages = client.get(f"/conversations/{conversation_id}/messages", headers=buyer).json()["items"]
    assert [m["content"] for m in messages] == ["구매 가능할까요?", "네 가능해요"]
    # 탈퇴한 상대에게는 보낼 수 없다.
    sent = client.post(f"/conversations/{conversation_id}/messages", json={"content": "안녕하세요"}, headers=buyer)
    assert sent.status_code == 400


def test_withdraw_cleans_wishlist_blocks_and_keeps_reports(
    client: TestClient,
    db_session: Session,
    seller: dict,
    buyer: dict,
    create_post: Callable[..., dict],
) -> None:
    post = create_post(seller)
    seller_id = client.get("/users/me", headers=seller).json()["id"]
    buyer_id = client.get("/users/me", headers=buyer).json()["id"]
    assert client.post(f"/posts/{post['id']}/wishlist", headers=buyer).status_code in (200, 201)
    assert client.post(f"/users/{seller_id}/block", headers=buyer).status_code in (200, 201)
    report = client.post(f"/users/{seller_id}/reports", json={"reason": "SPAM"}, headers=buyer)
    assert report.status_code == 201, report.text

    client.post("/users/me/withdraw", json={"password": TEST_PASSWORD}, headers=buyer)

    assert db_session.scalars(select(Wishlist)).all() == []
    assert db_session.scalars(select(UserBlock)).all() == []
    kept = db_session.scalars(select(Report)).all()
    assert len(kept) == 1 and kept[0].reporter_id is None and kept[0].reported_user_id == seller_id
    # 탈퇴한 사용자는 없는 사람으로 본다. (차단·신고 대상 404)
    assert client.post(f"/users/{buyer_id}/block", headers=seller).status_code == 404


def test_can_sign_up_again_with_same_email_after_withdraw(client: TestClient, seller: dict) -> None:
    client.post("/users/me/withdraw", json={"password": TEST_PASSWORD}, headers=seller)
    again = client.post(
        "/auth/signup",
        json={"email": "seller@campus.ac.kr", "password": TEST_PASSWORD, "nickname": "판매자", "security_question": SECURITY_QUESTION},
    )
    assert again.status_code == 201
