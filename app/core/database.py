from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# SQLite는 기본적으로 생성한 스레드에서만 연결을 허용하는데,
# FastAPI는 요청을 여러 스레드에서 처리하므로 이 검사를 끈다.
connect_args = (
    {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """모든 모델이 상속하는 기반 클래스. 테이블 생성 시 메타데이터를 한곳에 모은다."""


# 요청마다 세션을 하나 열고, 요청이 끝나면 반드시 닫아 연결 누수를 막는다.
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
