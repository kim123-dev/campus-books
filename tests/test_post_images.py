import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models import PostImage
from app.services import image_service
from tests.conftest import test_engine

# ---------- 테스트용 사진 만들기 ----------


def make_image(fmt: str = "JPEG", size: tuple[int, int] = (800, 600), mode: str = "RGB", **save_args) -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size, (200, 80, 40) if mode == "RGB" else None).save(buffer, format=fmt, **save_args)
    return buffer.getvalue()


def make_jpeg_with_gps() -> bytes:
    """GPS 위치가 담긴 휴대폰 사진을 흉내 낸다."""
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make (기기 제조사)
    gps = exif.get_ifd(0x8825)  # GPSInfo
    gps[1] = "N"
    gps[2] = (37.0, 33.0, 59.0)  # 위도
    gps[3] = "E"
    gps[4] = (126.0, 58.0, 41.0)  # 경도
    return make_image("JPEG", exif=exif.tobytes())


def upload(client: TestClient, post_id: int, headers: dict, data: bytes, filename: str = "book.jpg",
           content_type: str = "image/jpeg"):
    return client.post(
        f"/posts/{post_id}/images", headers=headers, files={"file": (filename, data, content_type)}
    )


@pytest.fixture
def owner(make_auth_headers) -> dict:
    return make_auth_headers("owner@campus.ac.kr", "작성자")


@pytest.fixture
def other(make_auth_headers) -> dict:
    return make_auth_headers("other@campus.ac.kr", "다른사람")


@pytest.fixture
def post(owner: dict, create_post) -> dict:
    return create_post(owner)


def stored_files(image_dir: Path) -> list[str]:
    return sorted(p.name for p in image_dir.glob("*")) if image_dir.exists() else []


# ---------- 정상 업로드 ----------


@pytest.mark.parametrize(
    "fmt, filename, content_type",
    [("JPEG", "a.jpg", "image/jpeg"), ("PNG", "a.png", "image/png"), ("WEBP", "a.webp", "image/webp")],
)
def test_upload_accepts_jpeg_png_webp(client, owner, post, image_dir, fmt, filename, content_type) -> None:
    response = upload(client, post["id"], owner, make_image(fmt), filename, content_type)

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"id", "url", "thumbnail_url"}
    assert body["url"].startswith("/images/") and body["url"].endswith(".webp")
    assert body["thumbnail_url"].endswith("_thumb.webp")
    assert len(stored_files(image_dir)) == 2  # 상세용 + 썸네일


def test_uploaded_files_are_reencoded_webp_with_resized_thumbnail(client, owner, post, image_dir) -> None:
    body = upload(client, post["id"], owner, make_image("PNG", size=(3000, 1500))).json()

    main = Image.open(image_dir / body["url"].removeprefix("/images/"))
    thumb = Image.open(image_dir / body["thumbnail_url"].removeprefix("/images/"))
    assert main.format == "WEBP" and thumb.format == "WEBP"
    assert main.size == (image_service.MAX_SIDE, 800)  # 긴 변 1600으로 줄고 비율 유지
    assert max(thumb.size) == image_service.THUMB_SIDE


def test_server_generates_filename_ignoring_client_filename(client, owner, post, image_dir) -> None:
    body = upload(client, post["id"], owner, make_image(), filename="../../evil name.jpg").json()

    name = body["url"].removeprefix("/images/")
    assert "evil" not in name and ".." not in name
    assert len(name) == len("0" * 32 + ".webp")
    assert all("evil" not in f for f in stored_files(image_dir))


def test_png_named_jpg_is_accepted_by_content(client, owner, post) -> None:
    # 확장자·Content-Type이 아니라 실제 내용으로 판단한다.
    response = upload(client, post["id"], owner, make_image("PNG"), "photo.jpg", "image/jpeg")

    assert response.status_code == 201


def test_transparent_png_keeps_alpha(client, owner, post, image_dir) -> None:
    body = upload(client, post["id"], owner, make_image("PNG", mode="RGBA"), "a.png", "image/png").json()

    assert Image.open(image_dir / body["url"].removeprefix("/images/")).mode == "RGBA"


def test_gps_and_exif_are_removed(client, owner, post, image_dir) -> None:
    original = make_jpeg_with_gps()
    assert Image.open(io.BytesIO(original)).getexif().get_ifd(0x8825)  # 원본에는 GPS가 있다.

    body = upload(client, post["id"], owner, original).json()

    for url in (body["url"], body["thumbnail_url"]):
        saved = Image.open(image_dir / url.removeprefix("/images/"))
        assert not saved.getexif()  # EXIF 자체가 없다 (GPS·기기 정보 포함)
        assert "exif" not in saved.info and "xmp" not in saved.info
        assert b"PhoneMaker" not in (image_dir / url.removeprefix("/images/")).read_bytes()


def test_rotated_phone_photo_is_turned_upright(client, owner, post, image_dir) -> None:
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: 90도 돌려서 봐야 하는 사진
    data = make_image("JPEG", size=(800, 600), exif=exif.tobytes())

    body = upload(client, post["id"], owner, data).json()

    # 회전 정보는 지워지므로 픽셀 자체가 세로로 돌아가 있어야 한다.
    assert Image.open(image_dir / body["url"].removeprefix("/images/")).size == (600, 800)


# ---------- 형식·크기 거절 ----------


@pytest.mark.parametrize("fmt, filename", [("GIF", "a.gif"), ("BMP", "a.bmp")])
def test_unsupported_formats_are_rejected(client, owner, post, image_dir, fmt, filename) -> None:
    response = upload(client, post["id"], owner, make_image(fmt), filename, "image/jpeg")

    assert response.status_code == 422
    assert response.json()["detail"] == "JPG, PNG, WebP 사진만 올릴 수 있습니다."
    assert stored_files(image_dir) == []


@pytest.mark.parametrize(
    "data",
    [
        b"<script>alert(1)</script>",  # .jpg로 이름만 바꾼 텍스트
        b"\xff\xd8\xff\xe0" + b"not really a jpeg" * 10,  # JPEG 헤더만 흉내 낸 파일
        make_image("JPEG")[:300],  # 중간에 잘린 사진
        b"",
    ],
    ids=["text", "fake-header", "truncated", "empty"],
)
def test_non_images_are_rejected(client, owner, post, image_dir, data) -> None:
    response = upload(client, post["id"], owner, data, "photo.jpg", "image/jpeg")

    assert response.status_code == 422
    assert stored_files(image_dir) == []


def test_file_over_5mb_is_rejected_with_413(client, owner, post, image_dir) -> None:
    # 헤더는 정상 JPEG이고 뒤를 채워 5MB를 넘긴다.
    data = make_image() + b"\0" * image_service.MAX_IMAGE_BYTES

    response = upload(client, post["id"], owner, data)

    assert response.status_code == 413
    assert response.json()["detail"] == "사진은 한 장에 5MB까지 올릴 수 있습니다."
    assert stored_files(image_dir) == []


def test_service_stops_reading_over_limit_without_content_length(client, owner, post, monkeypatch) -> None:
    # 미들웨어(Content-Length)를 거치지 않는 경우에도 서비스가 읽으면서 막는다.
    monkeypatch.setattr(image_service, "MAX_IMAGE_BYTES", 1000)

    response = upload(client, post["id"], owner, make_image())

    assert response.status_code == 413


def test_pixel_bomb_is_rejected(client, owner, post, image_dir) -> None:
    # 파일은 작지만 풀면 거대한 이미지 (8000 x 8000 = 6400만 픽셀)
    data = make_image("PNG", size=(8000, 8000), mode="L")
    assert len(data) < image_service.MAX_IMAGE_BYTES

    response = upload(client, post["id"], owner, data, "a.png", "image/png")

    assert response.status_code == 422
    assert stored_files(image_dir) == []


def test_missing_file_field_returns_422(client, owner, post) -> None:
    response = client.post(f"/posts/{post['id']}/images", headers=owner)

    assert response.status_code == 422


# ---------- 권한·상태 ----------


def test_upload_requires_login(client, post) -> None:
    assert upload(client, post["id"], {}, make_image()).status_code == 401


def test_upload_to_missing_post_returns_404(client, owner) -> None:
    assert upload(client, 9999, owner, make_image()).status_code == 404


def test_upload_to_others_post_returns_403(client, other, post, image_dir) -> None:
    assert upload(client, post["id"], other, make_image()).status_code == 403
    assert stored_files(image_dir) == []


def test_upload_to_sold_post_returns_400(client, owner, post) -> None:
    client.patch(f"/posts/{post['id']}/status", json={"status": "SOLD"}, headers=owner)

    response = upload(client, post["id"], owner, make_image())

    assert response.status_code == 400
    assert response.json()["detail"] == "판매 완료된 글은 수정할 수 없습니다."


def test_fourth_image_is_rejected(client, owner, post, image_dir) -> None:
    for _ in range(3):
        assert upload(client, post["id"], owner, make_image()).status_code == 201

    response = upload(client, post["id"], owner, make_image())

    assert response.status_code == 400
    assert response.json()["detail"] == "사진은 글 하나에 3장까지 올릴 수 있습니다."
    assert len(stored_files(image_dir)) == 6


def test_upload_rate_limit_returns_429(client, owner, create_post, monkeypatch) -> None:
    monkeypatch.setattr(
        image_service, "IMAGE_UPLOAD_RATE_LIMIT", image_service.UploadRateLimit(max_uploads=2, window_seconds=600)
    )
    first, second = create_post(owner), create_post(owner)
    assert upload(client, first["id"], owner, make_image()).status_code == 201
    assert upload(client, second["id"], owner, make_image()).status_code == 201  # 글이 달라도 함께 센다.

    response = upload(client, second["id"], owner, make_image())

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "600"


def test_rate_limit_is_per_user(client, owner, other, create_post, monkeypatch) -> None:
    monkeypatch.setattr(
        image_service, "IMAGE_UPLOAD_RATE_LIMIT", image_service.UploadRateLimit(max_uploads=1, window_seconds=600)
    )
    assert upload(client, create_post(owner)["id"], owner, make_image()).status_code == 201

    assert upload(client, create_post(other)["id"], other, make_image()).status_code == 201


# ---------- 삭제 ----------


def test_delete_image_removes_row_and_files(client, db_session: Session, owner, post, image_dir) -> None:
    body = upload(client, post["id"], owner, make_image()).json()

    response = client.delete(f"/posts/{post['id']}/images/{body['id']}", headers=owner)

    assert response.status_code == 204
    assert stored_files(image_dir) == []
    db_session.expire_all()
    assert db_session.get(PostImage, body["id"]) is None
    assert client.get(f"/posts/{post['id']}").json()["images"] == []


def test_deleted_slot_is_reused(client, owner, post) -> None:
    ids = [upload(client, post["id"], owner, make_image()).json()["id"] for _ in range(3)]
    client.delete(f"/posts/{post['id']}/images/{ids[0]}", headers=owner)

    assert upload(client, post["id"], owner, make_image()).status_code == 201
    assert len(client.get(f"/posts/{post['id']}").json()["images"]) == 3


def test_delete_image_permissions(client, owner, other, post, create_post) -> None:
    image = upload(client, post["id"], owner, make_image()).json()
    other_post = create_post(owner)

    assert client.delete(f"/posts/{post['id']}/images/{image['id']}").status_code == 401
    assert client.delete(f"/posts/{post['id']}/images/{image['id']}", headers=other).status_code == 403
    assert client.delete(f"/posts/9999/images/{image['id']}", headers=owner).status_code == 404
    # 다른 글 주소로 이 사진을 지울 수 없다.
    assert client.delete(f"/posts/{other_post['id']}/images/{image['id']}", headers=owner).status_code == 404
    assert client.delete(f"/posts/{post['id']}/images/9999", headers=owner).status_code == 404


def test_delete_image_of_sold_post_returns_400(client, owner, post) -> None:
    image = upload(client, post["id"], owner, make_image()).json()
    client.patch(f"/posts/{post['id']}/status", json={"status": "SOLD"}, headers=owner)

    assert client.delete(f"/posts/{post['id']}/images/{image['id']}", headers=owner).status_code == 400


def test_post_delete_removes_images_and_files(client, db_session: Session, owner, post, image_dir) -> None:
    for _ in range(2):
        upload(client, post["id"], owner, make_image())

    assert client.delete(f"/posts/{post['id']}", headers=owner).status_code == 204

    assert stored_files(image_dir) == []
    db_session.expire_all()
    assert db_session.scalars(select(PostImage)).all() == []


def test_failed_db_insert_leaves_no_files(client, owner, post, image_dir, monkeypatch) -> None:
    def broken(*_args, **_kwargs):
        raise RuntimeError("DB 오류 흉내")

    monkeypatch.setattr(image_service, "_insert_into_free_slot", broken)
    with pytest.raises(RuntimeError):
        upload(client, post["id"], owner, make_image())

    assert stored_files(image_dir) == []


# ---------- 응답·제공 ----------


def test_detail_includes_images_in_slot_order(client, owner, post) -> None:
    uploaded = [upload(client, post["id"], owner, make_image()).json() for _ in range(2)]

    images = client.get(f"/posts/{post['id']}").json()["images"]

    assert images == uploaded


def test_list_and_my_posts_include_first_thumbnail(client, owner, post, create_post) -> None:
    first = upload(client, post["id"], owner, make_image()).json()
    upload(client, post["id"], owner, make_image())
    no_image = create_post(owner)

    for url in ("/posts", "/users/me/posts"):
        items = {item["id"]: item for item in client.get(url, headers=owner).json()["items"]}
        assert items[post["id"]]["thumbnail_url"] == first["thumbnail_url"]
        assert items[no_image["id"]]["thumbnail_url"] is None
        assert "images" not in items[post["id"]]  # 목록에는 사진 목록 전체를 싣지 않는다.


def test_list_with_thumbnails_keeps_two_queries(client, owner, create_post) -> None:
    for _ in range(3):
        upload(client, create_post(owner)["id"], owner, make_image())

    statements: list[str] = []

    def count(*args) -> None:
        statements.append(args[2])

    event.listen(test_engine, "before_cursor_execute", count)
    try:
        assert client.get("/posts").status_code == 200
    finally:
        event.remove(test_engine, "before_cursor_execute", count)

    assert len(statements) == 2  # 전체 수 + 글(판매자·썸네일 포함)


def test_image_is_served_with_safe_headers(client, owner, post) -> None:
    body = upload(client, post["id"], owner, make_image()).json()

    response = client.get(body["url"])

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "max-age=31536000" in response.headers["cache-control"]
    assert Image.open(io.BytesIO(response.content)).format == "WEBP"
    assert client.get(body["thumbnail_url"]).status_code == 200


@pytest.mark.parametrize(
    "name",
    [
        "../app/main.py",
        "..%2F..%2F.env",
        "%2e%2e%2fdev.db",
        "dev.db",
        "0123456789abcdef0123456789abcdef.png",
        "0123456789ABCDEF0123456789ABCDEF.webp",
        "0123456789abcdef0123456789abcdef.webp",  # 형식은 맞지만 없는 파일
    ],
)
def test_image_route_rejects_bad_or_missing_names(client, name) -> None:
    response = client.get(f"/images/{name}")

    assert response.status_code == 404

