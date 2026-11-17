"""로그인 실패 횟수 제한(IP별, 메모리)과 프록시 뒤의 접속 주소 읽기."""

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.core.client_ip import client_ip
from app.services import login_rate_limit
from app.services.login_rate_limit import LoginLimit
from tests.conftest import TEST_PASSWORD

EMAIL = "student@campus.ac.kr"
LIMITED = {"detail": "로그인 실패가 너무 많습니다. 잠시 후 다시 시도해 주세요."}


@pytest.fixture
def student(make_auth_headers) -> dict:
    return make_auth_headers(EMAIL, "책벌레")


def web_login(client: TestClient, password: str = TEST_PASSWORD, ip: str | None = None):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return client.post("/auth/login", data={"username": EMAIL, "password": password}, headers=headers)


def app_login(client: TestClient, password: str = TEST_PASSWORD, ip: str | None = None):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return client.post("/auth/token", data={"username": EMAIL, "password": password}, headers=headers)


def fail(client: TestClient, times: int, ip: str | None = None, login=web_login) -> None:
    for _ in range(times):
        assert login(client, "wrong-password", ip).status_code == 401


# ---------- 한도 ----------


def test_eleventh_attempt_after_ten_failures_is_429(client, student) -> None:
    fail(client, 10)
    # 한도에 닿으면 비밀번호가 맞아도 막는다. (맞는 비밀번호를 찾아낸 순간에도 알 수 없게)
    response = web_login(client)
    assert response.status_code == 429 and response.json() == LIMITED
    assert 1 <= int(response.headers["Retry-After"]) <= 600


def test_web_and_app_login_share_the_count(client, student) -> None:
    fail(client, 5, login=web_login)
    fail(client, 5, login=app_login)
    assert app_login(client).status_code == 429
    assert web_login(client).status_code == 429


def test_successful_logins_are_not_counted(client, student) -> None:
    for _ in range(15):
        assert web_login(client).status_code == 200
    fail(client, 9)
    assert app_login(client).status_code == 200


def test_unknown_email_failures_are_counted(client) -> None:
    for _ in range(10):
        client.post("/auth/login", data={"username": "nobody@campus.ac.kr", "password": "x"})
    assert web_login(client).status_code == 429


def test_different_ips_are_counted_separately(client, student) -> None:
    fail(client, 10, ip="8.8.8.8")
    assert web_login(client, ip="8.8.8.8").status_code == 429
    assert web_login(client, ip="1.0.0.1").status_code == 200
    assert web_login(client).status_code == 200  # 헤더 없는 접속(testclient)도 따로


def test_window_expiry_allows_again(monkeypatch) -> None:
    monkeypatch.setattr(login_rate_limit, "LOGIN_LIMIT", LoginLimit(max_failures=2, window_seconds=600))
    login_rate_limit.record_failure("4.4.4.4", now=0)
    login_rate_limit.record_failure("4.4.4.4", now=100)
    with pytest.raises(Exception) as caught:
        login_rate_limit.check("4.4.4.4", now=500)
    assert caught.value.retry_after == 100  # 가장 오래된 실패(0초)가 600초에 빠진다.
    login_rate_limit.check("4.4.4.4", now=600)  # 하나가 창 밖으로 나가 다시 시도할 수 있다.


# ---------- 프록시 뒤의 접속 주소 ----------


def test_spoofed_left_entries_do_not_bypass_limit(client, student) -> None:
    """요청한 사람이 X-Forwarded-For 왼쪽에 아무 값이나 적어도, 프록시가 붙인 오른쪽 주소로 센다."""
    for n in range(10):
        response = client.post(
            "/auth/login",
            data={"username": EMAIL, "password": "wrong"},
            headers={"X-Forwarded-For": f"10.{n}.0.1, 172.16.{n}.1, 9.9.9.9"},
        )
        assert response.status_code == 401
    assert web_login(client, ip="1.1.1.1, 9.9.9.9").status_code == 429


def make_request(forwarded: list[str], peer: str = "100.64.0.7", real_ip: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", value.encode()) for value in forwarded]
    if real_ip is not None:
        headers.append((b"x-real-ip", real_ip.encode()))
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


@pytest.mark.parametrize(
    ("forwarded", "expected"),
    [
        (["8.8.4.4"], "8.8.4.4"),  # 프록시가 덮어쓴 경우
        (["1.2.3.4, 8.8.4.4"], "8.8.4.4"),  # 왼쪽(지어낸 값)은 보지 않는다
        (["8.8.4.4, 10.0.0.2, 100.64.0.3"], "8.8.4.4"),  # 프록시 내부망 주소는 건너뛴다
        (["fd12::1, 2001:4860::8888, fd00::3"], "2001:4860::8888"),
        (["8.8.4.4:443"], "8.8.4.4"),
        (["[2001:4860::8888]:443"], "2001:4860::8888"),
        (["::ffff:8.8.4.4"], "8.8.4.4"),
        (["1.2.3.4", "8.8.4.4"], "8.8.4.4"),  # 헤더가 두 줄로 와도 마지막 것부터
        (["garbage, 10.0.0.1"], "100.64.0.7"),  # 공인 주소가 없으면 접속 주소
        ([], "100.64.0.7"),
    ],
)
def test_client_ip_picks_rightmost_public_address(forwarded, expected) -> None:
    assert client_ip(make_request(forwarded)) == expected


def test_x_real_ip_wins_over_forwarded_for() -> None:
    """Railway 엣지가 넣는 X-Real-IP를 먼저 쓴다. X-Forwarded-For 오른쪽의 CDN 주소는 요청마다 바뀔 수 있다."""
    request = make_request(["8.8.4.4, 151.101.1.1"], real_ip="8.8.4.4")
    assert client_ip(request) == "8.8.4.4"
    assert client_ip(make_request(["151.101.1.1"], real_ip="  ")) == "151.101.1.1"  # 비었거나 잘못된 값이면 무시


def test_same_real_ip_is_counted_together_even_if_forwarded_for_changes(client, student) -> None:
    for n in range(10):
        response = client.post(
            "/auth/login",
            data={"username": EMAIL, "password": "wrong"},
            headers={"X-Real-IP": "9.9.9.9", "X-Forwarded-For": f"9.9.9.9, 151.101.{n}.1"},
        )
        assert response.status_code == 401
    blocked = client.post("/auth/login", data={"username": EMAIL, "password": TEST_PASSWORD}, headers={"X-Real-IP": "9.9.9.9"})
    assert blocked.status_code == 429
