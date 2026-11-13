from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Post

NOT_OWNER = {"detail": "본인이 작성한 글만 수정·삭제할 수 있습니다."}
SOLD_NOT_EDITABLE = {"detail": "판매 완료된 글은 수정할 수 없습니다."}


@pytest.fixture
def owner(make_auth_headers) -> dict:
    return make_auth_headers("owner@campus.ac.kr", "작성자")


@pytest.fixture
def other(make_auth_headers) -> dict:
    return make_auth_headers("other@campus.ac.kr", "다른사람")


@pytest.fixture
def post(owner: dict, create_post) -> dict:
    return create_post(owner)


def patch_post(client: TestClient, post_id: int, body: dict, headers: dict | None = None):
    return client.patch(f"/posts/{post_id}", json=body, headers=headers or {})


def error_fields(response) -> set[str]:
    return {err["loc"][-1] for err in response.json()["detail"]}


# ---------- 정상: 일부 필드 수정 ----------


def test_update_only_sent_fields(client: TestClient, owner: dict, post: dict) -> None:
    response = patch_post(client, post["id"], {"price": 9000, "condition": "FAIR"}, owner)

    assert response.status_code == 200
    body = response.json()
    assert body["price"] == 9000
    assert body["condition"] == "FAIR"
    # 보내지 않은 필드는 그대로여야 한다.
    for field in ("title", "book_title", "course_name", "description", "status", "created_at"):
        assert body[field] == post[field]


def test_update_is_persisted(client: TestClient, owner: dict, post: dict) -> None:
    patch_post(client, post["id"], {"title": "가격 내렸어요"}, owner)

    assert client.get(f"/posts/{post['id']}").json()["title"] == "가격 내렸어요"


def test_update_all_fields(client: TestClient, owner: dict, post: dict) -> None:
    body = {
        "title": "새 제목",
        "book_title": "새 교재",
        "course_name": "새 과목",
        "condition": "POOR",
        "price": 0,
        "description": "새 설명",
    }

    response = patch_post(client, post["id"], body, owner)

    assert response.status_code == 200
    assert {k: response.json()[k] for k in body} == body


def test_update_with_empty_body_changes_nothing(
    client: TestClient, owner: dict, post: dict
) -> None:
    response = patch_post(client, post["id"], {}, owner)

    assert response.status_code == 200
    assert response.json() == post


@pytest.mark.parametrize("value", [None, "", "   "], ids=["null", "빈문자열", "공백"])
@pytest.mark.parametrize("field", ["course_name", "description"])
def test_update_can_clear_optional_field(
    client: TestClient, owner: dict, post: dict, field: str, value
) -> None:
    response = patch_post(client, post["id"], {field: value}, owner)

    assert response.status_code == 200
    assert response.json()[field] is None


def test_update_strips_text(client: TestClient, owner: dict, post: dict) -> None:
    body = patch_post(client, post["id"], {"title": "  새 제목  "}, owner).json()

    assert body["title"] == "새 제목"


# ---------- updated_at ----------


@pytest.fixture
def old_time(db_session: Session, post: dict) -> datetime:
    """SQLite는 초 단위라 바로 비교하면 같은 값이 나올 수 있어, 시간을 과거로 돌려둔다."""
    old = datetime(2020, 1, 1)
    db_session.execute(
        update(Post).where(Post.id == post["id"]).values(created_at=old, updated_at=old)
    )
    db_session.commit()
    db_session.expire_all()
    return old


def test_update_refreshes_updated_at(
    client: TestClient, owner: dict, post: dict, old_time: datetime
) -> None:
    body = patch_post(client, post["id"], {"price": 1}, owner).json()

    assert datetime.fromisoformat(body["updated_at"]).replace(tzinfo=None) > old_time
    assert datetime.fromisoformat(body["created_at"]).replace(tzinfo=None) == old_time


@pytest.mark.parametrize("body", [{}, {"price": 15000}], ids=["빈본문", "같은값"])
def test_update_without_real_change_keeps_updated_at(
    client: TestClient, owner: dict, post: dict, old_time: datetime, body: dict
) -> None:
    # post_payload의 가격이 15000이므로 같은 값으로 수정하는 경우다.
    response = patch_post(client, post["id"], body, owner)

    assert datetime.fromisoformat(response.json()["updated_at"]).replace(tzinfo=None) == old_time


# ---------- 422: 입력 검증 ----------


@pytest.mark.parametrize("status_value", ["ON_SALE", "SOLD"])
def test_update_rejects_status_field(
    client: TestClient, owner: dict, post: dict, status_value: str
) -> None:
    response = patch_post(client, post["id"], {"status": status_value}, owner)

    assert response.status_code == 422
    assert error_fields(response) == {"status"}
    assert client.get(f"/posts/{post['id']}").json()["status"] == "ON_SALE"


@pytest.mark.parametrize("field", ["title", "book_title", "condition", "price"])
def test_update_required_field_to_null_returns_422(
    client: TestClient, owner: dict, post: dict, field: str
) -> None:
    response = patch_post(client, post["id"], {field: None}, owner)

    assert response.status_code == 422
    assert error_fields(response) == {field}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("price", -1),
        ("price", 10_000_001),
        ("price", "9000"),
        ("condition", "BEST"),
        ("title", "   "),
        ("title", "가" * 101),
        ("book_title", "가" * 201),
        ("course_name", "가" * 101),
        ("description", "가" * 2001),
    ],
    ids=["가격음수", "가격상한초과", "가격문자열", "잘못된상태", "제목공백", "제목101자",
         "교재명201자", "과목명101자", "설명2001자"],
)
def test_update_with_invalid_value_returns_422(
    client: TestClient, owner: dict, post: dict, field: str, value
) -> None:
    response = patch_post(client, post["id"], {field: value}, owner)

    assert response.status_code == 422
    assert error_fields(response) == {field}


# ---------- 400: 판매 완료된 글 ----------


@pytest.fixture
def sold_post(client: TestClient, owner: dict, post: dict) -> dict:
    response = client.patch(f"/posts/{post['id']}/status", json={"status": "SOLD"}, headers=owner)
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("body", [{"price": 1000}, {}], ids=["내용수정", "빈본문"])
def test_update_sold_post_returns_400(
    client: TestClient, owner: dict, sold_post: dict, body: dict
) -> None:
    response = patch_post(client, sold_post["id"], body, owner)

    assert response.status_code == 400
    assert response.json() == SOLD_NOT_EDITABLE
    # 상세 조회에서만 채우는 판매자 매너 학점을 빼면 그대로다.
    after = client.get(f"/posts/{sold_post['id']}").json()
    assert {**after, "seller_manner": None} == sold_post


@pytest.mark.parametrize("status_value", ["ON_SALE", "RESERVED"])
def test_update_non_sold_post_is_allowed(
    client: TestClient, owner: dict, post: dict, status_value: str
) -> None:
    client.patch(f"/posts/{post['id']}/status", json={"status": status_value}, headers=owner)

    assert patch_post(client, post["id"], {"price": 1000}, owner).status_code == 200


# ---------- 401 / 403 / 404 ----------


def test_update_without_login_returns_401(client: TestClient, post: dict) -> None:
    response = patch_post(client, post["id"], {"price": 1000})

    assert response.status_code == 401
    assert response.json() == {"detail": "로그인이 필요합니다."}


def test_update_by_other_user_returns_403(
    client: TestClient, other: dict, post: dict
) -> None:
    response = patch_post(client, post["id"], {"price": 1}, other)

    assert response.status_code == 403
    assert response.json() == NOT_OWNER
    assert client.get(f"/posts/{post['id']}").json()["price"] == post["price"]


def test_update_sold_post_by_other_user_returns_403(
    client: TestClient, other: dict, sold_post: dict
) -> None:
    # 권한 확인(403)이 판매 완료 확인(400)보다 먼저다.
    assert patch_post(client, sold_post["id"], {"price": 1}, other).status_code == 403


def test_update_missing_post_returns_404(client: TestClient, owner: dict) -> None:
    response = patch_post(client, 999, {"price": 1}, owner)

    assert response.status_code == 404
    assert response.json() == {"detail": "게시글을 찾을 수 없습니다."}
