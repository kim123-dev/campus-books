from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import UserBlock
from tests.conftest import test_engine

MY_BLOCKS_URL = "/users/me/blocks"
I_BLOCKED = "차단한 사용자에게는 쪽지를 보낼 수 없습니다. 차단을 해제하면 다시 보낼 수 있어요."
THEY_BLOCKED = "이 사용자에게는 쪽지를 보낼 수 없습니다."


@pytest.fixture
def seller(make_auth_headers) -> dict:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def buyer(make_auth_headers) -> dict:
    return make_auth_headers("buyer@campus.ac.kr", "구매자")


@pytest.fixture
def post(seller: dict, create_post) -> dict:
    return create_post(seller)


def user_id(client: TestClient, headers: dict) -> int:
    return client.get("/users/me", headers=headers).json()["id"]


def block(client: TestClient, target_id: int, headers: dict):
    return client.post(f"/users/{target_id}/block", headers=headers)


def unblock(client: TestClient, target_id: int, headers: dict):
    return client.delete(f"/users/{target_id}/block", headers=headers)


def send(client: TestClient, conversation_id: int, headers: dict, content: str = "안녕하세요"):
    return client.post(f"/conversations/{conversation_id}/messages", json={"content": content}, headers=headers)


@pytest.fixture
def conversation(client: TestClient, buyer: dict, post: dict) -> dict:
    response = client.post(f"/posts/{post['id']}/conversations", headers=buyer)
    assert response.status_code == 201
    return response.json()


def block_rows(db: Session) -> list[tuple[int, int]]:
    db.expire_all()
    return [(row.blocker_id, row.blocked_id) for row in db.scalars(select(UserBlock))]


# ---------- 차단·해제 ----------


def test_block_returns_201(client, seller, buyer) -> None:
    target = user_id(client, seller)

    response = block(client, target, buyer)

    assert response.status_code == 201
    assert response.json() == {"user_id": target, "is_blocked": True}


def test_duplicate_block_returns_200_and_keeps_one_row(client, db_session, seller, buyer) -> None:
    target = user_id(client, seller)
    block(client, target, buyer)

    assert block(client, target, buyer).status_code == 200
    assert len(block_rows(db_session)) == 1


def test_unblock_returns_204(client, db_session, seller, buyer) -> None:
    target = user_id(client, seller)
    block(client, target, buyer)

    response = unblock(client, target, buyer)

    assert response.status_code == 204 and response.content == b""
    assert block_rows(db_session) == []


def test_unblock_not_blocked_user_returns_204(client, seller, buyer) -> None:
    assert unblock(client, user_id(client, seller), buyer).status_code == 204


def test_block_self_returns_400(client, db_session, buyer) -> None:
    me = user_id(client, buyer)

    response = block(client, me, buyer)

    assert response.status_code == 400
    assert response.json()["detail"] == "자기 자신은 차단할 수 없습니다."
    assert block_rows(db_session) == []


def test_db_rejects_self_block(client, db_session, buyer) -> None:
    # 서비스 검사를 건너뛰어도 CHECK 제약이 막는다.
    me = user_id(client, buyer)
    db_session.add(UserBlock(blocker_id=me, blocked_id=me))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("method", ["post", "delete"])
def test_block_requires_login(client, seller, method) -> None:
    target = user_id(client, seller)

    assert getattr(client, method)(f"/users/{target}/block").status_code == 401


@pytest.mark.parametrize("method", ["post", "delete"])
def test_block_missing_user_returns_404(client, buyer, method) -> None:
    response = getattr(client, method)("/users/9999/block", headers=buyer)

    assert response.status_code == 404
    assert response.json()["detail"] == "사용자를 찾을 수 없습니다."


# ---------- 차단 목록 ----------


def test_my_blocks_requires_login(client) -> None:
    assert client.get(MY_BLOCKS_URL).status_code == 401


def test_my_blocks_shows_nickname_without_email(client, seller, buyer) -> None:
    target = user_id(client, seller)
    block(client, target, buyer)

    body = client.get(MY_BLOCKS_URL, headers=buyer).json()

    assert body["total"] == 1
    item = body["items"][0]
    assert item["user"] == {"id": target, "nickname": "판매자"}
    assert set(item) == {"user", "created_at"}
    assert "email" not in str(body) and "@" not in str(body)


def test_my_blocks_only_mine_and_not_who_blocked_me(client, seller, buyer) -> None:
    block(client, user_id(client, seller), buyer)

    # 차단당한 쪽의 목록에는 아무것도 없다. (누가 나를 차단했는지 알 수 없다)
    assert client.get(MY_BLOCKS_URL, headers=seller).json()["total"] == 0


def test_my_blocks_newest_first_and_pagination(client, db_session, buyer, make_auth_headers) -> None:
    targets = [user_id(client, make_auth_headers(f"u{i}@campus.ac.kr", f"사용자{i}")) for i in range(5)]
    for target in targets:
        block(client, target, buyer)
    # 차단한 시각을 직접 정해 순서를 확인한다: targets[2]가 가장 최근.
    db_now = db_session.scalar(select(func.now()))
    for minutes_ago, target in zip((50, 40, 10, 30, 20), targets):
        db_session.execute(
            update(UserBlock).where(UserBlock.blocked_id == target).values(created_at=db_now - timedelta(minutes=minutes_ago))
        )
    db_session.commit()

    pages = [client.get(MY_BLOCKS_URL, params={"page": n, "size": 2}, headers=buyer).json() for n in (1, 2, 3)]

    order = [item["user"]["id"] for page in pages for item in page["items"]]
    assert order == [targets[2], targets[4], targets[3], targets[1], targets[0]]
    assert [len(page["items"]) for page in pages] == [2, 2, 1]
    assert all(page["total"] == 5 for page in pages)


@pytest.mark.parametrize("params", [{"page": 0}, {"size": 101}])
def test_my_blocks_invalid_pagination_returns_422(client, buyer, params) -> None:
    assert client.get(MY_BLOCKS_URL, params=params, headers=buyer).status_code == 422


# ---------- 쪽지 (양방향) ----------


@pytest.mark.parametrize(
    ("blocker", "sender", "message"),
    [("buyer", "buyer", I_BLOCKED), ("buyer", "seller", THEY_BLOCKED), ("seller", "seller", I_BLOCKED), ("seller", "buyer", THEY_BLOCKED)],
    ids=["buyer-blocks-buyer-sends", "buyer-blocks-seller-sends", "seller-blocks-seller-sends", "seller-blocks-buyer-sends"],
)
def test_message_blocked_both_directions(client, seller, buyer, conversation, blocker, sender, message) -> None:
    users = {"seller": seller, "buyer": buyer}
    other = "seller" if blocker == "buyer" else "buyer"
    block(client, user_id(client, users[other]), users[blocker])

    response = send(client, conversation["id"], users[sender])

    assert response.status_code == 400
    assert response.json()["detail"] == message


def test_blocked_message_is_not_saved(client, seller, buyer, conversation) -> None:
    block(client, user_id(client, buyer), seller)
    send(client, conversation["id"], buyer, "저장되면 안 되는 메시지")

    items = client.get(f"/conversations/{conversation['id']}/messages", headers=seller).json()["items"]
    assert all(item["content"] != "저장되면 안 되는 메시지" for item in items)


def test_messaging_works_again_after_unblock(client, seller, buyer, conversation) -> None:
    target = user_id(client, seller)
    block(client, target, buyer)
    unblock(client, target, buyer)

    assert send(client, conversation["id"], buyer).status_code == 201
    assert send(client, conversation["id"], seller).status_code == 201


def test_history_still_readable_after_block(client, seller, buyer, conversation) -> None:
    send(client, conversation["id"], buyer, "차단 전 메시지")
    block(client, user_id(client, seller), buyer)

    for headers in (buyer, seller):
        response = client.get(f"/conversations/{conversation['id']}/messages", headers=headers)
        assert response.status_code == 200
        assert [m["content"] for m in response.json()["items"]] == ["차단 전 메시지"]
    # 쪽지함에도 그대로 남는다.
    assert client.get("/conversations", headers=buyer).json()["total"] == 1


@pytest.mark.parametrize("blocker", ["buyer", "seller"])
def test_new_inquiry_blocked_both_directions(client, seller, buyer, post, blocker) -> None:
    users = {"seller": seller, "buyer": buyer}
    other = "seller" if blocker == "buyer" else "buyer"
    block(client, user_id(client, users[other]), users[blocker])

    response = client.post(f"/posts/{post['id']}/conversations", headers=buyer)

    assert response.status_code == 400
    assert response.json()["detail"] == (I_BLOCKED if blocker == "buyer" else THEY_BLOCKED)


def test_existing_conversation_returned_even_if_blocked(client, seller, buyer, post, conversation) -> None:
    block(client, user_id(client, seller), buyer)

    response = client.post(f"/posts/{post['id']}/conversations", headers=buyer)

    assert response.status_code == 200
    assert response.json()["id"] == conversation["id"]
    assert response.json()["can_send"] is False


def test_conversation_detail_block_flags(client, seller, buyer, conversation) -> None:
    url = f"/conversations/{conversation['id']}"
    assert {k: conversation[k] for k in ("can_send", "blocked_by_me")} == {"can_send": True, "blocked_by_me": False}

    block(client, user_id(client, seller), buyer)

    mine = client.get(url, headers=buyer).json()
    theirs = client.get(url, headers=seller).json()
    assert (mine["can_send"], mine["blocked_by_me"]) == (False, True)
    # 차단당한 쪽은 보낼 수 없다는 것만 알고, 차단당했다는 표시는 받지 않는다.
    assert (theirs["can_send"], theirs["blocked_by_me"]) == (False, False)


def test_conversation_list_has_no_block_fields(client, seller, buyer, conversation) -> None:
    block(client, user_id(client, seller), buyer)

    item = client.get("/conversations", headers=seller).json()["items"][0]

    assert "can_send" not in item and "blocked_by_me" not in item


# ---------- 목록 숨김 ----------


def test_blocked_users_posts_hidden_from_my_list(client, seller, buyer, make_auth_headers, create_post) -> None:
    other = make_auth_headers("other@campus.ac.kr", "다른판매자")
    hidden = [create_post(seller, title=f"숨길 글{i}")["id"] for i in range(2)]
    visible = create_post(other, title="보일 글")["id"]
    block(client, user_id(client, seller), buyer)

    body = client.get("/posts", headers=buyer).json()

    assert [item["id"] for item in body["items"]] == [visible]
    assert body["total"] == 1
    assert all(post_id not in [item["id"] for item in body["items"]] for post_id in hidden)


def test_hidden_with_search_and_filters(client, seller, buyer, make_auth_headers, create_post) -> None:
    other = make_auth_headers("other@campus.ac.kr", "다른판매자")
    create_post(seller, title="자료구조 A", price=1000)
    keep = create_post(other, title="자료구조 B", price=2000)["id"]
    block(client, user_id(client, seller), buyer)

    body = client.get("/posts", params={"q": "자료구조", "max_price": 5000}, headers=buyer).json()

    assert [item["id"] for item in body["items"]] == [keep] and body["total"] == 1


def test_list_hiding_is_one_way(client, seller, buyer, create_post) -> None:
    create_post(buyer, title="구매자 글")
    block(client, user_id(client, buyer), seller)  # 판매자가 구매자를 차단

    # 차단당한 구매자의 목록에는 판매자 글이 그대로 보인다. (차단 사실을 알아챌 수 없게)
    seller_posts = create_post(seller, title="판매자 글")["id"]
    assert seller_posts in [item["id"] for item in client.get("/posts", headers=buyer).json()["items"]]
    # 차단한 판매자의 목록에서는 구매자 글이 빠진다.
    assert [item["title"] for item in client.get("/posts", headers=seller).json()["items"]] == ["판매자 글"]


def test_guest_list_unaffected(client, seller, buyer, post) -> None:
    block(client, user_id(client, seller), buyer)

    assert client.get("/posts").json()["total"] == 1


def test_list_visible_again_after_unblock(client, seller, buyer, post) -> None:
    target = user_id(client, seller)
    block(client, target, buyer)
    unblock(client, target, buyer)

    assert client.get("/posts", headers=buyer).json()["total"] == 1


def test_logged_in_list_query_count_unchanged_by_blocks(client, seller, buyer, make_auth_headers, create_post) -> None:
    for i in range(3):
        block(client, user_id(client, make_auth_headers(f"b{i}@campus.ac.kr", f"차단{i}")), buyer)
    for _ in range(3):
        create_post(seller)

    statements: list[str] = []

    def record(*args) -> None:
        statements.append(args[2])

    event.listen(test_engine, "before_cursor_execute", record)
    try:
        assert client.get("/posts", headers=buyer).status_code == 200
    finally:
        event.remove(test_engine, "before_cursor_execute", record)

    # 로그인 사용자 + 개수 + 글 + 찜 여부. 차단 조건은 같은 쿼리 안의 하위 쿼리라 늘지 않는다.
    assert len(statements) == 4


def test_detail_still_viewable_with_block_flag(client, seller, buyer, post) -> None:
    url = f"/posts/{post['id']}"
    assert client.get(url).json()["is_seller_blocked"] is None
    assert client.get(url, headers=buyer).json()["is_seller_blocked"] is False

    block(client, user_id(client, seller), buyer)

    response = client.get(url, headers=buyer)
    assert response.status_code == 200
    assert response.json()["is_seller_blocked"] is True
    # 판매자 쪽 화면에는 누가 자신을 차단했는지 드러나지 않는다.
    assert client.get(url, headers=seller).json()["is_seller_blocked"] is False
