import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Post, User


@pytest.fixture
def owner(make_auth_headers) -> dict:
    return make_auth_headers("owner@campus.ac.kr", "작성자")


@pytest.fixture
def other(make_auth_headers) -> dict:
    return make_auth_headers("other@campus.ac.kr", "다른사람")


@pytest.fixture
def post(owner: dict, create_post) -> dict:
    return create_post(owner)


def delete_post(client: TestClient, post_id: int, headers: dict | None = None):
    return client.delete(f"/posts/{post_id}", headers=headers or {})


# ---------- 정상 ----------


def test_delete_returns_204_without_body(client: TestClient, owner: dict, post: dict) -> None:
    response = delete_post(client, post["id"], owner)

    assert response.status_code == 204
    assert response.content == b""


def test_deleted_post_is_removed_from_db(
    client: TestClient, db_session: Session, owner: dict, post: dict
) -> None:
    delete_post(client, post["id"], owner)

    # hard delete: 숨김 처리가 아니라 행 자체가 없어져야 한다.
    db_session.expire_all()
    assert db_session.get(Post, post["id"]) is None


def test_deleted_post_returns_404_on_read(client: TestClient, owner: dict, post: dict) -> None:
    delete_post(client, post["id"], owner)

    assert client.get(f"/posts/{post['id']}").status_code == 404


def test_deleted_post_disappears_from_lists(
    client: TestClient, owner: dict, create_post
) -> None:
    keep = create_post(owner, title="남길 글")
    remove = create_post(owner, title="지울 글")

    delete_post(client, remove["id"], owner)

    for url in ("/posts", "/users/me/posts"):
        body = client.get(url, headers=owner).json()
        assert [item["id"] for item in body["items"]] == [keep["id"]]
        assert body["total"] == 1


def test_delete_twice_returns_404(client: TestClient, owner: dict, post: dict) -> None:
    delete_post(client, post["id"], owner)

    response = delete_post(client, post["id"], owner)

    assert response.status_code == 404
    assert response.json() == {"detail": "게시글을 찾을 수 없습니다."}


@pytest.mark.parametrize("status", ["RESERVED", "SOLD"])
def test_delete_is_allowed_in_any_status(
    client: TestClient, owner: dict, post: dict, status: str
) -> None:
    client.patch(f"/posts/{post['id']}/status", json={"status": status}, headers=owner)

    assert delete_post(client, post["id"], owner).status_code == 204


def test_delete_keeps_the_seller_account(
    client: TestClient, db_session: Session, owner: dict, post: dict
) -> None:
    delete_post(client, post["id"], owner)

    db_session.expire_all()
    assert db_session.get(User, post["seller"]["id"]) is not None
    assert client.get("/users/me", headers=owner).status_code == 200


# ---------- 401 / 403 / 404 ----------


def test_delete_without_login_returns_401(client: TestClient, post: dict) -> None:
    response = delete_post(client, post["id"])

    assert response.status_code == 401
    assert response.json() == {"detail": "로그인이 필요합니다."}
    assert client.get(f"/posts/{post['id']}").status_code == 200


def test_delete_by_other_user_returns_403(client: TestClient, other: dict, post: dict) -> None:
    response = delete_post(client, post["id"], other)

    assert response.status_code == 403
    assert response.json() == {"detail": "본인이 작성한 글만 수정·삭제할 수 있습니다."}
    assert client.get(f"/posts/{post['id']}").status_code == 200


def test_delete_missing_post_returns_404(client: TestClient, owner: dict) -> None:
    assert delete_post(client, 999, owner).status_code == 404
