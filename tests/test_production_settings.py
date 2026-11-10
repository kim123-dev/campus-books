"""운영(production) 배포 설정 확인. 배포 플랫폼이 주는 값이 그대로 동작하고, 빠뜨린 설정은 시작 전에 걸러지는지 본다."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine

from app.core.config import MIN_PRODUCTION_SECRET_KEY_LENGTH, Settings
from app.main import api_docs_urls

PG_URL = "postgresql://user:pw@db.internal:5432/railway"
PRODUCTION_KEY = "k" * MIN_PRODUCTION_SECRET_KEY_LENGTH


def make_settings(**values: str) -> Settings:
    # .env와 테스트용 환경변수(DATABASE_URL=sqlite://)에 영향받지 않도록 값을 직접 넣는다.
    return Settings(_env_file=None, **values)


# ---------- DB 주소 ----------


@pytest.mark.parametrize("url", [PG_URL, "postgres://user:pw@db.internal:5432/railway"])
def test_postgres_url_uses_psycopg_driver(url: str) -> None:
    settings = make_settings(SECRET_KEY="x", DATABASE_URL=url)

    assert settings.DATABASE_URL == "postgresql+psycopg://user:pw@db.internal:5432/railway"
    # 드라이버를 실제로 불러올 수 있는지 확인한다. (연결은 하지 않는다)
    assert create_engine(settings.DATABASE_URL).dialect.driver == "psycopg"


def test_sqlite_url_is_unchanged() -> None:
    assert make_settings(SECRET_KEY="x", DATABASE_URL="sqlite:///./dev.db").DATABASE_URL == "sqlite:///./dev.db"


# ---------- 운영 설정 검사 ----------


def test_development_is_default() -> None:
    assert make_settings(SECRET_KEY="x").is_production is False


def test_production_accepts_valid_settings() -> None:
    settings = make_settings(ENVIRONMENT="production", SECRET_KEY=PRODUCTION_KEY, DATABASE_URL=PG_URL)

    assert settings.is_production is True


def test_production_rejects_sqlite() -> None:
    with pytest.raises(ValidationError, match="PostgreSQL"):
        make_settings(ENVIRONMENT="production", SECRET_KEY=PRODUCTION_KEY, DATABASE_URL="sqlite:///./dev.db")


def test_production_rejects_short_secret_key() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        make_settings(ENVIRONMENT="production", SECRET_KEY="change-me", DATABASE_URL=PG_URL)


# ---------- API 문서 ----------


def test_docs_disabled_in_production() -> None:
    client = TestClient(FastAPI(**api_docs_urls(is_production=True)))

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_docs_enabled_in_development(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
