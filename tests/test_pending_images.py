"""임시 사진(POST·DELETE /pending-images)과 글 작성·수정에서 임시 사진을 붙이는 흐름."""

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import PendingImage, Post, PostImage
from app.services import alert_service, image_service, pending_image_service
from tests.conftest import TEST_PASSWORD
from tests.test_post_images import make_image, make_jpeg_with_gps, stored_files, upload


def upload_pending(client, headers: dict, data: bytes | None = None):
    return client.post(
        "/pending-images", headers=headers, files={"file": ("book.jpg", data or make_image(), "image/jpeg")}
    )


def pending_id(client, headers: dict) -> int:
    response = upload_pending(client, headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def owner(make_auth_headers) -> dict:
    return make_auth_headers("owner@campus.ac.kr", "작성자")


@pytest.fixture
def other(make_auth_headers) -> dict:
    return make_auth_headers("other@campus.ac.kr", "다른사람")


@pytest.fixture
def pending_dir(image_dir: Path) -> Path:
    return image_dir.parent / "pending"


def pending_rows(db_session: Session) -> list[PendingImage]:
    db_session.expire_all()
    return list(db_session.scalars(select(PendingImage).order_by(PendingImage.id)))


# ---------- 올리기 ----------


def test_upload_returns_only_id_and_stores_files_outside_public_folder(
    client, owner, image_dir, pending_dir, db_session
) -> None:
    response = upload_pending(client, owner)

    assert response.status_code == 201, response.text
    assert set(response.json()) == {"id"}
    files = stored_files(pending_dir)
    assert len(files) == 2  # 상세용 + 썸네일
    assert stored_files(image_dir) == []
    # 글에 붙기 전에는 파일 이름을 알아도 공개 주소로 열 수 없다.
    assert all(client.get(f"/images/{name}").status_code == 404 for name in files)


def test_upload_requires_login(client, pending_dir) -> None:
    response = client.post("/pending-images", files={"file": ("a.jpg", make_image(), "image/jpeg")})

    assert response.status_code == 401
    assert stored_files(pending_dir) == []


def test_upload_rejects_broken_file_without_leaving_files(client, owner, pending_dir, db_session) -> None:
    response = upload_pending(client, owner, b"not an image")

    assert response.status_code == 422
    assert stored_files(pending_dir) == []
    assert pending_rows(db_session) == []


def test_upload_over_25mb_is_rejected_before_reading_body(client, owner) -> None:
    response = client.post(
        "/pending-images",
        headers={**owner, "Content-Length": str(image_service.MAX_IMAGE_BYTES + 1024 * 1024)},
        files={"file": ("a.jpg", make_image(), "image/jpeg")},
    )

    assert response.status_code == 413


def test_upload_removes_gps_metadata(client, owner, pending_dir) -> None:
    from PIL import Image

    assert upload_pending(client, owner, make_jpeg_with_gps()).status_code == 201

    for path in pending_dir.glob("*"):
        with Image.open(path) as image:
            assert not image.getexif()


def test_rate_limit_counts_pending_and_attached_images_together(client, owner, create_post, monkeypatch) -> None:
    monkeypatch.setattr(
        image_service, "IMAGE_UPLOAD_RATE_LIMIT", image_service.UploadRateLimit(max_uploads=2, window_seconds=600)
    )
    create_post(owner, image_ids=[pending_id(client, owner)])  # 글에 붙은 사진 1장
    assert upload_pending(client, owner).status_code == 201  # 임시 사진 1장

    response = upload_pending(client, owner)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "600"
    # 기존 업로드 API도 임시 사진을 함께 센다.
    assert upload(client, create_post(owner)["id"], owner, make_image()).status_code == 429


def test_only_newest_pending_images_are_kept_per_user(client, owner, pending_dir, db_session) -> None:
    ids = [pending_id(client, owner) for _ in range(pending_image_service.MAX_PENDING_PER_USER + 1)]

    rows = pending_rows(db_session)

    assert [row.id for row in rows] == ids[1:]  # 가장 오래된 한 장이 지워진다.
    assert len(stored_files(pending_dir)) == 2 * pending_image_service.MAX_PENDING_PER_USER


def test_expired_pending_images_are_purged_on_next_upload(client, owner, other, pending_dir, db_session) -> None:
    old = pending_id(client, owner)
    fresh = pending_id(client, owner)
    created = db_session.scalar(select(PendingImage.created_at).where(PendingImage.id == old))
    db_session.execute(
        update(PendingImage)
        .where(PendingImage.id == old)
        .values(created_at=created - pending_image_service.PENDING_TTL - timedelta(minutes=1))
    )
    db_session.commit()

    newest = pending_id(client, other)  # 누가 올리든 오래된 임시 사진을 함께 치운다.

    assert [row.id for row in pending_rows(db_session)] == [fresh, newest]
    assert len(stored_files(pending_dir)) == 4


# ---------- 지우기 ----------


def test_delete_removes_row_and_files(client, owner, pending_dir, db_session) -> None:
    image_id = pending_id(client, owner)

    response = client.delete(f"/pending-images/{image_id}", headers=owner)

    assert response.status_code == 204
    assert pending_rows(db_session) == []
    assert stored_files(pending_dir) == []
    assert client.delete(f"/pending-images/{image_id}", headers=owner).status_code == 404


def test_delete_of_someone_elses_pending_image_is_404(client, owner, other, pending_dir) -> None:
    image_id = pending_id(client, owner)

    assert client.delete(f"/pending-images/{image_id}", headers=other).status_code == 404
    assert client.delete(f"/pending-images/{image_id}").status_code == 401
    assert len(stored_files(pending_dir)) == 2


# ---------- 글 작성에 붙이기 ----------


def test_create_post_attaches_pending_images_in_order(
    client, owner, post_payload, image_dir, pending_dir, db_session
) -> None:
    first, second = pending_id(client, owner), pending_id(client, owner)
    names = {row.id: row.filename for row in pending_rows(db_session)}

    response = client.post("/posts", json={**post_payload, "image_ids": [second, first]}, headers=owner)

    assert response.status_code == 201, response.text
    body = response.json()
    assert [image["url"] for image in body["images"]] == [f"/images/{names[second]}", f"/images/{names[first]}"]
    assert body["thumbnail_url"] == body["images"][0]["thumbnail_url"]
    # 파일은 공개 폴더로 옮겨지고 임시 사진은 남지 않는다.
    assert stored_files(pending_dir) == [] and len(stored_files(image_dir)) == 4
    assert pending_rows(db_session) == []
    assert all(client.get(image["url"]).status_code == 200 for image in body["images"])
    assert client.get(f"/posts/{body['id']}").json()["images"] == body["images"]


def test_create_post_without_image_ids_still_works(client, owner, create_post) -> None:
    assert create_post(owner)["images"] == []
    assert create_post(owner, image_ids=[])["images"] == []


@pytest.mark.parametrize("image_ids", [[1, 2, 3, 4], [1, 1], ["1"], [0], [1.5], None, "1"])
def test_create_post_rejects_malformed_image_ids(client, owner, post_payload, image_ids) -> None:
    response = client.post("/posts", json={**post_payload, "image_ids": image_ids}, headers=owner)

    assert response.status_code == 422


def test_create_post_with_missing_pending_image_is_400_and_saves_nothing(
    client, owner, post_payload, pending_dir, image_dir, db_session
) -> None:
    kept = pending_id(client, owner)

    response = client.post("/posts", json={**post_payload, "image_ids": [kept, 9999]}, headers=owner)

    assert response.status_code == 400
    assert "다시 골라" in response.json()["detail"]
    assert db_session.scalars(select(Post)).all() == []
    # 함께 보낸 멀쩡한 임시 사진은 그대로 남아 다시 시도할 수 있다.
    assert [row.id for row in pending_rows(db_session)] == [kept]
    assert len(stored_files(pending_dir)) == 2 and stored_files(image_dir) == []


def test_create_post_cannot_use_someone_elses_pending_image(
    client, owner, other, post_payload, pending_dir, db_session
) -> None:
    theirs = pending_id(client, other)

    response = client.post("/posts", json={**post_payload, "image_ids": [theirs]}, headers=owner)

    assert response.status_code == 400
    assert [row.id for row in pending_rows(db_session)] == [theirs]
    assert len(stored_files(pending_dir)) == 2


def test_pending_image_can_be_attached_only_once(client, owner, create_post, post_payload) -> None:
    image_id = pending_id(client, owner)
    create_post(owner, image_ids=[image_id])

    response = client.post("/posts", json={**post_payload, "image_ids": [image_id]}, headers=owner)

    assert response.status_code == 400


def test_files_return_to_pending_folder_when_saving_the_post_fails(
    client, owner, post_payload, pending_dir, image_dir, db_session, monkeypatch
) -> None:
    image_id = pending_id(client, owner)

    def fail(*args, **kwargs):
        raise RuntimeError("DB 오류 흉내")

    # context: 이 블록의 바꿔 끼우기만 되돌린다. (undo는 conftest가 바꿔 둔 사진 폴더까지 되돌린다)
    with monkeypatch.context() as patch:
        patch.setattr(alert_service, "notify_matching", fail)
        with pytest.raises(RuntimeError):
            client.post("/posts", json={**post_payload, "image_ids": [image_id]}, headers=owner)

    assert db_session.scalars(select(Post)).all() == []
    assert len(stored_files(pending_dir)) == 2 and stored_files(image_dir) == []
    # 같은 번호로 다시 시도하면 성공한다.
    retry = client.post("/posts", json={**post_payload, "image_ids": [image_id]}, headers=owner)
    assert retry.status_code == 201 and len(retry.json()["images"]) == 1


def test_matching_alert_is_sent_with_photo_already_attached(client, owner, other, post_payload) -> None:
    assert client.post("/users/me/alerts", json={"keyword": "자료구조"}, headers=other).status_code == 201

    post = client.post("/posts", json={**post_payload, "image_ids": [pending_id(client, owner)]}, headers=owner).json()

    notifications = client.get("/notifications", headers=other).json()
    assert notifications["items"][0]["post"]["thumbnail_url"] == post["thumbnail_url"]


# ---------- 글 수정에서 붙이기·지우기 ----------


@pytest.fixture
def post_with_three(client, owner, create_post) -> dict:
    return create_post(owner, image_ids=[pending_id(client, owner) for _ in range(3)])


def test_update_adds_pending_images_after_existing_ones(client, owner, create_post, pending_dir) -> None:
    post = create_post(owner, image_ids=[pending_id(client, owner)])

    response = client.patch(
        f"/posts/{post['id']}", json={"add_image_ids": [pending_id(client, owner)]}, headers=owner
    )

    assert response.status_code == 200, response.text
    images = response.json()["images"]
    assert len(images) == 2 and images[0] == post["images"][0]
    assert stored_files(pending_dir) == []


def test_update_can_swap_one_of_three_images_in_one_request(
    client, owner, post_with_three, image_dir, db_session
) -> None:
    removed = post_with_three["images"][1]
    new_id = pending_id(client, owner)

    response = client.patch(
        f"/posts/{post_with_three['id']}",
        json={"title": "새 제목", "remove_image_ids": [removed["id"]], "add_image_ids": [new_id]},
        headers=owner,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "새 제목"
    assert len(body["images"]) == 3 and removed["id"] not in [image["id"] for image in body["images"]]
    # 지운 사진의 파일은 사라지고, 새 사진은 지운 칸에 들어간다.
    assert client.get(removed["url"]).status_code == 404
    assert len(stored_files(image_dir)) == 6
    slots = db_session.scalars(select(PostImage.slot).order_by(PostImage.slot)).all()
    assert slots == [0, 1, 2]


def test_update_only_removing_images(client, owner, post_with_three, image_dir) -> None:
    ids = [image["id"] for image in post_with_three["images"]]

    response = client.patch(f"/posts/{post_with_three['id']}", json={"remove_image_ids": ids[:2]}, headers=owner)

    assert [image["id"] for image in response.json()["images"]] == ids[2:]
    assert response.json()["thumbnail_url"] == post_with_three["images"][2]["thumbnail_url"]
    assert len(stored_files(image_dir)) == 2


def test_update_over_three_images_is_400_and_changes_nothing(
    client, owner, post_with_three, pending_dir, image_dir
) -> None:
    extra = pending_id(client, owner)

    response = client.patch(
        f"/posts/{post_with_three['id']}", json={"title": "바뀌면 안 됨", "add_image_ids": [extra]}, headers=owner
    )

    assert response.status_code == 400
    after = client.get(f"/posts/{post_with_three['id']}").json()
    assert after["title"] == post_with_three["title"] and after["images"] == post_with_three["images"]
    assert len(stored_files(pending_dir)) == 2 and len(stored_files(image_dir)) == 6


def test_update_removing_image_of_another_post_is_404_and_changes_nothing(
    client, owner, create_post, post_with_three, image_dir
) -> None:
    mine = create_post(owner, image_ids=[pending_id(client, owner)])

    response = client.patch(
        f"/posts/{mine['id']}",
        json={"remove_image_ids": [mine["images"][0]["id"], post_with_three["images"][0]["id"]]},
        headers=owner,
    )

    assert response.status_code == 404
    assert client.get(f"/posts/{mine['id']}").json()["images"] == mine["images"]
    assert len(stored_files(image_dir)) == 8


def test_update_with_missing_pending_image_keeps_removed_images(client, owner, post_with_three, image_dir) -> None:
    response = client.patch(
        f"/posts/{post_with_three['id']}",
        json={"remove_image_ids": [post_with_three["images"][0]["id"]], "add_image_ids": [9999]},
        headers=owner,
    )

    assert response.status_code == 400
    assert client.get(f"/posts/{post_with_three['id']}").json()["images"] == post_with_three["images"]
    assert len(stored_files(image_dir)) == 6


def test_update_without_image_fields_leaves_images_untouched(client, owner, post_with_three) -> None:
    response = client.patch(f"/posts/{post_with_three['id']}", json={"price": 9000}, headers=owner)

    assert response.json()["images"] == post_with_three["images"]


def test_other_user_cannot_attach_images_to_my_post(client, owner, other, create_post, pending_dir) -> None:
    post = create_post(owner)

    response = client.patch(
        f"/posts/{post['id']}", json={"add_image_ids": [pending_id(client, other)]}, headers=other
    )

    assert response.status_code == 403
    assert len(stored_files(pending_dir)) == 2


def test_sold_post_cannot_change_images(client, owner, post_with_three) -> None:
    client.patch(f"/posts/{post_with_three['id']}/status", json={"status": "SOLD"}, headers=owner)

    response = client.patch(
        f"/posts/{post_with_three['id']}",
        json={"remove_image_ids": [post_with_three["images"][0]["id"]]},
        headers=owner,
    )

    assert response.status_code == 400


# ---------- 탈퇴 ----------


def test_withdraw_deletes_pending_images(client, owner, pending_dir, db_session) -> None:
    pending_id(client, owner)

    response = client.post("/users/me/withdraw", json={"password": TEST_PASSWORD}, headers=owner)

    assert response.status_code == 204, response.text
    assert pending_rows(db_session) == []
    assert stored_files(pending_dir) == []
