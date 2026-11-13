"""쪽지 사진: 보내기 검사(차단·탈퇴·정지·도배·횟수), 비공개 제공(참여자만), 목록 미리보기, 신고 사본·관리자 보기."""

import io
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Message, MessageImage, MessageReportSnapshot, User
from app.services import message_image_service
from app.services.message_image_service import ImageRateLimit
from tests.test_post_images import make_image, make_jpeg_with_gps
from tests.test_suspension import suspend_for


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


@pytest.fixture
def message_dir(tmp_path: Path) -> Path:
    # conftest가 쪽지 사진 폴더를 이 경로로 바꿔 둔다.
    return tmp_path / "uploads" / "messages"


def send_photo(client: TestClient, room_id: int, headers: dict | None, data: bytes | None = None, content: str | None = None):
    form = {"content": content} if content is not None else {}
    return client.post(
        f"/conversations/{room_id}/images",
        files={"file": ("photo.jpg", data or make_image(), "image/jpeg")},
        data=form,
        headers=headers or {},
    )


def test_send_photo_creates_message_and_private_files(client, db_session: Session, buyer, room, message_dir, image_dir) -> None:
    response = send_photo(client, room, buyer)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["has_image"] is True and body["content"] == "" and body["is_mine"] is True
    saved = db_session.scalar(select(MessageImage))
    assert saved.message_id == body["id"]
    assert sorted(p.name for p in message_dir.iterdir()) == sorted([saved.filename, saved.thumb_filename])
    # 판매글 사진 폴더에는 아무것도 없다. → 공개 주소 /images/{name}로 열 수 없다.
    assert not image_dir.exists() or not any(image_dir.iterdir())
    assert client.get(f"/images/{saved.filename}").status_code == 404


def test_photo_with_text_and_gps_removed(client, db_session, buyer, room, message_dir) -> None:
    response = send_photo(client, room, buyer, make_jpeg_with_gps(), content="  책 상태 사진이에요  ")

    assert response.status_code == 201, response.text
    assert response.json()["content"] == "책 상태 사진이에요"
    saved = db_session.scalar(select(MessageImage))
    with Image.open(message_dir / saved.filename) as image:
        assert image.format == "WEBP"
        assert not image.getexif()


def test_participants_can_view_full_and_thumb_with_private_headers(client, buyer, seller, room) -> None:
    message_id = send_photo(client, room, buyer, make_image(size=(1200, 900))).json()["id"]

    full = client.get(f"/messages/{message_id}/image", headers=seller)
    thumb = client.get(f"/messages/{message_id}/image", params={"size": "thumb"}, headers=buyer)

    assert full.status_code == thumb.status_code == 200
    assert full.headers["content-type"] == "image/webp"
    assert full.headers["cache-control"] == "private, no-store"
    assert full.headers["x-content-type-options"] == "nosniff"
    with Image.open(io.BytesIO(thumb.content)) as image:
        assert max(image.size) == 400
    with Image.open(io.BytesIO(full.content)) as image:
        assert max(image.size) == 1200


def test_only_participants_can_view(client, buyer, room, make_auth_headers) -> None:
    message_id = send_photo(client, room, buyer).json()["id"]
    stranger = make_auth_headers("stranger@campus.ac.kr", "제삼자")

    assert client.get(f"/messages/{message_id}/image").status_code == 401
    assert client.get(f"/messages/{message_id}/image", headers=stranger).status_code == 403
    assert client.get("/messages/9999/image", headers=stranger).status_code == 404


def test_text_message_has_no_image(client, buyer, room) -> None:
    message_id = client.post(f"/conversations/{room}/messages", json={"content": "글만"}, headers=buyer).json()["id"]

    response = client.get(f"/messages/{message_id}/image", headers=buyer)

    assert response.status_code == 404
    assert response.json() == {"detail": "사진을 찾을 수 없습니다."}


def test_photo_hidden_after_leaving_is_404_for_leaver_only(client, buyer, seller, room) -> None:
    message_id = send_photo(client, room, seller).json()["id"]
    client.post(f"/conversations/{room}/leave", headers=buyer)

    assert client.get(f"/messages/{message_id}/image", headers=buyer).status_code == 404
    assert client.get(f"/messages/{message_id}/image", headers=seller).status_code == 200


def test_message_list_and_preview_mark_photos(client, buyer, seller, room) -> None:
    client.post(f"/conversations/{room}/messages", json={"content": "안녕하세요"}, headers=buyer)
    send_photo(client, room, buyer)

    items = client.get(f"/conversations/{room}/messages", headers=seller).json()["items"]
    preview = client.get("/conversations", headers=seller).json()["items"][0]["last_message"]

    assert [m["has_image"] for m in items] == [False, True]
    assert preview["has_image"] is True and preview["content"] == ""


def test_blocked_cannot_send_but_can_still_view(client, buyer, seller, room) -> None:
    message_id = send_photo(client, room, buyer).json()["id"]
    seller_id = client.get("/users/me", headers=seller).json()["id"]
    client.post(f"/users/{seller_id}/block", headers=buyer)

    assert send_photo(client, room, buyer).status_code == 400
    assert client.get(f"/messages/{message_id}/image", headers=seller).status_code == 200


def test_cannot_send_to_withdrawn_partner_but_photos_remain(client, db_session, buyer, seller, room, message_dir) -> None:
    message_id = send_photo(client, room, seller).json()["id"]
    client.post("/users/me/withdraw", json={"password": "password123"}, headers=seller)

    assert send_photo(client, room, buyer).status_code == 400
    assert client.get(f"/messages/{message_id}/image", headers=buyer).status_code == 200
    assert len(list(message_dir.iterdir())) == 2


def test_suspended_user_cannot_send_but_can_view(client, db_session, buyer, seller, room) -> None:
    message_id = send_photo(client, room, seller).json()["id"]
    suspend_for(db_session, "buyer@campus.ac.kr", timedelta(days=3))

    assert send_photo(client, room, buyer).status_code == 403
    assert client.get(f"/messages/{message_id}/image", headers=buyer).status_code == 200


def test_photo_rate_limit(client, db_session, buyer, room, monkeypatch) -> None:
    # 쪽지 도배 제한(10초 5건)보다 먼저 걸리도록 사진 제한을 2장으로 줄여 확인한다.
    monkeypatch.setattr(message_image_service, "MESSAGE_IMAGE_RATE_LIMIT", ImageRateLimit(max_images=2, window_seconds=600))

    statuses = [send_photo(client, room, buyer).status_code for _ in range(3)]

    assert statuses == [201, 201, 429]
    assert send_photo(client, room, buyer).headers["retry-after"] == "600"


def test_message_rate_limit_also_applies(client, db_session, buyer, room) -> None:
    for i in range(5):
        client.post(f"/conversations/{room}/messages", json={"content": f"메시지 {i}"}, headers=buyer)

    assert send_photo(client, room, buyer).status_code == 429


def test_invalid_file_and_long_text_are_rejected_without_files(client, db_session, buyer, room, message_dir) -> None:
    assert send_photo(client, room, buyer, b"not an image").status_code == 422
    assert send_photo(client, room, buyer, content="가" * 1001).status_code == 422
    assert db_session.scalar(select(Message)) is None
    assert not message_dir.exists() or not any(message_dir.iterdir())


def test_non_participant_cannot_send(client, room, make_auth_headers) -> None:
    stranger = make_auth_headers("stranger@campus.ac.kr", "제삼자")

    assert send_photo(client, room, stranger).status_code == 403
    assert send_photo(client, room, None).status_code == 401
    assert send_photo(client, 9999, stranger).status_code == 404


def test_report_snapshot_keeps_photo_for_admin(client, db_session, buyer, seller, room, make_admin_headers) -> None:
    message_id = send_photo(client, room, seller, content="이 사진 보세요").json()["id"]
    report = client.post(f"/messages/{message_id}/reports", json={"reason": "ABUSE"}, headers=buyer).json()
    other = send_photo(client, room, seller).json()["id"]

    snapshot = db_session.scalar(select(MessageReportSnapshot))
    image = db_session.scalar(select(MessageImage).where(MessageImage.message_id == message_id))
    assert snapshot.image_filename == image.filename

    admin = make_admin_headers()
    item = client.get("/admin/reports", headers=admin).json()["items"][0]
    assert item["message"]["has_image"] is True
    photo = client.get(f"/admin/reports/{report['id']}/image", headers=admin)
    assert photo.status_code == 200 and photo.headers["cache-control"] == "private, no-store"
    # 관리자도 대화 참여자가 아니므로 신고되지 않은 사진은 볼 수 없다.
    assert client.get(f"/messages/{other}/image", headers=admin).status_code == 403
    # 일반 사용자는 관리자 경로로 볼 수 없다.
    assert client.get(f"/admin/reports/{report['id']}/image", headers=buyer).status_code == 403


def test_admin_image_for_text_report_is_404(client, buyer, seller, room, make_admin_headers) -> None:
    message_id = client.post(f"/conversations/{room}/messages", json={"content": "글만"}, headers=seller).json()["id"]
    report = client.post(f"/messages/{message_id}/reports", json={"reason": "ABUSE"}, headers=buyer).json()

    assert client.get(f"/admin/reports/{report['id']}/image", headers=make_admin_headers()).status_code == 404


def test_db_failure_removes_written_files(client, db_session, buyer, room, message_dir, monkeypatch) -> None:
    from app.services import conversation_service

    def broken(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(conversation_service, "append_message", broken)
    with pytest.raises(RuntimeError):
        send_photo(client, room, buyer)

    assert not any(message_dir.iterdir())
    assert db_session.scalar(select(User).where(User.email == "buyer@campus.ac.kr")) is not None
