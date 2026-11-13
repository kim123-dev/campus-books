from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, update
from sqlalchemy.orm import Session

from app.models import Post

POSTS_URL = "/posts"
POST_NOT_FOUND = {"detail": "게시글을 찾을 수 없습니다."}


# ---------- 상세 ----------


def test_read_post_returns_detail_with_seller_nickname(
    client: TestClient, auth_headers: dict, create_post
) -> None:
    created = create_post(auth_headers)

    response = client.get(f"{POSTS_URL}/{created['id']}")

    assert response.status_code == 200
    # 판매자의 매너 학점은 상세 조회에서만 채운다. 그 밖의 내용은 작성 응답과 같다.
    assert created["seller_manner"] is None
    assert response.json()["seller_manner"]["gpa"] == 3.5
    assert response.json() == {**created, "seller_manner": response.json()["seller_manner"]}
    assert response.json()["seller"]["nickname"] == "판매자"


def test_read_post_does_not_require_login(
    client: TestClient, auth_headers: dict, create_post
) -> None:
    created = create_post(auth_headers)

    assert client.get(f"{POSTS_URL}/{created['id']}").status_code == 200


@pytest.mark.parametrize("post_id", [999, 0, -1])
def test_read_missing_post_returns_404(client: TestClient, post_id: int) -> None:
    response = client.get(f"{POSTS_URL}/{post_id}")

    assert response.status_code == 404
    assert response.json() == POST_NOT_FOUND


def test_read_post_with_non_integer_id_returns_422(client: TestClient) -> None:
    assert client.get(f"{POSTS_URL}/abc").status_code == 422


# ---------- 목록: 내용과 정렬 ----------


def test_list_posts_empty(client: TestClient) -> None:
    response = client.get(POSTS_URL)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "size": 20}


def test_list_posts_shows_each_seller_nickname(
    client: TestClient, make_auth_headers, create_post
) -> None:
    create_post(make_auth_headers("a@campus.ac.kr", "철수"), title="A의 글")
    create_post(make_auth_headers("b@campus.ac.kr", "영희"), title="B의 글")

    items = client.get(POSTS_URL).json()["items"]

    nicknames = {item["title"]: item["seller"]["nickname"] for item in items}
    assert nicknames == {"A의 글": "철수", "B의 글": "영희"}


def test_list_posts_newest_first_when_created_in_same_second(
    client: TestClient, auth_headers: dict, create_post
) -> None:
    # 연달아 작성하면 created_at이 같은 초일 수 있다. 이때는 나중에 쓴 글(id가 큰 글)이 먼저 와야 한다.
    ids = [create_post(auth_headers, title=f"글{i}")["id"] for i in range(3)]

    items = client.get(POSTS_URL).json()["items"]

    assert [item["id"] for item in items] == list(reversed(ids))


def test_list_posts_sorted_by_created_at_not_id(
    client: TestClient, db_session: Session, auth_headers: dict, create_post
) -> None:
    first = create_post(auth_headers, title="먼저 쓴 글")
    second = create_post(auth_headers, title="나중에 쓴 글")
    # id 순서와 작성 시간 순서를 일부러 반대로 만들어, 정렬 기준이 created_at인지 확인한다.
    db_session.execute(
        update(Post).where(Post.id == first["id"]).values(created_at=datetime(2030, 1, 1))
    )
    db_session.execute(
        update(Post).where(Post.id == second["id"]).values(created_at=datetime(2020, 1, 1))
    )
    db_session.commit()

    items = client.get(POSTS_URL).json()["items"]

    assert [item["id"] for item in items] == [first["id"], second["id"]]


def test_list_posts_loads_sellers_without_n_plus_1(
    client: TestClient, db_session: Session, make_auth_headers, create_post
) -> None:
    for i in range(5):
        create_post(make_auth_headers(f"user{i}@campus.ac.kr", f"사용자{i}"))
    db_session.expire_all()  # 세션에 남아 있는 User 캐시를 비워, 실제로 DB 조회가 일어나게 한다.

    statements: list[str] = []

    def record(conn, cursor, statement, *args) -> None:
        statements.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        response = client.get(POSTS_URL)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert len(response.json()["items"]) == 5
    # 전체 개수 1번 + 글과 판매자를 JOIN한 목록 1번. 판매자 수가 늘어도 그대로여야 한다.
    assert len(statements) == 2


# ---------- 목록: 페이지네이션 ----------


@pytest.fixture
def three_posts(auth_headers: dict, create_post) -> list[int]:
    """최신순으로 정렬한 id 목록을 돌려준다."""
    ids = [create_post(auth_headers, title=f"글{i}")["id"] for i in range(3)]
    return list(reversed(ids))


@pytest.mark.parametrize(
    ("page", "expected_slice"),
    [(1, slice(0, 2)), (2, slice(2, 3)), (3, slice(0, 0))],
    ids=["첫페이지", "마지막페이지_일부", "마지막페이지_다음"],
)
def test_list_posts_pagination(
    client: TestClient, three_posts: list[int], page: int, expected_slice: slice
) -> None:
    response = client.get(POSTS_URL, params={"page": page, "size": 2})

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == three_posts[expected_slice]
    assert body["total"] == 3
    assert body["page"] == page
    assert body["size"] == 2


def test_list_posts_far_beyond_last_page_returns_empty(
    client: TestClient, three_posts: list[int]
) -> None:
    body = client.get(POSTS_URL, params={"page": 1000}).json()

    assert body["items"] == []
    assert body["total"] == 3


def test_list_posts_size_exactly_total_fits_one_page(
    client: TestClient, three_posts: list[int]
) -> None:
    first = client.get(POSTS_URL, params={"page": 1, "size": 3}).json()
    second = client.get(POSTS_URL, params={"page": 2, "size": 3}).json()

    assert [item["id"] for item in first["items"]] == three_posts
    assert second["items"] == []


@pytest.mark.parametrize("size", [1, 100])
def test_list_posts_accepts_size_boundaries(client: TestClient, size: int) -> None:
    response = client.get(POSTS_URL, params={"size": size})

    assert response.status_code == 200
    assert response.json()["size"] == size


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": -1},
        {"size": 0},
        {"size": 101},
        {"page": "abc"},
        {"size": "1.5"},
    ],
    ids=["page0", "page음수", "size0", "size101", "page문자", "size실수"],
)
def test_list_posts_with_invalid_pagination_returns_422(
    client: TestClient, params: dict
) -> None:
    assert client.get(POSTS_URL, params=params).status_code == 422


# ---------- updated_at ----------


def test_updated_at_changes_when_post_is_modified(
    client: TestClient, db_session: Session, auth_headers: dict, create_post
) -> None:
    # 수정 API는 아직 없으므로 ORM으로 직접 수정해, 모델의 자동 갱신 설정을 확인한다.
    created = create_post(auth_headers)
    old_time = datetime(2020, 1, 1)
    db_session.execute(
        update(Post)
        .where(Post.id == created["id"])
        .values(created_at=old_time, updated_at=old_time)
    )
    db_session.commit()

    post = db_session.get(Post, created["id"])
    post.price = 9000
    db_session.commit()
    db_session.refresh(post)

    assert post.updated_at.replace(tzinfo=None) > old_time
    assert post.created_at.replace(tzinfo=None) == old_time
