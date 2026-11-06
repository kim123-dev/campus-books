import os

# 앱 import 전에 테스트 전용 값을 넣어, .env 없이도 테스트가 돌고
# 개발용 DB(dev.db)를 건드리지 않게 한다.
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


# 테스트마다 실제 서버를 띄우지 않고 앱을 직접 호출하기 위한 클라이언트
@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
