from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Wishlist
from tests.conftest import test_engine

MY_WISHLIST_URL = "/users/me/wishlist"


@pytest.fixture
def seller(make_auth_headers) -> dict:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def buyer(make_auth_headers) -> dict:
    return make_auth_headers("buyer@campus.ac.kr", "구매자")


@pytest.fixture
def post(seller: dict, create_post) -> dict:
    return create_post(seller)


def wish(client: TestClient, post_id: int, headers: dict):
    return client.post(f"/posts/{post_id}/wishlist", headers=headers)


def unwish(client: TestClient, post_id: int, headers: dict):
    return client.delete(f"/posts/{post_id}/wishlist", headers=headers)


def wishlist_rows(db: Session) -> list[tuple[int, int]]:
    db.expire_all()
    return [(row.user_id, row.post_id) for row in db.scalars(select(Wishlist))]


def count_queries(client: TestClient, url: str, headers: dict | None = None) -> int:
    statements: list[str] = []

    def record(*args) -> None:
        statements.append(args[2])

    event.listen(test_engine, "before_cursor_execute", record)
    try:
        assert client.get(url, headers=headers or {}).status_code == 200
    finally:
        event.remove(test_engine, "before_cursor_execute", record)
    return len(statements)


# ---------- 추가·해제 ----------


def test_add_returns_201(client, buyer, post) -> None:
    response = wish(client, post["id"], buyer)

    assert response.status_code == 201
    assert response.json() == {"post_id": post["id"], "is_wishlisted": True}


def test_duplicate_add_returns_200_and_keeps_one_row(client, db_session, buyer, post) -> None:
    wish(client, post["id"], buyer)

    response = wish(client, post["id"], buyer)

    assert response.status_code == 200
    assert response.json()["is_wishlisted"] is True
    assert len(wishlist_rows(db_session)) == 1


def test_db_rejects_duplicate_row(db_session, client, buyer, post) -> None:
    # 서비스 검사를 건너뛰어도 기본 키(user_id, post_id)가 중복을 막는다.
    wish(client, post["id"], buyer)
    user_id = wishlist_rows(db_session)[0][0]
    db_session.add(Wishlist(user_id=user_id, post_id=post["id"]))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_remove_returns_204_and_deletes_row(client, db_session, buyer, post) -> None:
    wish(client, post["id"], buyer)

    response = unwish(client, post["id"], buyer)

    assert response.status_code == 204
    assert response.content == b""
    assert wishlist_rows(db_session) == []


def test_remove_not_wished_post_returns_204(client, buyer, post) -> None:
    assert unwish(client, post["id"], buyer).status_code == 204
    assert unwish(client, post["id"], buyer).status_code == 204  # 두 번 해제해도 같다.


def test_wish_again_after_remove(client, buyer, post) -> None:
    wish(client, post["id"], buyer)
    unwish(client, post["id"], buyer)

    assert wish(client, post["id"], buyer).status_code == 201


def test_remove_only_affects_my_wish(client, db_session, buyer, make_auth_headers, post) -> None:
    other = make_auth_headers("other@campus.ac.kr", "다른사람")
    wish(client, post["id"], buyer)
    wish(client, post["id"], other)

    unwish(client, post["id"], buyer)

    assert len(wishlist_rows(db_session)) == 1
    assert client.get(MY_WISHLIST_URL, headers=other).json()["total"] == 1


# ---------- 권한·상태 ----------


@pytest.mark.parametrize("method", ["post", "delete"])
def test_wishlist_requires_login(client, post, method) -> None:
    response = getattr(client, method)(f"/posts/{post['id']}/wishlist")

    assert response.status_code == 401


def test_my_wishlist_requires_login(client) -> None:
    assert client.get(MY_WISHLIST_URL).status_code == 401


@pytest.mark.parametrize("method", ["post", "delete"])
def test_missing_post_returns_404(client, buyer, method) -> None:
    response = getattr(client, method)("/posts/9999/wishlist", headers=buyer)

    assert response.status_code == 404
    assert response.json()["detail"] == "게시글을 찾을 수 없습니다."


def test_own_post_returns_400(client, db_session, seller, post) -> None:
    response = wish(client, post["id"], seller)

    assert response.status_code == 400
    assert response.json()["detail"] == "본인 글은 찜할 수 없습니다."
    assert wishlist_rows(db_session) == []


def test_new_wish_on_sold_post_returns_400(client, seller, buyer, post) -> None:
    client.patch(f"/posts/{post['id']}/status", json={"status": "SOLD"}, headers=seller)

    response = wish(client, post["id"], buyer)

    assert response.status_code == 400
    assert response.json()["detail"] == "판매 완료된 글은 새로 찜할 수 없습니다."


def test_reserved_post_can_be_wished(client, seller, buyer, post) -> None:
    client.patch(f"/posts/{post['id']}/status", json={"status": "RESERVED"}, headers=seller)

    assert wish(client, post["id"], buyer).status_code == 201


def test_wished_post_stays_in_list_after_sold(client, seller, buyer, post) -> None:
    wish(client, post["id"], buyer)
    client.patch(f"/posts/{post['id']}/status", json={"status": "SOLD"}, headers=seller)

    items = client.get(MY_WISHLIST_URL, headers=buyer).json()["items"]
    assert [(item["id"], item["status"]) for item in items] == [(post["id"], "SOLD")]
    # 이미 찜한 판매 완료 글에 다시 요청해도 실패하지 않고, 해제도 된다.
    assert wish(client, post["id"], buyer).status_code == 200
    assert unwish(client, post["id"], buyer).status_code == 204


# ---------- 글 삭제 연동 ----------


def test_post_delete_removes_wishes(client, db_session, seller, buyer, make_auth_headers, post, create_post) -> None:
    other = make_auth_headers("other@campus.ac.kr", "다른사람")
    keep = create_post(seller, title="남는 글")
    for headers in (buyer, other):
        wish(client, post["id"], headers)
    wish(client, keep["id"], buyer)

    assert client.delete(f"/posts/{post['id']}", headers=seller).status_code == 204

    assert [post_id for _, post_id in wishlist_rows(db_session)] == [keep["id"]]
    items = client.get(MY_WISHLIST_URL, headers=buyer).json()
    assert items["total"] == 1 and items["items"][0]["id"] == keep["id"]


# ---------- 내 찜 목록 ----------


def test_my_wishlist_empty(client, buyer) -> None:
    assert client.get(MY_WISHLIST_URL, headers=buyer).json() == {"items": [], "total": 0, "page": 1, "size": 20}


def test_my_wishlist_newest_wish_first(client, db_session, seller, buyer, create_post) -> None:
    ids = [create_post(seller, title=f"글{i}")["id"] for i in range(3)]
    # 글 순서와 다르게 찜하고, 찜한 시각을 직접 정해 "찜한 순서"로 정렬되는지 본다.
    for post_id in (ids[1], ids[0], ids[2]):
        wish(client, post_id, buyer)
    for minutes_ago, post_id in ((30, ids[1]), (20, ids[0]), (10, ids[2])):
        db_session.execute(
            update(Wishlist)
            .where(Wishlist.post_id == post_id)
            .values(created_at=_minutes_ago(db_session, minutes_ago))
        )
    db_session.commit()

    items = client.get(MY_WISHLIST_URL, headers=buyer).json()["items"]

    assert [item["id"] for item in items] == [ids[2], ids[0], ids[1]]


def test_my_wishlist_same_second_ordered_by_post_id_desc(client, db_session, seller, buyer, create_post) -> None:
    ids = [create_post(seller, title=f"글{i}")["id"] for i in range(3)]
    for post_id in ids:
        wish(client, post_id, buyer)
    db_session.execute(update(Wishlist).values(created_at=_minutes_ago(db_session, 5)))
    db_session.commit()

    items = client.get(MY_WISHLIST_URL, headers=buyer).json()["items"]

    assert [item["id"] for item in items] == sorted(ids, reverse=True)


def test_my_wishlist_items_have_card_fields(client, seller, buyer, post) -> None:
    wish(client, post["id"], buyer)

    item = client.get(MY_WISHLIST_URL, headers=buyer).json()["items"][0]

    assert item["is_wishlisted"] is True
    assert item["seller"] == {"id": post["seller"]["id"], "nickname": "판매자"}
    assert "thumbnail_url" in item and "email" not in item["seller"]


def test_my_wishlist_only_mine(client, seller, buyer, make_auth_headers, create_post) -> None:
    other = make_auth_headers("other@campus.ac.kr", "다른사람")
    mine, theirs = create_post(seller)["id"], create_post(seller)["id"]
    wish(client, mine, buyer)
    wish(client, theirs, other)

    items = client.get(MY_WISHLIST_URL, headers=buyer).json()["items"]

    assert [item["id"] for item in items] == [mine]


def test_my_wishlist_pagination(client, seller, buyer, create_post) -> None:
    ids = [create_post(seller, title=f"글{i}")["id"] for i in range(5)]
    for post_id in ids:
        wish(client, post_id, buyer)

    pages = [client.get(MY_WISHLIST_URL, params={"page": n, "size": 2}, headers=buyer).json() for n in (1, 2, 3, 4)]

    assert [len(page["items"]) for page in pages] == [2, 2, 1, 0]
    assert all(page["total"] == 5 for page in pages)
    seen = [item["id"] for page in pages for item in page["items"]]
    assert sorted(seen) == sorted(ids) and len(set(seen)) == 5  # 겹치거나 빠진 글이 없다.


@pytest.mark.parametrize("params", [{"page": 0}, {"size": 0}, {"size": 101}, {"page": "abc"}])
def test_my_wishlist_invalid_pagination_returns_422(client, buyer, params) -> None:
    assert client.get(MY_WISHLIST_URL, params=params, headers=buyer).status_code == 422


@pytest.mark.parametrize("size", [1, 100])
def test_my_wishlist_accepts_size_boundaries(client, buyer, size) -> None:
    assert client.get(MY_WISHLIST_URL, params={"size": size}, headers=buyer).status_code == 200


# ---------- 목록·상세의 찜 여부 ----------


def test_list_is_wishlisted_null_for_guest(client, buyer, post) -> None:
    wish(client, post["id"], buyer)

    assert client.get("/posts").json()["items"][0]["is_wishlisted"] is None


def test_list_is_wishlisted_for_logged_in_user(client, seller, buyer, create_post) -> None:
    wished, plain = create_post(seller)["id"], create_post(seller)["id"]
    wish(client, wished, buyer)

    flags = {item["id"]: item["is_wishlisted"] for item in client.get("/posts", headers=buyer).json()["items"]}

    assert flags == {wished: True, plain: False}


def test_detail_is_wishlisted(client, buyer, post) -> None:
    url = f"/posts/{post['id']}"
    assert client.get(url).json()["is_wishlisted"] is None
    assert client.get(url, headers=buyer).json()["is_wishlisted"] is False

    wish(client, post["id"], buyer)

    assert client.get(url, headers=buyer).json()["is_wishlisted"] is True


def test_invalid_token_list_still_works_without_flags(client, post) -> None:
    response = client.get("/posts", headers={"Authorization": "Bearer broken"})

    assert response.status_code == 200
    assert response.json()["items"][0]["is_wishlisted"] is None


# ---------- 쿼리 수 ----------


def test_guest_list_query_count_unchanged(client, seller, create_post) -> None:
    for _ in range(3):
        create_post(seller)

    assert count_queries(client, "/posts") == 2  # 개수 + 글(판매자·썸네일 포함)


def test_logged_in_list_adds_one_query_for_flags(client, seller, buyer, create_post) -> None:
    for _ in range(5):
        wish(client, create_post(seller)["id"], buyer)

    # 로그인 사용자 조회 1 + 개수 1 + 글 1 + 찜 여부 1. 글 수와 상관없다.
    assert count_queries(client, "/posts", buyer) == 4


def test_my_wishlist_query_count_does_not_grow(client, seller, buyer, create_post) -> None:
    wish(client, create_post(seller)["id"], buyer)
    one = count_queries(client, MY_WISHLIST_URL, buyer)
    for _ in range(4):
        wish(client, create_post(seller)["id"], buyer)

    assert count_queries(client, MY_WISHLIST_URL, buyer) == one == 3  # 사용자 + 개수 + 글


# 저장된 created_at과 같은 기준(DB 시간)으로 과거 시각을 만든다.
def _minutes_ago(db: Session, minutes: int):
    return db.scalar(select(func.now())) - timedelta(minutes=minutes)
