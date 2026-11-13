from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Post

INVALID_TRANSITION = {"detail": "판매 완료된 글은 판매 중으로만 되돌릴 수 있습니다."}
STATUSES = ["ON_SALE", "RESERVED", "SOLD"]


@pytest.fixture
def owner(make_auth_headers) -> dict:
    return make_auth_headers("owner@campus.ac.kr", "작성자")


@pytest.fixture
def other(make_auth_headers) -> dict:
    return make_auth_headers("other@campus.ac.kr", "다른사람")


@pytest.fixture
def post(owner: dict, create_post) -> dict:
    return create_post(owner)


def change_status(client: TestClient, post_id: int, status: str, headers: dict | None = None):
    return client.patch(f"/posts/{post_id}/status", json={"status": status}, headers=headers or {})


# 테스트 준비용: 규칙을 거치지 않고 DB에서 바로 상태를 맞춘다.
# updated_at을 자기 자신으로 지정해, 준비 단계에서 onupdate로 시간이 바뀌지 않게 한다.
def set_status(db_session: Session, post_id: int, status: str) -> None:
    db_session.execute(
        update(Post)
        .where(Post.id == post_id)
        .values(status=status, updated_at=Post.updated_at)
    )
    db_session.commit()
    db_session.expire_all()


# ---------- 전이표 9칸 ----------

# (현재 상태, 바꿀 상태, 기대 응답 코드)
TRANSITIONS = [
    ("ON_SALE", "ON_SALE", 200),
    ("ON_SALE", "RESERVED", 200),
    ("ON_SALE", "SOLD", 200),
    ("RESERVED", "ON_SALE", 200),
    ("RESERVED", "RESERVED", 200),
    ("RESERVED", "SOLD", 200),
    ("SOLD", "ON_SALE", 200),
    ("SOLD", "RESERVED", 400),
    ("SOLD", "SOLD", 200),
]


@pytest.mark.parametrize(
    ("current", "target", "expected_code"),
    TRANSITIONS,
    ids=[f"{c}->{t}" for c, t, _ in TRANSITIONS],
)
def test_status_transition_table(
    client: TestClient,
    db_session: Session,
    owner: dict,
    post: dict,
    current: str,
    target: str,
    expected_code: int,
) -> None:
    set_status(db_session, post["id"], current)

    response = change_status(client, post["id"], target, owner)

    assert response.status_code == expected_code
    saved_status = client.get(f"/posts/{post['id']}").json()["status"]
    if expected_code == 200:
        assert response.json()["status"] == target
        assert saved_status == target
    else:
        assert response.json() == INVALID_TRANSITION
        assert saved_status == current  # 실패하면 상태가 바뀌지 않아야 한다.


def test_status_change_returns_full_post(client: TestClient, owner: dict, post: dict) -> None:
    body = change_status(client, post["id"], "RESERVED", owner).json()

    assert body == {**post, "status": "RESERVED", "updated_at": body["updated_at"]}


def test_status_flow_reserve_cancel_then_sell(
    client: TestClient, owner: dict, post: dict
) -> None:
    # 예약 → 예약 취소 → 다시 예약 → 판매 완료 흐름
    for status in ["RESERVED", "ON_SALE", "RESERVED", "SOLD"]:
        assert change_status(client, post["id"], status, owner).json()["status"] == status


# ---------- 멱등과 updated_at ----------


@pytest.fixture
def old_time(db_session: Session, post: dict) -> datetime:
    old = datetime(2020, 1, 1)
    db_session.execute(
        update(Post).where(Post.id == post["id"]).values(created_at=old, updated_at=old)
    )
    db_session.commit()
    db_session.expire_all()
    return old


def updated_at_of(response) -> datetime:
    return datetime.fromisoformat(response.json()["updated_at"]).replace(tzinfo=None)


def test_status_change_refreshes_updated_at(
    client: TestClient, owner: dict, post: dict, old_time: datetime
) -> None:
    assert updated_at_of(change_status(client, post["id"], "RESERVED", owner)) > old_time


@pytest.mark.parametrize("status", STATUSES)
def test_same_status_is_idempotent_and_keeps_updated_at(
    client: TestClient,
    db_session: Session,
    owner: dict,
    post: dict,
    old_time: datetime,
    status: str,
) -> None:
    set_status(db_session, post["id"], status)

    # 여러 번 보내도 같은 결과여야 한다.
    first = change_status(client, post["id"], status, owner)
    second = change_status(client, post["id"], status, owner)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert updated_at_of(second) == old_time


# ---------- 422: 입력 검증 ----------


@pytest.mark.parametrize(
    "body",
    [{"status": "DELETED"}, {"status": "on_sale"}, {"status": None}, {}, {"status": "SOLD", "price": 1}],
    ids=["없는상태", "소문자", "null", "빈본문", "다른필드"],
)
def test_status_change_with_invalid_body_returns_422(
    client: TestClient, owner: dict, post: dict, body: dict
) -> None:
    response = client.patch(f"/posts/{post['id']}/status", json=body, headers=owner)

    assert response.status_code == 422
    assert client.get(f"/posts/{post['id']}").json()["status"] == "ON_SALE"


# ---------- 401 / 403 / 404 ----------


def test_status_change_without_login_returns_401(client: TestClient, post: dict) -> None:
    response = change_status(client, post["id"], "SOLD")

    assert response.status_code == 401
    assert response.json() == {"detail": "로그인이 필요합니다."}


def test_status_change_by_other_user_returns_403(
    client: TestClient, other: dict, post: dict
) -> None:
    response = change_status(client, post["id"], "SOLD", other)

    assert response.status_code == 403
    assert response.json() == {"detail": "본인이 작성한 글만 수정·삭제할 수 있습니다."}
    assert client.get(f"/posts/{post['id']}").json()["status"] == "ON_SALE"


def test_status_change_on_sold_post_by_other_user_returns_403(
    client: TestClient, db_session: Session, other: dict, post: dict
) -> None:
    # 권한 확인(403)이 전이 규칙 확인(400)보다 먼저다.
    set_status(db_session, post["id"], "SOLD")

    assert change_status(client, post["id"], "ON_SALE", other).status_code == 403


def test_status_change_on_missing_post_returns_404(client: TestClient, owner: dict) -> None:
    response = change_status(client, 999, "SOLD", owner)

    assert response.status_code == 404
    assert response.json() == {"detail": "게시글을 찾을 수 없습니다."}
