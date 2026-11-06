import pytest
from fastapi.testclient import TestClient

MY_POSTS_URL = "/users/me/posts"


def test_my_posts_returns_only_my_posts_newest_first(
    client: TestClient, make_auth_headers, create_post
) -> None:
    me = make_auth_headers("me@campus.ac.kr", "나야나")
    other = make_auth_headers("other@campus.ac.kr", "다른사람")
    mine_1 = create_post(me, title="내 글 1")["id"]
    create_post(other, title="남의 글")
    mine_2 = create_post(me, title="내 글 2")["id"]

    response = client.get(MY_POSTS_URL, headers=me)

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [mine_2, mine_1]
    assert body["total"] == 2
    assert {item["seller"]["nickname"] for item in body["items"]} == {"나야나"}


def test_my_posts_empty(client: TestClient, auth_headers: dict) -> None:
    response = client.get(MY_POSTS_URL, headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "size": 20}


def test_my_posts_without_login_returns_401(client: TestClient) -> None:
    response = client.get(MY_POSTS_URL)

    assert response.status_code == 401
    assert response.json() == {"detail": "로그인이 필요합니다."}


def test_my_posts_pagination(client: TestClient, auth_headers: dict, create_post) -> None:
    ids = [create_post(auth_headers, title=f"글{i}")["id"] for i in range(3)]
    newest_first = list(reversed(ids))

    page1 = client.get(MY_POSTS_URL, params={"page": 1, "size": 2}, headers=auth_headers).json()
    page2 = client.get(MY_POSTS_URL, params={"page": 2, "size": 2}, headers=auth_headers).json()
    page3 = client.get(MY_POSTS_URL, params={"page": 3, "size": 2}, headers=auth_headers).json()

    assert [item["id"] for item in page1["items"]] == newest_first[:2]
    assert [item["id"] for item in page2["items"]] == newest_first[2:]
    assert page3["items"] == []
    assert page1["total"] == page2["total"] == page3["total"] == 3


@pytest.mark.parametrize("params", [{"page": 0}, {"size": 0}, {"size": 101}])
def test_my_posts_with_invalid_pagination_returns_422(
    client: TestClient, auth_headers: dict, params: dict
) -> None:
    response = client.get(MY_POSTS_URL, params=params, headers=auth_headers)

    assert response.status_code == 422


def test_my_posts_route_is_not_shadowed_by_users_me(client: TestClient) -> None:
    # /users/me/posts가 OpenAPI에 등록되고 로그인이 필요한 API로 표시되는지 확인한다.
    schema = client.get("/openapi.json").json()

    assert {"OAuth2PasswordBearer": []} in schema["paths"][MY_POSTS_URL]["get"]["security"]
