"""복구 코드와 비밀번호 재설정: 가입 시 1회 노출, 해시만 저장, 재발급, 재설정, 같은 응답, 시도 제한, 정지·관리자."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AdminAction, PasswordResetAttempt, RecoveryCode, User, UserRole
from app.services import recovery_service

EMAIL = "student@campus.ac.kr"
PASSWORD = "password123"
NEW_PASSWORD = "newpassword456"
RESET_URL = "/auth/password-reset"
CODE_URL = "/users/me/recovery-code"
SAME_FAILURE = {"detail": "이메일 또는 복구 코드가 맞지 않습니다."}
CODE_PATTERN = re.compile(r"^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}(-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}){3}$")


def signup(client: TestClient, email: str = EMAIL, nickname: str = "책벌레") -> dict:
    response = client.post("/auth/signup", json={"email": email, "password": PASSWORD, "nickname": nickname})
    assert response.status_code == 201, response.text
    return response.json()


def login(client: TestClient, email: str = EMAIL, password: str = PASSWORD):
    return client.post("/auth/login", data={"username": email, "password": password})


def headers_for(client: TestClient, email: str = EMAIL, password: str = PASSWORD) -> dict:
    return {"Authorization": f"Bearer {login(client, email, password).json()['access_token']}"}


def reset(client: TestClient, code: str, email: str = EMAIL, new_password: str = NEW_PASSWORD):
    body = {"email": email, "recovery_code": code, "new_password": new_password}
    return client.post(RESET_URL, json=body)


def attempts(db: Session) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(PasswordResetAttempt)) or 0


# ---------- 코드 모양과 저장 ----------


def test_signup_returns_code_once_and_stores_only_hash(client, db_session) -> None:
    code = signup(client)["recovery_code"]

    assert CODE_PATTERN.match(code)
    row = db_session.scalar(select(RecoveryCode))
    assert row.code_hash == recovery_service.hash_code(code)
    assert code.replace("-", "") not in row.code_hash
    # 코드 원문은 다시 볼 수 없다. 내 정보에는 발급 시각만 나온다.
    me = client.get("/users/me", headers=headers_for(client)).json()
    assert me["recovery_code_issued_at"] is not None
    assert code not in str(me)


def test_codes_are_random() -> None:
    codes = {recovery_service.generate_code() for _ in range(200)}
    assert len(codes) == 200
    assert all(CODE_PATTERN.match(code) for code in codes)
    # 31글자 16자리 = 약 79비트
    assert len(recovery_service.CODE_ALPHABET) ** recovery_service.CODE_LENGTH > 2**79


def test_code_alphabet_has_no_confusing_letters() -> None:
    assert not set("01ILO") & set(recovery_service.CODE_ALPHABET)


# ---------- 재설정 성공 ----------


def test_reset_changes_password_consumes_code_and_returns_new_one(client, db_session) -> None:
    code = signup(client)["recovery_code"]
    old_headers = headers_for(client)

    response = reset(client, code)

    assert response.status_code == 200, response.text
    new_code = response.json()["recovery_code"]
    assert CODE_PATTERN.match(new_code) and new_code != code
    # 이전 토큰은 모두 끊기고, 옛 비밀번호는 안 되고 새 비밀번호로 로그인된다.
    assert client.get("/users/me", headers=old_headers).status_code == 401
    assert login(client).status_code == 401
    assert login(client, password=NEW_PASSWORD).status_code == 200
    # 쓴 코드는 다시 쓸 수 없고, 새 코드는 쓸 수 있다.
    assert reset(client, code, new_password="another-pass1").json() == SAME_FAILURE
    assert reset(client, new_code, new_password="another-pass1").status_code == 200


@pytest.mark.parametrize("transform", [str.lower, lambda c: c.replace("-", ""), lambda c: f"  {c.replace('-', ' ')} "])
def test_code_accepts_lowercase_spaces_and_no_hyphens(client, transform) -> None:
    code = signup(client)["recovery_code"]

    assert reset(client, transform(code)).status_code == 200


def test_email_is_case_insensitive(client) -> None:
    code = signup(client)["recovery_code"]

    assert reset(client, code, email=EMAIL.upper()).status_code == 200


# ---------- 같은 실패 응답 ----------


def test_wrong_code_unknown_email_and_no_code_get_same_400(client, db_session) -> None:
    signup(client)
    other = signup(client, "nocode@campus.ac.kr", "코드없음")
    db_session.execute(RecoveryCode.__table__.delete().where(RecoveryCode.user_id == other["id"]))
    db_session.commit()
    fake = recovery_service.generate_code()

    responses = [
        reset(client, fake),  # 틀린 코드
        reset(client, fake, email="nobody@campus.ac.kr"),  # 없는 이메일
        reset(client, fake, email="nocode@campus.ac.kr"),  # 코드를 발급받지 않은 계정
        reset(client, "!!!!"),  # 모양이 다른 코드
    ]

    assert [r.status_code for r in responses] == [400, 400, 400, 400]
    assert all(r.json() == SAME_FAILURE for r in responses)
    assert login(client).status_code == 200  # 비밀번호는 그대로


def test_withdrawn_account_gets_same_400(client) -> None:
    code = signup(client)["recovery_code"]
    client.post("/users/me/withdraw", json={"password": PASSWORD}, headers=headers_for(client))

    assert reset(client, code).json() == SAME_FAILURE


def test_withdraw_deletes_recovery_code(client, db_session) -> None:
    signup(client)
    client.post("/users/me/withdraw", json={"password": PASSWORD}, headers=headers_for(client))

    assert db_session.scalar(select(RecoveryCode)) is None


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-email", "recovery_code": "ABCD", "new_password": NEW_PASSWORD},
        {"email": EMAIL, "recovery_code": "", "new_password": NEW_PASSWORD},
        {"email": EMAIL, "recovery_code": "ABCD", "new_password": "short"},
        {"email": EMAIL, "recovery_code": "ABCD"},
        {"email": EMAIL, "recovery_code": "ABCD", "new_password": NEW_PASSWORD, "extra": 1},
    ],
)
def test_invalid_body_is_422_and_not_counted(client, db_session, body) -> None:
    assert client.post(RESET_URL, json=body).status_code == 422
    assert attempts(db_session) == 0


# ---------- 시도 제한 ----------


def test_email_limit_5_per_hour_returns_429_with_retry_after(client, db_session) -> None:
    code = signup(client)["recovery_code"]
    fake = recovery_service.generate_code()
    for _ in range(5):
        assert reset(client, fake).status_code == 400

    response = reset(client, code)  # 6번째는 맞는 코드라도 막는다

    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 3600
    assert login(client).status_code == 200
    assert attempts(db_session) == 5  # 막힌 시도는 기록하지 않는다


def test_unknown_email_is_limited_the_same_way(client) -> None:
    fake = recovery_service.generate_code()
    statuses = [reset(client, fake, email="nobody@campus.ac.kr").status_code for _ in range(6)]

    assert statuses == [400] * 5 + [429]


def test_limit_resets_after_an_hour(client, db_session) -> None:
    code = signup(client)["recovery_code"]
    fake = recovery_service.generate_code()
    for _ in range(5):
        reset(client, fake)
    for row in db_session.scalars(select(PasswordResetAttempt)).all():
        row.created_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1, minutes=1)
    db_session.commit()

    assert reset(client, code).status_code == 200


def test_ip_limit_30_per_hour(client, db_session) -> None:
    # 이메일을 바꿔 가며 시도해도 같은 IP에서 30번이 넘으면 막는다.
    fake = recovery_service.generate_code()
    statuses = [reset(client, fake, email=f"user{i}@campus.ac.kr").status_code for i in range(31)]

    assert statuses == [400] * 30 + [429]


def test_attempts_store_email_hash_not_email(client, db_session) -> None:
    reset(client, recovery_service.generate_code())

    row = db_session.scalar(select(PasswordResetAttempt))
    assert EMAIL not in row.email_hash and len(row.email_hash) == 64
    assert row.ip == "testclient" and row.success is False


# ---------- 정지·관리자 ----------


def test_suspended_user_can_reset_but_stays_suspended(client, db_session) -> None:
    code = signup(client)["recovery_code"]
    user = db_session.scalar(select(User).where(User.email == EMAIL))
    user.suspended_until = (datetime.now(UTC) + timedelta(days=3)).replace(tzinfo=None)
    db_session.commit()

    assert reset(client, code).status_code == 200
    assert login(client, password=NEW_PASSWORD).status_code == 403


def test_admin_reset_is_written_to_admin_log(client, db_session) -> None:
    body = signup(client)
    db_session.scalar(select(User).where(User.email == EMAIL)).role = UserRole.ADMIN
    db_session.commit()

    assert reset(client, body["recovery_code"]).status_code == 200

    db_session.expire_all()
    entry = db_session.scalar(select(AdminAction))
    assert (entry.action, entry.admin_id, entry.target_user_id) == ("RESET_PASSWORD_BY_CODE", body["id"], body["id"])


def test_normal_user_reset_writes_no_admin_log(client, db_session) -> None:
    reset(client, signup(client)["recovery_code"])

    assert db_session.scalar(select(AdminAction)) is None


# ---------- 내 정보에서 발급·재발급 ----------


def test_reissue_needs_password_and_invalidates_old_code(client) -> None:
    old = signup(client)["recovery_code"]
    headers = headers_for(client)

    assert client.post(CODE_URL, json={"password": "wrong-password"}, headers=headers).status_code == 400
    response = client.post(CODE_URL, json={"password": PASSWORD}, headers=headers)

    assert response.status_code == 200
    new = response.json()["recovery_code"]
    assert CODE_PATTERN.match(new) and new != old and response.json()["issued_at"]
    assert reset(client, old).json() == SAME_FAILURE
    assert reset(client, new).status_code == 200


def test_existing_user_without_code_can_issue_one(client, db_session) -> None:
    signup(client)
    db_session.execute(RecoveryCode.__table__.delete())
    db_session.commit()
    headers = headers_for(client)
    assert client.get("/users/me", headers=headers).json()["recovery_code_issued_at"] is None

    code = client.post(CODE_URL, json={"password": PASSWORD}, headers=headers).json()["recovery_code"]

    assert client.get("/users/me", headers=headers).json()["recovery_code_issued_at"] is not None
    assert reset(client, code).status_code == 200


def test_reissue_requires_login_and_valid_body(client) -> None:
    signup(client)
    assert client.post(CODE_URL, json={"password": PASSWORD}).status_code == 401
    assert client.post(CODE_URL, json={}, headers=headers_for(client)).status_code == 422


def test_suspended_user_can_reissue(client, db_session) -> None:
    signup(client)
    headers = headers_for(client)
    db_session.scalar(select(User).where(User.email == EMAIL)).suspended_until = (
        datetime.now(UTC) + timedelta(days=1)
    ).replace(tzinfo=None)
    db_session.commit()

    assert client.post(CODE_URL, json={"password": PASSWORD}, headers=headers).status_code == 200
