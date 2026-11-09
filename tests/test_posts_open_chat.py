from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import ALGORITHM, create_access_token
from app.schemas.post import MAX_OPEN_CHAT_URL_LENGTH, OPEN_CHAT_URL_ERROR

VALID_URL = "https://open.kakao.com/o/sAbC123x"
PREFIX = "https://open.kakao.com/"


@pytest.fixture
def owner(make_auth_headers) -> dict:
    return make_auth_headers("owner@campus.ac.kr", "작성자")


@pytest.fixture
def buyer(make_auth_headers) -> dict:
    return make_auth_headers("buyer@campus.ac.kr", "구매자")


@pytest.fixture
def post(owner: dict, create_post) -> dict:
    return create_post(owner, open_chat_url=VALID_URL)


def open_chat_error(response) -> list[str]:
    """422 응답에서 open_chat_url 필드의 에러 메시지만 모은다."""
    return [err["msg"] for err in response.json()["detail"] if err["loc"][-1] == "open_chat_url"]


# ---------- 작성: 허용되는 주소 ----------


@pytest.mark.parametrize(
    "url",
    [
        VALID_URL,
        "https://open.kakao.com/me/campus_seller",
        "https://open.kakao.com/o/gAbc-12_x?lang=ko&ref=a%20b",
    ],
)
def test_create_accepts_kakao_open_chat_url(client: TestClient, owner: dict, create_post, url: str) -> None:
    created = create_post(owner, open_chat_url=url)

    assert created["open_chat_url"] == url


def test_create_trims_surrounding_spaces(client: TestClient, owner: dict, create_post) -> None:
    created = create_post(owner, open_chat_url=f"  {VALID_URL}  ")

    assert created["open_chat_url"] == VALID_URL


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_create_without_url_stores_null(client: TestClient, owner: dict, create_post, blank) -> None:
    created = create_post(owner, open_chat_url=blank)

    assert created["open_chat_url"] is None


def test_create_url_is_optional(client: TestClient, owner: dict, post_payload: dict) -> None:
    # 필드를 아예 보내지 않아도 된다. (기존 클라이언트 호환)
    response = client.post("/posts", json=post_payload, headers=owner)

    assert response.status_code == 201
    assert response.json()["open_chat_url"] is None


# ---------- 작성: 거절되는 주소 (422) ----------

REJECTED_URLS = [
    pytest.param("javascript:alert(1)", id="javascript"),
    pytest.param("JaVaScRiPt:alert(document.cookie)", id="javascript-mixed-case"),
    pytest.param(" javascript:alert(1)", id="javascript-leading-space"),
    pytest.param("data:text/html,<script>alert(1)</script>", id="data-uri"),
    pytest.param("http://open.kakao.com/o/sAbC123x", id="http-not-https"),
    pytest.param("https://open.kakao.com.evil.com/o/x", id="lookalike-subdomain"),
    pytest.param("https://evil.com/?https://open.kakao.com/o/x", id="other-domain-with-prefix-in-query"),
    pytest.param("https://evil.com/https://open.kakao.com/o/x", id="other-domain-with-prefix-in-path"),
    pytest.param("//open.kakao.com/o/x", id="protocol-relative"),
    pytest.param("HTTPS://OPEN.KAKAO.COM/o/x", id="uppercase"),
    pytest.param("https://open.kakao.com/", id="prefix-only"),
    pytest.param("https://open.kakao.com", id="no-trailing-slash"),
    pytest.param('https://open.kakao.com/o/x"><script>alert(1)</script>', id="attribute-breakout"),
    pytest.param("https://open.kakao.com/o/x' onmouseover='alert(1)", id="quote-and-space"),
    pytest.param("https://open.kakao.com/o/x\\@evil.com", id="backslash"),
    pytest.param("https://open.kakao.com/o/x\njavascript:alert(1)", id="newline"),
    pytest.param("https://open.kakao.com/o/x#<img src=x onerror=alert(1)>", id="fragment-html"),
]


@pytest.mark.parametrize("url", REJECTED_URLS)
def test_create_rejects_non_kakao_url(client: TestClient, owner: dict, post_payload: dict, url: str) -> None:
    response = client.post("/posts", json={**post_payload, "open_chat_url": url}, headers=owner)

    assert response.status_code == 422
    assert open_chat_error(response)


def test_reject_message_is_user_friendly(client: TestClient, owner: dict, post_payload: dict) -> None:
    response = client.post(
        "/posts", json={**post_payload, "open_chat_url": "javascript:alert(1)"}, headers=owner
    )

    assert OPEN_CHAT_URL_ERROR in open_chat_error(response)[0]


def test_rejected_url_does_not_create_post(client: TestClient, owner: dict, post_payload: dict) -> None:
    client.post("/posts", json={**post_payload, "open_chat_url": "javascript:alert(1)"}, headers=owner)

    assert client.get("/posts").json()["total"] == 0


def test_create_accepts_max_length(client: TestClient, owner: dict, create_post) -> None:
    url = PREFIX + "o/" + "a" * (MAX_OPEN_CHAT_URL_LENGTH - len(PREFIX) - 2)
    assert len(url) == MAX_OPEN_CHAT_URL_LENGTH

    assert create_post(owner, open_chat_url=url)["open_chat_url"] == url


def test_create_rejects_too_long_url(client: TestClient, owner: dict, post_payload: dict) -> None:
    url = PREFIX + "o/" + "a" * (MAX_OPEN_CHAT_URL_LENGTH - len(PREFIX) - 1)
    assert len(url) == MAX_OPEN_CHAT_URL_LENGTH + 1

    response = client.post("/posts", json={**post_payload, "open_chat_url": url}, headers=owner)

    assert response.status_code == 422
    assert [err["type"] for err in response.json()["detail"]] == ["string_too_long"]


def test_create_rejects_non_string_url(client: TestClient, owner: dict, post_payload: dict) -> None:
    response = client.post("/posts", json={**post_payload, "open_chat_url": 123}, headers=owner)

    assert response.status_code == 422


# ---------- 수정 ----------


def test_update_sets_url(client: TestClient, owner: dict, create_post) -> None:
    created = create_post(owner)
    assert created["open_chat_url"] is None

    response = client.patch(f"/posts/{created['id']}", json={"open_chat_url": VALID_URL}, headers=owner)

    assert response.status_code == 200
    assert response.json()["open_chat_url"] == VALID_URL
    assert client.get(f"/posts/{created['id']}", headers=owner).json()["open_chat_url"] == VALID_URL


def test_update_changes_url(client: TestClient, owner: dict, post: dict) -> None:
    new_url = "https://open.kakao.com/o/newLink9"

    response = client.patch(f"/posts/{post['id']}", json={"open_chat_url": new_url}, headers=owner)

    assert response.json()["open_chat_url"] == new_url


@pytest.mark.parametrize("blank", [None, "", "  "])
def test_update_blank_clears_url(client: TestClient, owner: dict, post: dict, blank) -> None:
    response = client.patch(f"/posts/{post['id']}", json={"open_chat_url": blank}, headers=owner)

    assert response.status_code == 200
    assert response.json()["open_chat_url"] is None


def test_update_without_field_keeps_url(client: TestClient, owner: dict, post: dict) -> None:
    response = client.patch(f"/posts/{post['id']}", json={"price": 1000}, headers=owner)

    assert response.json()["open_chat_url"] == VALID_URL


@pytest.mark.parametrize("url", REJECTED_URLS)
def test_update_rejects_non_kakao_url_and_keeps_old(
    client: TestClient, owner: dict, post: dict, url: str
) -> None:
    response = client.patch(f"/posts/{post['id']}", json={"open_chat_url": url}, headers=owner)

    assert response.status_code == 422
    assert open_chat_error(response)
    assert client.get(f"/posts/{post['id']}", headers=owner).json()["open_chat_url"] == VALID_URL


def test_update_by_other_user_is_forbidden(client: TestClient, buyer: dict, post: dict) -> None:
    response = client.patch(f"/posts/{post['id']}", json={"open_chat_url": None}, headers=buyer)

    assert response.status_code == 403


def test_status_change_response_includes_url(client: TestClient, owner: dict, post: dict) -> None:
    response = client.patch(f"/posts/{post['id']}/status", json={"status": "RESERVED"}, headers=owner)

    assert response.json()["open_chat_url"] == VALID_URL


# ---------- 상세: 로그인한 사용자에게만 링크를 준다 ----------


def test_detail_shows_url_to_logged_in_buyer(client: TestClient, buyer: dict, post: dict) -> None:
    response = client.get(f"/posts/{post['id']}", headers=buyer)

    assert response.status_code == 200
    assert response.json()["open_chat_url"] == VALID_URL


def test_detail_shows_url_to_owner(client: TestClient, owner: dict, post: dict) -> None:
    assert client.get(f"/posts/{post['id']}", headers=owner).json()["open_chat_url"] == VALID_URL


def test_detail_hides_url_without_token(client: TestClient, post: dict) -> None:
    response = client.get(f"/posts/{post['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["open_chat_url"] is None
    # 링크만 비우고 나머지 글 내용은 그대로 보여준다.
    assert body["title"] == post["title"]


def test_detail_hides_url_with_expired_token(client: TestClient, buyer: dict, post: dict) -> None:
    buyer_id = client.get("/users/me", headers=buyer).json()["id"]
    expired = create_access_token(buyer_id, expires_delta=timedelta(seconds=-1))

    response = client.get(f"/posts/{post['id']}", headers={"Authorization": f"Bearer {expired}"})

    assert response.status_code == 200
    assert response.json()["open_chat_url"] is None


@pytest.mark.parametrize(
    "authorization",
    [
        pytest.param("Bearer not-a-jwt", id="garbage"),
        pytest.param(
            "Bearer " + jwt.encode({"sub": "1", "exp": 4102444800}, "attacker-key", algorithm=ALGORITHM),
            id="wrong-signature",
        ),
        pytest.param(
            "Bearer " + jwt.encode({"sub": "abc", "exp": 4102444800}, get_settings().SECRET_KEY, algorithm=ALGORITHM),
            id="non-integer-sub",
        ),
        pytest.param("Bearer " + create_access_token(9999), id="deleted-user"),
        pytest.param("Basic dXNlcjpwYXNz", id="not-bearer"),
    ],
)
def test_detail_hides_url_with_invalid_token(client: TestClient, post: dict, authorization: str) -> None:
    response = client.get(f"/posts/{post['id']}", headers={"Authorization": authorization})

    assert response.status_code == 200
    assert response.json()["open_chat_url"] is None


def test_tampered_token_is_hidden(client: TestClient, buyer: dict, post: dict) -> None:
    # 정상 토큰의 서명 부분을 바꿔 변조한다.
    token = buyer["Authorization"].removeprefix("Bearer ")
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[::-1]}"

    response = client.get(f"/posts/{post['id']}", headers={"Authorization": f"Bearer {tampered}"})

    assert response.status_code == 200
    assert response.json()["open_chat_url"] is None


def test_hiding_url_does_not_erase_it(client: TestClient, owner: dict, post: dict) -> None:
    # 비로그인 응답에서 null로 비운 값이 DB에 저장되면 안 된다.
    client.get(f"/posts/{post['id']}")
    client.patch(f"/posts/{post['id']}", json={"price": 1000}, headers=owner)

    assert client.get(f"/posts/{post['id']}", headers=owner).json()["open_chat_url"] == VALID_URL


def test_missing_post_is_still_404_without_token(client: TestClient) -> None:
    assert client.get("/posts/9999").status_code == 404


# ---------- 목록에는 링크를 넣지 않는다 ----------


def test_list_does_not_include_url(client: TestClient, buyer: dict, post: dict) -> None:
    item = client.get("/posts", headers=buyer).json()["items"][0]

    assert "open_chat_url" not in item


def test_my_posts_does_not_include_url(client: TestClient, owner: dict, post: dict) -> None:
    item = client.get("/users/me/posts", headers=owner).json()["items"][0]

    assert "open_chat_url" not in item


# ---------- XSS 시도 문자열 ----------


def test_xss_in_url_is_never_stored(client: TestClient, owner: dict, post_payload: dict) -> None:
    attempts = [
        "javascript:alert(1)",
        '"><script>alert(1)</script>',
        "<img src=x onerror=alert(1)>",
        "https://open.kakao.com/o/x\"onclick=\"alert(1)",
        "https://open.kakao.com/o/<svg/onload=alert(1)>",
    ]
    for url in attempts:
        response = client.post("/posts", json={**post_payload, "open_chat_url": url}, headers=owner)
        assert response.status_code == 422, url

    assert client.get("/posts").json()["total"] == 0


def test_xss_in_other_fields_is_returned_as_plain_text(
    client: TestClient, owner: dict, buyer: dict, create_post
) -> None:
    # 다른 칸의 스크립트 문자열은 저장되지만, 서버가 바꾸지 않고 글자 그대로 돌려준다.
    # (화면은 textContent로만 넣으므로 실행되지 않는다. tests/test_static.py 참고)
    script = "<script>alert(1)</script>"
    created = create_post(owner, title=script, description=script, open_chat_url=VALID_URL)

    body = client.get(f"/posts/{created['id']}", headers=buyer).json()

    assert body["title"] == script
    assert body["description"] == script
    assert body["open_chat_url"] == VALID_URL
