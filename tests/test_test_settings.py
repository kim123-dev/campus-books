"""테스트 환경 설정 확인. 속도를 위해 바꾼 설정이 테스트에만 적용되고, 병렬 실행에서도 서로 섞이지 않는지 본다."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.security import hash_password, verify_password
from tests.conftest import SECURITY_QUESTION, test_engine


# ---------- bcrypt 비용 ----------


def test_bcrypt_rounds_lowered_in_tests() -> None:
    assert get_settings().BCRYPT_ROUNDS == 4
    # bcrypt 해시는 "$2b$<비용>$..." 형식이라, 실제로 4로 만들어졌는지 해시에서 확인한다.
    password_hash = hash_password("password123")
    assert password_hash.startswith("$2b$04$")
    assert verify_password("password123", password_hash)


def test_signup_stores_low_cost_hash_in_tests(client, db_session) -> None:
    from app.models import User

    client.post("/auth/signup", json={"email": "a@campus.ac.kr", "password": "password123", "nickname": "가나", "security_question": SECURITY_QUESTION})

    assert db_session.query(User).one().password_hash.startswith("$2b$04$")


def test_production_default_rounds_is_12(monkeypatch: pytest.MonkeyPatch) -> None:
    # 테스트용 환경변수와 .env를 빼고 만들면 운영 기본값이 나와야 한다.
    monkeypatch.delenv("BCRYPT_ROUNDS")
    assert Settings(_env_file=None, SECRET_KEY="x").BCRYPT_ROUNDS == 12


def test_hash_made_with_other_cost_still_verifies() -> None:
    # 검증은 해시에 적힌 비용을 따르므로, 비용을 바꿔도 기존 사용자가 로그인할 수 있다.
    import bcrypt

    old_hash = bcrypt.hashpw(b"password123", bcrypt.gensalt(rounds=5)).decode()
    assert verify_password("password123", old_hash)


@pytest.mark.parametrize("rounds", ["3", "32", "abc"])
def test_invalid_rounds_rejected(monkeypatch: pytest.MonkeyPatch, rounds: str) -> None:
    # 실수로 너무 낮은(보안 약화) 값이나 bcrypt가 받지 않는 값을 넣으면 서버가 뜨지 않게 한다.
    monkeypatch.setenv("BCRYPT_ROUNDS", rounds)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY="x")


# ---------- 병렬 실행(pytest-xdist) 격리 ----------


def test_db_is_in_memory() -> None:
    # 인메모리 SQLite는 프로세스 메모리 안에만 있으므로, 워커(프로세스)마다 DB가 따로 생긴다.
    assert test_engine.url.database in (None, "", ":memory:")
    assert os.environ["DATABASE_URL"] == "sqlite://"


def test_upload_dir_is_per_test_temp_folder(image_dir: Path, tmp_path: Path, worker_id: str) -> None:
    # 사진 폴더는 테스트마다 새 임시 폴더다. 병렬 실행이면 임시 폴더 경로에 워커 이름이 들어가 워커끼리도 겹치지 않는다.
    assert image_dir.is_relative_to(tmp_path)
    assert not image_dir.exists()
    if worker_id != "master":
        assert worker_id in str(tmp_path)
