"""닉네임 변경 (PATCH /users/me): 가입과 같은 검사, 중복 409, 30일에 한 번, 정지 중 403."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NicknameChange, User

ME_URL = "/users/me"
SELLER = "seller@campus.ac.kr"


def change(client: TestClient, headers: dict, nickname) -> object:
    return client.patch(ME_URL, json={"nickname": nickname}, headers=headers)


def user_by_email(db: Session, email: str) -> User:
    db.expire_all()
    return db.scalar(select(User).where(User.email == email))


def age_changes(db: Session, delta: timedelta) -> None:
    """변경 기록을 delta만큼 과거로 옮긴다. 30일이 지난 뒤를 흉내 내기 위해서다."""
    for row in db.scalars(select(NicknameChange)).all():
        row.created_at = row.created_at - delta
    db.commit()


def test_change_nickname_returns_me_with_next_change_time(client, auth_headers) -> None:
    before = datetime.now(UTC)
    response = change(client, auth_headers, "  새이름  ")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["nickname"] == "새이름"  # 가입처럼 앞뒤 공백을 지운다
    changeable = datetime.fromisoformat(body["nickname_changeable_at"].replace("Z", "+00:00"))
    if changeable.tzinfo is None:
        changeable = changeable.replace(tzinfo=UTC)
    assert timedelta(days=29, hours=23) < changeable - before <= timedelta(days=30, seconds=5)
    # 내 정보 조회에도 같은 값이 나온다.
    assert client.get(ME_URL, headers=auth_headers).json()["nickname"] == "새이름"


def test_new_user_can_change_right_away(client, auth_headers) -> None:
    assert client.get(ME_URL, headers=auth_headers).json()["nickname_changeable_at"] is None


def test_change_is_recorded_with_old_nickname(client, db_session, auth_headers) -> None:
    change(client, auth_headers, "새이름")

    row = db_session.scalar(select(NicknameChange))
    assert (row.old_nickname, row.new_nickname) == ("판매자", "새이름")


def test_second_change_within_30_days_is_400(client, db_session, auth_headers) -> None:
    assert change(client, auth_headers, "첫변경").status_code == 200

    response = change(client, auth_headers, "두번째")

    assert response.status_code == 400
    assert response.json()["detail"].startswith("닉네임은 30일에 한 번만 바꿀 수 있습니다.")
    assert "부터 바꿀 수 있어요." in response.json()["detail"]
    assert user_by_email(db_session, SELLER).nickname == "첫변경"


def test_can_change_again_after_30_days(client, db_session, auth_headers) -> None:
    change(client, auth_headers, "첫변경")
    age_changes(db_session, timedelta(days=30, seconds=1))

    assert client.get(ME_URL, headers=auth_headers).json()["nickname_changeable_at"] is None
    assert change(client, auth_headers, "두번째").status_code == 200


def test_duplicate_nickname_is_409(client, make_auth_headers, auth_headers) -> None:
    make_auth_headers("buyer@campus.ac.kr", "구매자")

    response = change(client, auth_headers, "구매자")

    assert response.status_code == 409
    assert response.json() == {"detail": "이미 사용 중인 닉네임입니다."}


def test_duplicate_comes_before_30_day_limit(client, make_auth_headers, auth_headers) -> None:
    # 판정 순서 409 → 400
    make_auth_headers("buyer@campus.ac.kr", "구매자")
    change(client, auth_headers, "첫변경")

    assert change(client, auth_headers, "구매자").status_code == 409


def test_same_nickname_is_400(client, auth_headers) -> None:
    response = change(client, auth_headers, "판매자")

    assert response.status_code == 400
    assert response.json() == {"detail": "지금 쓰고 있는 닉네임과 같습니다."}


@pytest.mark.parametrize("nickname", ["a", "   ", "가" * 31, "withdrawn-abc", "Withdrawn-x", None, 3])
def test_invalid_nickname_is_422(client, auth_headers, nickname) -> None:
    assert change(client, auth_headers, nickname).status_code == 422


def test_unknown_field_is_422(client, auth_headers) -> None:
    response = client.patch(ME_URL, json={"nickname": "새이름", "email": "x@campus.ac.kr"}, headers=auth_headers)

    assert response.status_code == 422


def test_requires_login(client) -> None:
    assert change(client, {}, "새이름").status_code == 401


def test_suspended_user_gets_403_before_validation(client, db_session, auth_headers) -> None:
    user = user_by_email(db_session, SELLER)
    user.suspended_until = (datetime.now(UTC) + timedelta(days=1)).replace(tzinfo=None)
    db_session.commit()

    assert change(client, auth_headers, "새이름").status_code == 403
    assert change(client, auth_headers, "a").status_code == 403  # 401 → 403 → 422


def test_old_nickname_becomes_free(client, make_auth_headers, auth_headers) -> None:
    change(client, auth_headers, "새이름")

    # 바꾸기 전 이름은 다른 사람이 가입에 쓸 수 있다.
    make_auth_headers("buyer@campus.ac.kr", "판매자")


def test_withdraw_deletes_nickname_history(client, db_session, auth_headers) -> None:
    change(client, auth_headers, "새이름")

    response = client.post("/users/me/withdraw", json={"password": "password123"}, headers=auth_headers)

    assert response.status_code == 204
    assert db_session.scalar(select(NicknameChange)) is None
