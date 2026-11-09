import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Message
from app.schemas.conversation import MAX_MESSAGE_LENGTH
from app.services import conversation_service
from app.services.conversation_service import MESSAGE_RATE_LIMIT, RateLimit

RATE_LIMITED = {"detail": "메시지를 너무 빠르게 보내고 있습니다. 잠시 후 다시 시도해 주세요."}


@pytest.fixture
def seller(make_auth_headers) -> dict:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def buyer(make_auth_headers) -> dict:
    return make_auth_headers("buyer@campus.ac.kr", "구매자")


@pytest.fixture
def stranger(make_auth_headers) -> dict:
    return make_auth_headers("stranger@campus.ac.kr", "제삼자")


@pytest.fixture
def conversation(client: TestClient, seller: dict, buyer: dict, create_post) -> dict:
    post = create_post(seller)
    response = client.post(f"/posts/{post['id']}/conversations", headers=buyer)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def no_rate_limit(monkeypatch) -> None:
    """메시지를 많이 만들어야 하는 테스트에서 도배 제한을 사실상 끈다."""
    monkeypatch.setattr(conversation_service, "MESSAGE_RATE_LIMIT", RateLimit(10_000, 10))


def post_message(client: TestClient, conversation_id: int, headers: dict | None, body: dict):
    return client.post(f"/conversations/{conversation_id}/messages", json=body, headers=headers or {})


def send(client: TestClient, conversation_id: int, headers: dict, content: str = "안녕하세요") -> dict:
    response = post_message(client, conversation_id, headers, {"content": content})
    assert response.status_code == 201, response.text
    return response.json()


def get_messages(client: TestClient, conversation_id: int, headers: dict | None, **params):
    return client.get(f"/conversations/{conversation_id}/messages", params=params, headers=headers or {})


def unread_count(client: TestClient, headers: dict) -> int:
    return client.get("/conversations", headers=headers).json()["items"][0]["unread_count"]


def message_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Message))


# ---------- 전송 ----------


def test_send_message(client: TestClient, buyer: dict, conversation: dict) -> None:
    response = post_message(client, conversation["id"], buyer, {"content": "아직 판매 중인가요?"})

    assert response.status_code == 201
    body = response.json()
    assert body["content"] == "아직 판매 중인가요?"
    assert body["is_mine"] is True
    assert body["read_at"] is None
    assert body["created_at"] is not None
    assert set(body) == {"id", "sender_id", "is_mine", "content", "created_at", "read_at"}


def test_seller_can_reply(client: TestClient, buyer: dict, seller: dict, conversation: dict) -> None:
    send(client, conversation["id"], buyer)

    assert send(client, conversation["id"], seller, "네 있어요")["is_mine"] is True


def test_stranger_cannot_send(
    client: TestClient, stranger: dict, conversation: dict, db_session: Session
) -> None:
    response = post_message(client, conversation["id"], stranger, {"content": "끼어들기"})

    assert response.status_code == 403
    assert message_count(db_session) == 0


def test_send_to_missing_conversation_is_404(client: TestClient, buyer: dict) -> None:
    assert post_message(client, 9999, buyer, {"content": "안녕"}).status_code == 404


def test_send_without_login_is_401(client: TestClient, conversation: dict) -> None:
    assert post_message(client, conversation["id"], None, {"content": "안녕"}).status_code == 401


def test_send_without_login_is_401_even_with_invalid_body(
    client: TestClient, conversation: dict
) -> None:
    # 로그인 확인이 입력 검사보다 먼저다. (비로그인 사용자에게 검증 규칙을 알려주지 않는다)
    assert post_message(client, conversation["id"], None, {"content": ""}).status_code == 401


# ---------- 내용 검증 ----------


@pytest.mark.parametrize(
    "content",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="spaces"),
        pytest.param("\n\t \n", id="whitespace-mix"),
        pytest.param("　", id="full-width-space"),
        pytest.param("a" * (MAX_MESSAGE_LENGTH + 1), id="too-long"),
        pytest.param(123, id="number"),
        pytest.param(None, id="null"),
    ],
)
def test_send_rejects_invalid_content(
    client: TestClient, buyer: dict, conversation: dict, db_session: Session, content
) -> None:
    response = post_message(client, conversation["id"], buyer, {"content": content})

    assert response.status_code == 422
    assert message_count(db_session) == 0


def test_send_rejects_missing_content(client: TestClient, buyer: dict, conversation: dict) -> None:
    assert post_message(client, conversation["id"], buyer, {}).status_code == 422


def test_send_rejects_unknown_field(client: TestClient, buyer: dict, conversation: dict) -> None:
    response = post_message(client, conversation["id"], buyer, {"content": "안녕", "sender_id": 1})

    assert response.status_code == 422


@pytest.mark.parametrize("length", [1, MAX_MESSAGE_LENGTH])
def test_send_accepts_length_boundaries(
    client: TestClient, buyer: dict, conversation: dict, length: int
) -> None:
    assert len(send(client, conversation["id"], buyer, "가" * length)["content"]) == length


def test_send_strips_outer_spaces_only(client: TestClient, buyer: dict, conversation: dict) -> None:
    # 앞뒤 공백은 지우고, 문장 사이 줄바꿈은 그대로 둔다. 지운 뒤 길이로 검사한다.
    body = send(client, conversation["id"], buyer, "  첫 줄\n\n둘째 줄  ")
    assert body["content"] == "첫 줄\n\n둘째 줄"

    padded = "  " + "a" * MAX_MESSAGE_LENGTH + "  "
    assert len(send(client, conversation["id"], buyer, padded)["content"]) == MAX_MESSAGE_LENGTH


def test_script_content_is_returned_as_plain_text(
    client: TestClient, buyer: dict, seller: dict, conversation: dict
) -> None:
    script = '<script>alert(1)</script><img src=x onerror="alert(2)">'
    send(client, conversation["id"], buyer, script)

    items = get_messages(client, conversation["id"], seller).json()["items"]
    assert items[0]["content"] == script


# ---------- 조회 ----------


def test_list_messages_in_order(client: TestClient, buyer: dict, seller: dict, conversation: dict) -> None:
    send(client, conversation["id"], buyer, "1")
    send(client, conversation["id"], seller, "2")
    send(client, conversation["id"], buyer, "3")

    body = get_messages(client, conversation["id"], buyer).json()

    assert [m["content"] for m in body["items"]] == ["1", "2", "3"]
    assert [m["is_mine"] for m in body["items"]] == [True, False, True]
    assert body["has_more"] is False


def test_list_messages_empty(client: TestClient, buyer: dict, conversation: dict) -> None:
    assert get_messages(client, conversation["id"], buyer).json() == {"items": [], "has_more": False}


def test_stranger_cannot_read_messages(client: TestClient, buyer: dict, stranger: dict, conversation: dict) -> None:
    send(client, conversation["id"], buyer)

    response = get_messages(client, conversation["id"], stranger)

    assert response.status_code == 403
    assert response.json() == {"detail": "대화에 참여한 사용자만 볼 수 있습니다."}


def test_stranger_does_not_mark_as_read(
    client: TestClient, buyer: dict, seller: dict, stranger: dict, conversation: dict
) -> None:
    send(client, conversation["id"], buyer)
    get_messages(client, conversation["id"], stranger)

    assert unread_count(client, seller) == 1


def test_read_missing_conversation_messages_is_404(client: TestClient, buyer: dict) -> None:
    assert get_messages(client, 9999, buyer).status_code == 404


def test_read_messages_without_login_is_401(client: TestClient, conversation: dict) -> None:
    assert get_messages(client, conversation["id"], None).status_code == 401


# ---------- 읽음 처리와 안 읽은 개수 ----------


def test_unread_count_counts_partner_messages_only(
    client: TestClient, buyer: dict, seller: dict, conversation: dict
) -> None:
    send(client, conversation["id"], buyer, "1")
    send(client, conversation["id"], buyer, "2")

    assert unread_count(client, seller) == 2
    # 내가 보낸 메시지는 내 안 읽은 개수에 들어가지 않는다.
    assert unread_count(client, buyer) == 0


def test_reading_marks_partner_messages_as_read(
    client: TestClient, buyer: dict, seller: dict, conversation: dict
) -> None:
    send(client, conversation["id"], buyer, "1")
    send(client, conversation["id"], buyer, "2")

    items = get_messages(client, conversation["id"], seller).json()["items"]

    assert all(m["read_at"] is not None for m in items)
    assert unread_count(client, seller) == 0


def test_sender_sees_read_receipt(client: TestClient, buyer: dict, seller: dict, conversation: dict) -> None:
    send(client, conversation["id"], buyer)
    assert get_messages(client, conversation["id"], buyer).json()["items"][0]["read_at"] is None

    get_messages(client, conversation["id"], seller)

    assert get_messages(client, conversation["id"], buyer).json()["items"][0]["read_at"] is not None


def test_reading_own_messages_does_not_mark_them(
    client: TestClient, buyer: dict, seller: dict, conversation: dict
) -> None:
    send(client, conversation["id"], buyer)

    get_messages(client, conversation["id"], buyer)

    assert unread_count(client, seller) == 1


def test_reading_marks_all_unread_even_outside_page(
    client: TestClient, buyer: dict, seller: dict, conversation: dict
) -> None:
    for i in range(3):
        send(client, conversation["id"], buyer, str(i))

    get_messages(client, conversation["id"], seller, limit=1)

    assert unread_count(client, seller) == 0


def test_new_message_after_reading_is_unread(
    client: TestClient, buyer: dict, seller: dict, conversation: dict
) -> None:
    send(client, conversation["id"], buyer, "1")
    get_messages(client, conversation["id"], seller)

    send(client, conversation["id"], buyer, "2")

    assert unread_count(client, seller) == 1


def test_unread_counts_are_per_conversation(
    client: TestClient, buyer: dict, seller: dict, stranger: dict, conversation: dict
) -> None:
    other = client.post(f"/posts/{conversation['post']['id']}/conversations", headers=stranger).json()
    send(client, conversation["id"], buyer, "1")
    send(client, other["id"], stranger, "1")
    send(client, other["id"], stranger, "2")

    counts = {c["id"]: c["unread_count"] for c in client.get("/conversations", headers=seller).json()["items"]}

    assert counts == {conversation["id"]: 1, other["id"]: 2}


# ---------- 커서 페이지네이션 ----------


@pytest.fixture
def seven_messages(client: TestClient, buyer: dict, conversation: dict, no_rate_limit) -> list[int]:
    return [send(client, conversation["id"], buyer, f"m{i}")["id"] for i in range(7)]


def test_default_returns_latest_messages(
    client: TestClient, buyer: dict, conversation: dict, seven_messages: list[int]
) -> None:
    body = get_messages(client, conversation["id"], buyer, limit=3).json()

    assert [m["id"] for m in body["items"]] == seven_messages[-3:]
    assert body["has_more"] is True


def test_before_id_walks_back_without_gaps(
    client: TestClient, buyer: dict, conversation: dict, seven_messages: list[int]
) -> None:
    collected: list[int] = []
    body = get_messages(client, conversation["id"], buyer, limit=3).json()
    collected = [m["id"] for m in body["items"]]
    while body["has_more"]:
        body = get_messages(client, conversation["id"], buyer, limit=3, before_id=collected[0]).json()
        collected = [m["id"] for m in body["items"]] + collected

    assert collected == seven_messages


def test_after_id_returns_newer_messages(
    client: TestClient, buyer: dict, conversation: dict, seven_messages: list[int]
) -> None:
    body = get_messages(client, conversation["id"], buyer, after_id=seven_messages[1], limit=3).json()

    assert [m["id"] for m in body["items"]] == seven_messages[2:5]
    assert body["has_more"] is True

    rest = get_messages(client, conversation["id"], buyer, after_id=seven_messages[4], limit=3).json()
    assert [m["id"] for m in rest["items"]] == seven_messages[5:]
    assert rest["has_more"] is False


def test_after_latest_id_is_empty(
    client: TestClient, buyer: dict, conversation: dict, seven_messages: list[int]
) -> None:
    body = get_messages(client, conversation["id"], buyer, after_id=seven_messages[-1]).json()

    assert body == {"items": [], "has_more": False}


def test_limit_equal_to_remaining_has_no_more(
    client: TestClient, buyer: dict, conversation: dict, seven_messages: list[int]
) -> None:
    body = get_messages(client, conversation["id"], buyer, limit=7).json()

    assert len(body["items"]) == 7
    assert body["has_more"] is False


def test_cursor_does_not_leak_other_conversations(
    client: TestClient, buyer: dict, stranger: dict, conversation: dict
) -> None:
    other = client.post(f"/posts/{conversation['post']['id']}/conversations", headers=stranger).json()
    before = send(client, other["id"], stranger, "남의 방 1")
    mine = send(client, conversation["id"], buyer, "내 방")
    send(client, other["id"], stranger, "남의 방 2")

    body = get_messages(client, conversation["id"], buyer, after_id=before["id"]).json()

    assert [m["id"] for m in body["items"]] == [mine["id"]]


@pytest.mark.parametrize(
    "params",
    [
        {"after_id": 1, "before_id": 5},
        {"limit": 0},
        {"limit": 101},
        {"after_id": 0},
        {"before_id": -1},
        {"after_id": "abc"},
    ],
)
def test_invalid_cursor_params_are_422(
    client: TestClient, buyer: dict, conversation: dict, params: dict
) -> None:
    assert get_messages(client, conversation["id"], buyer, **params).status_code == 422


# ---------- 도배 방지 ----------


def test_rate_limit_blocks_after_limit(
    client: TestClient, buyer: dict, conversation: dict, db_session: Session
) -> None:
    for i in range(MESSAGE_RATE_LIMIT.max_messages):
        send(client, conversation["id"], buyer, str(i))

    response = post_message(client, conversation["id"], buyer, {"content": "한 번 더"})

    assert response.status_code == 429
    assert response.json() == RATE_LIMITED
    assert response.headers["retry-after"] == str(MESSAGE_RATE_LIMIT.window_seconds)
    assert message_count(db_session) == MESSAGE_RATE_LIMIT.max_messages


def test_rate_limit_counts_across_conversations(
    client: TestClient, buyer: dict, seller: dict, conversation: dict, create_post
) -> None:
    # 여러 판매자에게 돌아가며 보내는 도배도 막는다.
    other_post = create_post(seller, title="다른 글")
    other = client.post(f"/posts/{other_post['id']}/conversations", headers=buyer).json()
    for i in range(MESSAGE_RATE_LIMIT.max_messages):
        target = conversation if i % 2 == 0 else other
        send(client, target["id"], buyer, str(i))

    assert post_message(client, other["id"], buyer, {"content": "더"}).status_code == 429


def test_rate_limit_is_per_sender(
    client: TestClient, buyer: dict, seller: dict, conversation: dict
) -> None:
    for i in range(MESSAGE_RATE_LIMIT.max_messages):
        send(client, conversation["id"], buyer, str(i))

    # 구매자가 제한에 걸려도 판매자는 답장할 수 있다.
    send(client, conversation["id"], seller, "천천히 보내 주세요")


def test_rate_limit_resets_after_window(
    client: TestClient, buyer: dict, conversation: dict, db_session: Session
) -> None:
    for i in range(MESSAGE_RATE_LIMIT.max_messages):
        send(client, conversation["id"], buyer, str(i))
    assert post_message(client, conversation["id"], buyer, {"content": "x"}).status_code == 429

    # 보낸 메시지들을 제한 시간보다 이전으로 옮겨, 시간이 지난 상황을 만든다.
    db_session.execute(
        update(Message).values(
            created_at=func.datetime(
                Message.created_at, f"-{MESSAGE_RATE_LIMIT.window_seconds + 1} seconds"
            )
        )
    )
    db_session.commit()

    send(client, conversation["id"], buyer, "이제 됩니다")


# ---------- 대화방 목록 갱신 ----------


def test_sending_updates_conversation_summary(
    client: TestClient, buyer: dict, seller: dict, conversation: dict
) -> None:
    before = client.get(f"/conversations/{conversation['id']}", headers=seller).json()
    send(client, conversation["id"], buyer, "마지막 메시지")

    after = client.get(f"/conversations/{conversation['id']}", headers=seller).json()

    assert after["last_message"]["content"] == "마지막 메시지"
    assert after["last_message"]["is_mine"] is False
    assert after["unread_count"] == 1
    assert after["last_message_at"] >= before["last_message_at"]
