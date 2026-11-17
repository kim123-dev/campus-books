"""로그인 실패 횟수 제한(메모리). 웹 로그인(/auth/login)과 앱 로그인(/auth/token)이 함께 센다.

캠퍼스 Wi-Fi는 많은 학생이 IP 하나(NAT)를 함께 쓴다. IP만 엄격하게 세면 한 사람의 실수나 공격 때문에
같은 건물의 다른 학생까지 로그인하지 못하므로, 두 가지를 따로 센다.
- 이메일별(엄격): 10분에 실패 10번이면 그 이메일은 막는다. 한 계정의 비밀번호를 맞혀 보는 공격을 IP를 바꿔도 막는다.
  없는 이메일도 똑같이 세어, 막히는지 여부로 가입 여부를 알 수 없게 한다.
- IP별(완화): 10분에 실패 100번. 여러 계정을 돌려 가며 맞혀 보는 공격을 막되 공유 IP의 다른 학생은 막지 않는다.
둘 중 하나라도 한도에 닿으면 비밀번호가 맞아도 429. 성공한 로그인과 정지(403)는 세지 않는다.

새 테이블·환경 변수 없이 서버 메모리에 둔다. 서버가 다시 시작되면 기록이 사라지고, 서버가 여러 대면 대마다 따로 센다.
(지금 Railway는 한 대. 대수를 늘리면 DB에 두는 방식으로 바꿔야 한다) 요청은 스레드 풀에서 동시에 처리되므로 잠금으로 보호한다.
"""

import math
import threading
import time
from collections import deque
from dataclasses import dataclass

from app.core.exceptions import LoginRateLimitError


@dataclass(frozen=True)
class LoginLimit:
    max_failures: int
    window_seconds: int


# 이 값들만 바꾸면 된다. 테스트는 monkeypatch로 바꾼다.
EMAIL_LIMIT = LoginLimit(max_failures=10, window_seconds=600)
IP_LIMIT = LoginLimit(max_failures=100, window_seconds=600)
# 기억하는 키(이메일·IP) 수 상한. 넘으면 오래된 기록부터 비워 메모리가 끝없이 늘지 않게 한다.
MAX_TRACKED_KEYS = 100_000

# 키: ("email", 정리한 이메일) 또는 ("ip", 주소)
_failures: dict[tuple[str, str], deque[float]] = {}
_lock = threading.Lock()


def normalize_email(email: str) -> str:
    """같은 이메일을 같은 키로 센다. 대소문자와 앞뒤 공백 차이로 한도를 피하지 못하게."""
    return email.strip().lower()


def check(email: str, ip: str, now: float | None = None) -> None:
    """이메일·IP 중 하나라도 한도에 닿았으면 LoginRateLimitError(429). 둘 다면 더 오래 기다려야 하는 쪽을 알려준다."""
    now = time.monotonic() if now is None else now
    waits = []
    with _lock:
        for key, limit in _keys(email, ip):
            times = _recent(key, limit, now)
            if len(times) >= limit.max_failures:
                waits.append(math.ceil(times[0] + limit.window_seconds - now))
    if waits:
        raise LoginRateLimitError(retry_after=max(1, max(waits)))


def record_failure(email: str, ip: str, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    with _lock:
        for key, limit in _keys(email, ip):
            if key not in _failures and len(_failures) >= MAX_TRACKED_KEYS:
                _prune(now)
            times = _recent(key, limit, now)
            times.append(now)
            _failures[key] = times


def reset() -> None:
    """기록을 모두 지운다. (테스트용)"""
    with _lock:
        _failures.clear()


def _keys(email: str, ip: str) -> list[tuple[tuple[str, str], LoginLimit]]:
    return [(("email", normalize_email(email)), EMAIL_LIMIT), (("ip", ip), IP_LIMIT)]


def _limit_of(key: tuple[str, str]) -> LoginLimit:
    return EMAIL_LIMIT if key[0] == "email" else IP_LIMIT


def _recent(key: tuple[str, str], limit: LoginLimit, now: float) -> deque[float]:
    times = _failures.get(key, deque())
    while times and times[0] <= now - limit.window_seconds:
        times.popleft()
    if not times:
        _failures.pop(key, None)
    return times


def _prune(now: float) -> None:
    for key in list(_failures):
        _recent(key, _limit_of(key), now)
    # 그래도 가득 차 있으면(공격 중) 가장 먼저 넣은 키부터 비운다.
    while len(_failures) >= MAX_TRACKED_KEYS:
        _failures.pop(next(iter(_failures)))
