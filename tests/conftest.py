import os

# 앱 import 전에 테스트 전용 값을 넣어, .env 없이도 테스트가 돌고
# 개발용 DB(dev.db)를 건드리지 않게 한다.
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "sqlite://")

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

# 인메모리 SQLite는 연결마다 DB가 따로 생기므로, StaticPool로 연결 하나를 공유한다.
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


# 테스트마다 빈 테이블에서 시작해, 테스트끼리 데이터가 섞이지 않게 한다.
@pytest.fixture
def db_session() -> Iterator[Session]:
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


# 앱의 get_db를 테스트 세션으로 바꿔 끼워, 실제 DB 대신 인메모리 DB를 쓰게 한다.
@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()
