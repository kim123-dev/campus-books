import os

# 앱 import 전에 테스트 전용 값을 넣어, .env 없이도 테스트가 돌고
# 개발용 DB(dev.db)를 건드리지 않게 한다.
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "sqlite://")

from collections.abc import Callable, Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import image_storage  # noqa: E402

# 인메모리 SQLite는 연결마다 DB가 따로 생기므로, StaticPool로 연결 하나를 공유한다.
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


# 사진 업로드 테스트가 프로젝트의 uploads/ 폴더에 파일을 남기지 않도록, 모든 테스트에서
# 사진 폴더를 테스트마다 새로 만든 임시 폴더로 바꿔 둔다.
@pytest.fixture(autouse=True)
def image_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "uploads" / "posts"
    monkeypatch.setattr(image_storage, "get_image_dir", lambda: directory)
    return directory


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


TEST_PASSWORD = "password123"


# 가입 + 로그인을 거쳐 Authorization 헤더를 만든다. 여러 사용자가 필요한 테스트를 위해 팩토리로 둔다.
@pytest.fixture
def make_auth_headers(client: TestClient) -> Callable[..., dict[str, str]]:
    def _make(email: str = "seller@campus.ac.kr", nickname: str = "판매자") -> dict[str, str]:
        signup = client.post(
            "/auth/signup",
            json={"email": email, "password": TEST_PASSWORD, "nickname": nickname},
        )
        assert signup.status_code == 201, signup.text
        login = client.post("/auth/login", data={"username": email, "password": TEST_PASSWORD})
        return {"Authorization": f"Bearer {login.json()['access_token']}"}

    return _make


@pytest.fixture
def auth_headers(make_auth_headers: Callable[..., dict[str, str]]) -> dict[str, str]:
    return make_auth_headers()


# 검증 테스트에서 필드 하나만 바꿔 쓰도록, 통과하는 기본 요청 본문을 제공한다.
@pytest.fixture
def post_payload() -> dict:
    return {
        "title": "자료구조 교재 팝니다",
        "book_title": "C언어로 쉽게 풀어쓴 자료구조",
        "course_name": "자료구조",
        "condition": "GOOD",
        "price": 15000,
        "description": "필기 거의 없어요.",
    }


# 글 작성 API를 호출하고 성공을 확인한 뒤 응답 본문을 돌려준다.
@pytest.fixture
def create_post(client: TestClient, post_payload: dict) -> Callable[..., dict]:
    def _create(headers: dict[str, str], **overrides) -> dict:
        response = client.post("/posts", json={**post_payload, **overrides}, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _create
