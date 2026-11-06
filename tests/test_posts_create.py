import pytest
from fastapi.testclient import TestClient

POSTS_URL = "/posts"
NOT_AUTHENTICATED = {"detail": "로그인이 필요합니다."}


# 422 응답에서 어떤 필드 때문에 실패했는지 확인한다.
def error_fields(response) -> set[str]:
    return {err["loc"][-1] for err in response.json()["detail"]}


# ---------- 정상 ----------


def test_create_post_returns_201_with_defaults(
    client: TestClient, auth_headers: dict, post_payload: dict
) -> None:
    response = client.post(POSTS_URL, json=post_payload, headers=auth_headers)

    assert response.status_code == 201
    body = response.json()
    for key, value in post_payload.items():
        assert body[key] == value
    # status는 요청에 없어도 ON_SALE로 시작한다.
    assert body["status"] == "ON_SALE"
    assert body["seller"]["nickname"] == "판매자"
    assert set(body["seller"]) == {"id", "nickname"}  # 이메일은 노출하지 않는다.
    assert body["created_at"] is not None
    assert body["updated_at"] is not None


def test_create_post_with_only_required_fields(
    client: TestClient, auth_headers: dict
) -> None:
    payload = {"title": "책 팝니다", "book_title": "선형대수학", "condition": "POOR", "price": 0}

    response = client.post(POSTS_URL, json=payload, headers=auth_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["course_name"] is None
    assert body["description"] is None
    assert body["price"] == 0  # 무료 나눔(0원)은 허용


def test_create_post_strips_text_and_turns_blank_optional_into_none(
    client: TestClient, auth_headers: dict, post_payload: dict
) -> None:
    payload = {
        **post_payload,
        "title": "  자료구조  ",
        "book_title": " 자료구조 교재 ",
        "course_name": "   ",
        "description": "",
    }

    body = client.post(POSTS_URL, json=payload, headers=auth_headers).json()

    assert body["title"] == "자료구조"
    assert body["book_title"] == "자료구조 교재"
    assert body["course_name"] is None
    assert body["description"] is None


# ---------- 인증 ----------


def test_create_post_without_login_returns_401(client: TestClient, post_payload: dict) -> None:
    response = client.post(POSTS_URL, json=post_payload)

    assert response.status_code == 401
    assert response.json() == NOT_AUTHENTICATED
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_create_post_with_invalid_token_returns_401(
    client: TestClient, post_payload: dict
) -> None:
    response = client.post(
        POSTS_URL, json=post_payload, headers={"Authorization": "Bearer not-a-jwt"}
    )

    assert response.status_code == 401


# ---------- 가격 ----------


@pytest.mark.parametrize(
    "price",
    [-1, 10_000_001, "15000", 1500.5, None],
    ids=["음수", "상한초과", "문자열", "실수", "null"],
)
def test_create_post_with_invalid_price_returns_422(
    client: TestClient, auth_headers: dict, post_payload: dict, price
) -> None:
    response = client.post(POSTS_URL, json={**post_payload, "price": price}, headers=auth_headers)

    assert response.status_code == 422
    assert error_fields(response) == {"price"}


def test_create_post_with_max_price_returns_201(
    client: TestClient, auth_headers: dict, post_payload: dict
) -> None:
    response = client.post(
        POSTS_URL, json={**post_payload, "price": 10_000_000}, headers=auth_headers
    )

    assert response.status_code == 201


# ---------- status는 받지 않음 ----------


@pytest.mark.parametrize("status_value", ["ON_SALE", "SOLD"])
def test_create_post_rejects_status_field(
    client: TestClient, auth_headers: dict, post_payload: dict, status_value: str
) -> None:
    response = client.post(
        POSTS_URL, json={**post_payload, "status": status_value}, headers=auth_headers
    )

    assert response.status_code == 422
    assert error_fields(response) == {"status"}


# ---------- 필수/선택 필드 ----------


@pytest.mark.parametrize("field", ["title", "book_title", "condition", "price"])
def test_create_post_missing_required_field_returns_422(
    client: TestClient, auth_headers: dict, post_payload: dict, field: str
) -> None:
    payload = {k: v for k, v in post_payload.items() if k != field}

    response = client.post(POSTS_URL, json=payload, headers=auth_headers)

    assert response.status_code == 422
    assert error_fields(response) == {field}


@pytest.mark.parametrize("condition", ["BEST", "good", "상", ""])
def test_create_post_with_invalid_condition_returns_422(
    client: TestClient, auth_headers: dict, post_payload: dict, condition: str
) -> None:
    response = client.post(
        POSTS_URL, json={**post_payload, "condition": condition}, headers=auth_headers
    )

    assert response.status_code == 422
    assert error_fields(response) == {"condition"}


@pytest.mark.parametrize("condition", ["GOOD", "FAIR", "POOR"])
def test_create_post_accepts_every_condition(
    client: TestClient, auth_headers: dict, post_payload: dict, condition: str
) -> None:
    response = client.post(
        POSTS_URL, json={**post_payload, "condition": condition}, headers=auth_headers
    )

    assert response.status_code == 201
    assert response.json()["condition"] == condition


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "   "),
        ("title", "가" * 101),
        ("book_title", ""),
        ("book_title", "가" * 201),
        ("course_name", "가" * 101),
        ("description", "가" * 2001),
    ],
    ids=["제목공백", "제목101자", "교재명빈값", "교재명201자", "과목명101자", "설명2001자"],
)
def test_create_post_with_invalid_text_returns_422(
    client: TestClient, auth_headers: dict, post_payload: dict, field: str, value: str
) -> None:
    response = client.post(POSTS_URL, json={**post_payload, field: value}, headers=auth_headers)

    assert response.status_code == 422
    assert error_fields(response) == {field}


def test_create_post_accepts_max_length_text(
    client: TestClient, auth_headers: dict, post_payload: dict
) -> None:
    payload = {
        **post_payload,
        "title": "가" * 100,
        "book_title": "가" * 200,
        "course_name": "가" * 100,
        "description": "가" * 2000,
    }

    response = client.post(POSTS_URL, json=payload, headers=auth_headers)

    assert response.status_code == 201
