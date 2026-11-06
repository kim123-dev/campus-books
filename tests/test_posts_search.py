import pytest
from fastapi.testclient import TestClient

POSTS_URL = "/posts"


def search(client: TestClient, **params):
    return client.get(POSTS_URL, params=params)


def titles(response) -> list[str]:
    return [item["title"] for item in response.json()["items"]]


# 아래 순서대로 작성되므로 최신순 결과는 이 목록의 역순이다.
SAMPLE_POSTS = [
    # (title, book_title, course_name, price, status)
    ("자료구조 팝니다", "C로 쓴 자료구조", "자료구조", 15000, "ON_SALE"),
    ("운영체제 공룡책", "Operating System Concepts", "운영체제", 30000, "RESERVED"),
    ("알고리즘 책", "Introduction to Algorithms", "알고리즘", 25000, "SOLD"),
    ("연습문제집", "자료구조 문제 300", None, 5000, "ON_SALE"),
    ("선형대수 교재", "Linear Algebra", "선형대수학", 0, "ON_SALE"),
    ("자료구조 새책", "자료구조 원서", "자료구조", 20000, "RESERVED"),
]


@pytest.fixture
def sample_posts(client: TestClient, auth_headers: dict, create_post) -> None:
    for title, book_title, course_name, price, status in SAMPLE_POSTS:
        post = create_post(
            auth_headers, title=title, book_title=book_title, course_name=course_name, price=price
        )
        if status != "ON_SALE":
            client.patch(f"/posts/{post['id']}/status", json={"status": status}, headers=auth_headers)


# ---------- 필터 없음 ----------


def test_no_filter_returns_everything(client: TestClient, sample_posts) -> None:
    body = search(client).json()

    assert body["total"] == len(SAMPLE_POSTS)
    assert titles(search(client)) == [p[0] for p in reversed(SAMPLE_POSTS)]


# ---------- q ----------


def test_q_matches_title_book_title_or_course_name(client: TestClient, sample_posts) -> None:
    # "자료구조": 제목(팝니다, 새책), 교재명만(연습문제집)에서 일치
    response = search(client, q="자료구조")

    assert titles(response) == ["자료구조 새책", "연습문제집", "자료구조 팝니다"]
    assert response.json()["total"] == 3


def test_q_matches_course_name_only(client: TestClient, sample_posts) -> None:
    # "대수학"은 과목명 "선형대수학"에만 있다.
    assert titles(search(client, q="대수학")) == ["선형대수 교재"]


def test_q_is_case_insensitive(client: TestClient, sample_posts) -> None:
    for q in ("linear", "LINEAR", "LiNeAr"):
        assert titles(search(client, q=q)) == ["선형대수 교재"]


def test_q_is_partial_and_keeps_spaces(client: TestClient, sample_posts) -> None:
    assert titles(search(client, q="System Con")) == ["운영체제 공룡책"]
    # 띄어쓰기를 포함한 문자열 전체가 하나의 검색어다. (단어별 OR 검색이 아님)
    assert titles(search(client, q="자료구조 운영체제")) == []


@pytest.mark.parametrize("q", ["", "   "], ids=["빈값", "공백"])
def test_blank_q_is_ignored(client: TestClient, sample_posts, q: str) -> None:
    assert search(client, q=q).json()["total"] == len(SAMPLE_POSTS)


def test_q_strips_spaces(client: TestClient, sample_posts) -> None:
    assert titles(search(client, q="  공룡  ")) == ["운영체제 공룡책"]


def test_q_too_long_returns_422(client: TestClient) -> None:
    assert search(client, q="가" * 101).status_code == 422
    assert search(client, q="가" * 100).status_code == 200


# ---------- q의 특수문자 ----------


@pytest.fixture
def special_posts(auth_headers: dict, create_post) -> None:
    for title in ["100% 새책", "1000원 책", "100원 책", "a_b 노트", "axb 노트", "ab 노트", r"a\b 노트"]:
        create_post(auth_headers, title=title, book_title="교재", course_name=None)


def test_q_percent_is_literal(client: TestClient, special_posts) -> None:
    # %가 와일드카드라면 "1000원 책", "100원 책"도 걸린다.
    response = search(client, q="100%")

    assert titles(response) == ["100% 새책"]
    assert response.json()["total"] == 1


def test_q_underscore_is_literal(client: TestClient, special_posts) -> None:
    # _가 와일드카드(아무 한 글자)라면 "axb 노트"도 걸린다.
    response = search(client, q="a_b")

    assert titles(response) == ["a_b 노트"]
    assert response.json()["total"] == 1


def test_q_backslash_is_literal(client: TestClient, special_posts) -> None:
    # 이스케이프 문자(\) 자체도 일반 글자로 검색되어야 한다.
    assert titles(search(client, q="a\\b")) == ["a\\b 노트"]


@pytest.mark.parametrize("q", ["%", "_", "%%", "\\"])
def test_q_only_special_chars_does_not_match_everything(
    client: TestClient, special_posts, q: str
) -> None:
    expected = {"%": ["100% 새책"], "_": ["a_b 노트"], "%%": [], "\\": ["a\\b 노트"]}

    assert titles(search(client, q=q)) == expected[q]


# ---------- status ----------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("ON_SALE", ["선형대수 교재", "연습문제집", "자료구조 팝니다"]),
        ("RESERVED", ["자료구조 새책", "운영체제 공룡책"]),
        ("SOLD", ["알고리즘 책"]),
    ],
)
def test_filter_by_status(
    client: TestClient, sample_posts, status: str, expected: list[str]
) -> None:
    response = search(client, status=status)

    assert titles(response) == expected
    assert response.json()["total"] == len(expected)
    assert {item["status"] for item in response.json()["items"]} == {status}


@pytest.mark.parametrize("status", ["DELETED", "on_sale", ""], ids=["없는값", "소문자", "빈값"])
def test_invalid_status_returns_422(client: TestClient, status: str) -> None:
    assert search(client, status=status).status_code == 422


# ---------- course_name ----------


def test_filter_by_course_name_exact_match(client: TestClient, sample_posts) -> None:
    response = search(client, course_name="자료구조")

    assert titles(response) == ["자료구조 새책", "자료구조 팝니다"]
    assert response.json()["total"] == 2


def test_course_name_is_not_partial(client: TestClient, sample_posts) -> None:
    # 과목명 "선형대수학"은 "선형대수"로 걸리지 않는다. (부분 검색은 q 담당)
    assert titles(search(client, course_name="선형대수")) == []
    assert titles(search(client, course_name="선형대수학")) == ["선형대수 교재"]


def test_course_name_ignores_case_and_spaces(
    client: TestClient, auth_headers: dict, create_post
) -> None:
    create_post(auth_headers, title="OS 책", course_name="Operating Systems")
    create_post(auth_headers, title="OS 실습 책", course_name="Operating Systems Lab")

    assert titles(search(client, course_name="  operating SYSTEMS ")) == ["OS 책"]


def test_blank_course_name_is_ignored(client: TestClient, sample_posts) -> None:
    assert search(client, course_name="  ").json()["total"] == len(SAMPLE_POSTS)


# ---------- 가격 ----------


def test_min_price_only(client: TestClient, sample_posts) -> None:
    response = search(client, min_price=20000)

    assert titles(response) == ["자료구조 새책", "알고리즘 책", "운영체제 공룡책"]
    assert response.json()["total"] == 3


def test_max_price_only(client: TestClient, sample_posts) -> None:
    response = search(client, max_price=5000)

    assert titles(response) == ["선형대수 교재", "연습문제집"]
    assert response.json()["total"] == 2


def test_price_range_includes_both_ends(client: TestClient, sample_posts) -> None:
    # 15000과 25000이 정확히 경계값인 글이 있다.
    response = search(client, min_price=15000, max_price=25000)

    assert titles(response) == ["자료구조 새책", "알고리즘 책", "자료구조 팝니다"]


@pytest.mark.parametrize(
    ("price", "expected"),
    [(0, ["선형대수 교재"]), (15000, ["자료구조 팝니다"]), (30000, ["운영체제 공룡책"]), (1, [])],
    ids=["0원", "15000원", "30000원", "해당없음"],
)
def test_same_min_and_max_price_matches_exact_price(
    client: TestClient, sample_posts, price: int, expected: list[str]
) -> None:
    response = search(client, min_price=price, max_price=price)

    assert response.status_code == 200
    assert titles(response) == expected


def test_min_greater_than_max_returns_422(client: TestClient) -> None:
    response = search(client, min_price=20001, max_price=20000)

    assert response.status_code == 422
    assert "min_price는 max_price보다 클 수 없습니다." in response.text


@pytest.mark.parametrize(
    "params",
    [
        {"min_price": -1},
        {"max_price": -1},
        {"min_price": 10_000_001},
        {"max_price": "abc"},
        {"min_price": "1.5"},
    ],
    ids=["min음수", "max음수", "min상한초과", "max문자", "min실수"],
)
def test_invalid_price_returns_422(client: TestClient, params: dict) -> None:
    assert search(client, **params).status_code == 422


# ---------- 조합 ----------


def test_combined_q_status_and_price(client: TestClient, sample_posts) -> None:
    # 자료구조(3건) ∩ ON_SALE ∩ 10000원 이상 → "자료구조 팝니다"만
    response = search(client, q="자료구조", status="ON_SALE", min_price=10000, max_price=30000)

    assert titles(response) == ["자료구조 팝니다"]
    assert response.json()["total"] == 1


def test_combined_all_filters(client: TestClient, sample_posts) -> None:
    response = search(
        client, q="새책", status="RESERVED", course_name="자료구조", min_price=20000, max_price=20000
    )

    assert titles(response) == ["자료구조 새책"]


@pytest.mark.parametrize(
    "params",
    [
        {"q": "존재하지않는교재"},
        {"q": "자료구조", "status": "SOLD"},
        {"status": "SOLD", "max_price": 10000},
        {"course_name": "운영체제", "min_price": 30001},
    ],
    ids=["검색어없음", "검색어+상태", "상태+가격", "과목+가격"],
)
def test_no_result(client: TestClient, sample_posts, params: dict) -> None:
    response = search(client, **params)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "size": 20}


# ---------- 필터 + 페이지네이션 + 정렬 ----------


@pytest.fixture
def many_posts(client: TestClient, auth_headers: dict, create_post) -> list[str]:
    """자료구조 글 5개와 다른 글 4개를 섞어 만든다. 자료구조 글 제목을 최신순으로 돌려준다."""
    matched = []
    for i in range(9):
        if i % 2 == 0:
            title = f"자료구조 {i}"
            matched.append(title)
        else:
            title = f"운영체제 {i}"
        create_post(auth_headers, title=title, book_title="교재", course_name=None)
    return list(reversed(matched))


@pytest.mark.parametrize(
    ("page", "expected_slice"),
    [(1, slice(0, 2)), (2, slice(2, 4)), (3, slice(4, 5)), (4, slice(0, 0))],
    ids=["1페이지", "2페이지", "마지막_일부", "마지막_다음"],
)
def test_filter_with_pagination_uses_filtered_total(
    client: TestClient, many_posts: list[str], page: int, expected_slice: slice
) -> None:
    response = search(client, q="자료구조", page=page, size=2)

    body = response.json()
    assert titles(response) == many_posts[expected_slice]
    # 전체 글은 9개지만 total은 필터에 맞는 5개여야 한다.
    assert body["total"] == 5
    assert body["page"] == page
    assert body["size"] == 2


def test_pages_together_cover_filtered_results_in_newest_order(
    client: TestClient, many_posts: list[str]
) -> None:
    collected: list[str] = []
    for page in (1, 2, 3):
        collected += titles(search(client, q="자료구조", page=page, size=2))

    # 페이지를 이어 붙이면 빠짐이나 중복 없이 최신순 전체가 되어야 한다.
    assert collected == many_posts


def test_filter_total_with_status_and_pagination(client: TestClient, sample_posts) -> None:
    response = search(client, status="ON_SALE", page=2, size=2)

    assert titles(response) == ["자료구조 팝니다"]
    assert response.json()["total"] == 3


def test_invalid_pagination_still_returns_422_with_filters(client: TestClient) -> None:
    assert search(client, q="자료구조", page=0).status_code == 422
    assert search(client, status="ON_SALE", size=101).status_code == 422
