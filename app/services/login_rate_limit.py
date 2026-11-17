"""로그인 실패 횟수 제한(IP별, 메모리). 웹 로그인(/auth/login)과 앱 로그인(/auth/token)이 함께 센다.

- IP당 10분에 실패 10번이면 그 뒤로는 비밀번호가 맞아도 429. 가장 오래된 실패가 10분을 넘기면 다시 할 수 있다.
- 성공한 로그인과 정지(403)는 비밀번호가 맞은 것이라 세지 않는다.
- 새 테이블·환경 변수 없이 서버 메모리에 둔다. 서버가 다시 시작되면 기록이 사라지고, 서버가 여러 대면 대마다 따로 센다.
  (지금 Railway는 한 대. 대수를 늘리면 DB에 두는 방식으로 바꿔야 한다)
- 요청은 스레드 풀에서 동시에 처리되므로 잠금으로 보호한다.
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


# 이 값 하나만 바꾸면 된다. 테스트는 monkeypatch로 바꾼다.
LOGIN_LIMIT = LoginLimit(max_failures=10, window_seconds=600)
# 기억하는 IP 수 상한. 넘으면 오래된 기록부터 비워 메모리가 끝없이 늘지 않게 한다.
MAX_TRACKED_IPS = 50_000

_failures: dict[str, deque[float]] = {}
_lock = threading.Lock()


def check(ip: str, now: float | None = None) -> None:
    """이 IP가 한도에 닿았으면 LoginRateLimitError(429, Retry-After)."""
    now = time.monotonic() if now is None else now
    with _lock:
        times = _recent(ip, now)
        if len(times) >= LOGIN_LIMIT.max_failures:
            retry_after = math.ceil(times[0] + LOGIN_LIMIT.window_seconds - now)
            raise LoginRateLimitError(retry_after=max(1, retry_after))


def record_failure(ip: str, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    with _lock:
        if ip not in _failures and len(_failures) >= MAX_TRACKED_IPS:
            _prune(now)
        times = _recent(ip, now)
        times.append(now)
        _failures[ip] = times


def reset() -> None:
    """기록을 모두 지운다. (테스트용)"""
    with _lock:
        _failures.clear()


def _recent(ip: str, now: float) -> deque[float]:
    times = _failures.get(ip, deque())
    while times and times[0] <= now - LOGIN_LIMIT.window_seconds:
        times.popleft()
    if not times:
        _failures.pop(ip, None)
    return times


def _prune(now: float) -> None:
    for ip in list(_failures):
        _recent(ip, now)
    # 그래도 가득 차 있으면(공격 중) 가장 먼저 넣은 IP부터 비운다.
    while len(_failures) >= MAX_TRACKED_IPS:
        _failures.pop(next(iter(_failures)))
