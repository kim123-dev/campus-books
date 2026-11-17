"""로그인 실패 횟수 제한(메모리): 이메일별 10분 10번(엄격), IP별 10분 100번(완화), 프록시 뒤의 접속 주소 읽기."""

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.core.client_ip import client_ip
from app.core.exceptions import LoginRateLimitError
from app.services import login_rate_limit
from app.services.login_rate_limit import LoginLimit
from tests.conftest import TEST_PASSWORD

EMAIL = "student@campus.ac.kr"
LIMITED = {"detail": "로그인 실패가 너무 많습니다. 잠시 후 다시 시도해 주세요."}


@pytest.fixture
def student(make_auth_headers) -> dict:
    return make_auth_headers(EMAIL, "책벌레")


def web_login(client: TestClient, email: str = EMAIL, password: str = TEST_PASSWORD, ip: str | None = None):
    headers = {"X-Real-IP": ip} if ip else {}
    return client.post("/auth/login", data={"username": email, "password": password}, headers=headers)


def app_login(client: TestClient, email: str = EMAIL, password: str = TEST_PASSWORD, ip: str | None = None):
    headers = {"X-Real-IP": ip} if ip else {}
    return client.post("/auth/token", data={"username": email, "password": password}, headers=headers)


def fail(client: TestClient, times: int, email: str = EMAIL, ip: str | None = None, login=web_login) -> None:
    for _ in range(times):
        assert login(client, email, "wrong-password", ip).status_code == 401


# ---------- 이메일별(엄격) ----------


def test_eleventh_attempt_for_same_email_is_429(client, student) -> None:
    fail(client, 10)
    # 한도에 닿으면 비밀번호가 맞아도 막는다. (맞는 비밀번호를 찾아낸 순간에도 알 수 없게)
    response = web_login(client)
    assert response.status_code == 429 and response.json() == LIMITED
    assert 1 <= int(response.headers["Retry-After"]) <= 600


def test_same_email_is_blocked_even_from_different_ips(client, student) -> None:
    for n in range(10):
        assert web_login(client, password="wrong", ip=f"8.8.{n}.1").status_code == 401
    assert web_login(client, ip="1.1.1.1").status_code == 429


def test_email_is_counted_case_and_space_insensitively(client, student) -> None:
    variants = ["Student@Campus.ac.kr", "STUDENT@CAMPUS.AC.KR", " student@campus.ac.kr "]
    for n in range(10):
        assert web_login(client, email=variants[n % 3], password="wrong").status_code == 401
    assert web_login(client).status_code == 429
    assert login_rate_limit.normalize_email("  A@B.Kr ") == "a@b.kr"


def test_unknown_email_is_counted_the_same_way(client, student) -> None:
    """없는 이메일도 10번에서 막혀, 막히는지 여부로 가입 여부를 알 수 없다."""
    statuses = [web_login(client, email="nobody@campus.ac.kr", password="x").status_code for _ in range(11)]
    assert statuses == [401] * 10 + [429]


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


# ---------- IP별(완화): 캠퍼스 공유 IP ----------


def test_shared_ip_with_different_emails_is_not_blocked_before_ip_limit(client, student) -> None:
    """학교 Wi-Fi(같은 IP)에서 여러 학생이 비밀번호를 틀려도, IP 한도(100) 전에는 다른 학생이 막히지 않는다."""
    campus = "61.43.1.1"
    for n in range(99):
        assert web_login(client, email=f"student{n % 30}@campus.ac.kr", password="wrong", ip=campus).status_code == 401
    assert web_login(client, ip=campus).status_code == 200  # 100번째 요청: 내 계정은 그대로 로그인


def test_ip_limit_blocks_spraying_many_accounts(client, student) -> None:
    campus = "61.43.1.1"
    for n in range(100):
        assert web_login(client, email=f"victim{n}@campus.ac.kr", password="wrong", ip=campus).status_code == 401
    assert web_login(client, ip=campus).status_code == 429
    assert web_login(client, ip="1.0.0.1").status_code == 200  # 다른 IP는 영향 없음


def test_window_expiry_and_retry_after_use_the_longer_wait(monkeypatch) -> None:
    monkeypatch.setattr(login_rate_limit, "EMAIL_LIMIT", LoginLimit(max_failures=2, window_seconds=600))
    monkeypatch.setattr(login_rate_limit, "IP_LIMIT", LoginLimit(max_failures=3, window_seconds=900))
    login_rate_limit.record_failure("a@campus.ac.kr", "4.4.4.4", now=0)
    login_rate_limit.record_failure("b@campus.ac.kr", "4.4.4.4", now=100)
    login_rate_limit.record_failure("b@campus.ac.kr", "4.4.4.4", now=200)
    # b는 이메일 한도(2)에, 4.4.4.4는 IP 한도(3)에 닿았다. 더 오래 기다려야 하는 쪽(IP: 0+900-300)을 알려준다.
    with pytest.raises(LoginRateLimitError) as caught:
        login_rate_limit.check("b@campus.ac.kr", "4.4.4.4", now=300)
    assert caught.value.retry_after == 600
    # 다른 IP에서도 b의 이메일 기록(100, 200)이 남아 있는 동안은 막힌다.
    with pytest.raises(LoginRateLimitError):
        login_rate_limit.check("b@campus.ac.kr", "8.8.8.8", now=650)
    login_rate_limit.check("b@campus.ac.kr", "8.8.8.8", now=700)  # 100이 600초 창을 벗어남
    login_rate_limit.check("c@campus.ac.kr", "4.4.4.4", now=900)  # IP 기록 0이 900초 창을 벗어남


# ---------- 프록시 뒤의 접속 주소 ----------


def make_request(forwarded: list[str], peer: str = "100.64.0.7", real_ip: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", value.encode()) for value in forwarded]
    if real_ip is not None:
        headers.append((b"x-real-ip", real_ip.encode()))
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


@pytest.mark.parametrize(
    ("forwarded", "expected"),
    [
        (["8.8.4.4"], "8.8.4.4"),
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
def test_client_ip_without_real_ip_picks_rightmost_public_address(forwarded, expected) -> None:
    assert client_ip(make_request(forwarded)) == expected


def test_x_real_ip_wins_over_forwarded_for() -> None:
    """Railway 엣지가 넣는 X-Real-IP를 먼저 쓴다. X-Forwarded-For 오른쪽의 CDN 주소는 요청마다 바뀔 수 있다."""
    assert client_ip(make_request(["8.8.4.4, 151.101.1.1"], real_ip="8.8.4.4")) == "8.8.4.4"
    assert client_ip(make_request(["151.101.1.1"], real_ip="  ")) == "151.101.1.1"  # 비었거나 잘못된 값이면 무시


def test_same_real_ip_is_counted_together_even_if_forwarded_for_changes(client, student) -> None:
    for n in range(100):
        response = client.post(
            "/auth/login",
            data={"username": f"user{n}@campus.ac.kr", "password": "wrong"},
            headers={"X-Real-IP": "9.9.9.9", "X-Forwarded-For": f"9.9.9.9, 151.101.{n}.1"},
        )
        assert response.status_code == 401
    assert web_login(client, ip="9.9.9.9").status_code == 429
