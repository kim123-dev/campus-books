"""비밀번호 재설정: 본인 확인 질문(이메일 → 질문 → 답 확인·확인증 → 확인증 + 새 비밀번호)과
서버 명령(python -m app.cli reset-password)."""

import logging
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cli
from app.core.security import ALGORITHM, create_access_token, create_password_reset_token
from app.models import AdminAction, PasswordResetAttempt, PasswordResetNotice, User, UserRole
from app.schemas.security_question import PRESET_QUESTIONS
from app.services import password_reset_service, security_question_service
from tests.conftest import SECURITY_QUESTION, TestingSessionLocal

EMAIL = "student@campus.ac.kr"
PASSWORD = "password123"
NEW_PASSWORD = "newpassword456"
ANSWER = SECURITY_QUESTION["answer"]
QUESTION = PRESET_QUESTIONS[SECURITY_QUESTION["question_key"]]
QUESTION_URL = "/auth/password-reset/question"
VERIFY_URL = "/auth/password-reset/verify"
RESET_URL = "/auth/password-reset"
INVALID_TOKEN = {"detail": "본인 확인이 만료되었거나 올바르지 않습니다. 처음부터 다시 확인해 주세요."}


def wrong(remaining: int) -> dict:
    return {"detail": f"이메일 또는 답이 맞지 않습니다. 남은 시도 {remaining}번 (24시간 기준)"}


def signup(client: TestClient, email: str = EMAIL, nickname: str = "책벌레", question: dict = SECURITY_QUESTION) -> dict:
    body = {"email": email, "password": PASSWORD, "nickname": nickname, "security_question": question}
    response = client.post("/auth/signup", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def login(client: TestClient, email: str = EMAIL, password: str = PASSWORD):
    return client.post("/auth/login", data={"username": email, "password": password})


def headers_for(client: TestClient, email: str = EMAIL, password: str = PASSWORD) -> dict:
    return {"Authorization": f"Bearer {login(client, email, password).json()['access_token']}"}


def get_question(client: TestClient, email: str = EMAIL):
    return client.post(QUESTION_URL, json={"email": email})


def verify(client: TestClient, answer: str = ANSWER, email: str = EMAIL):
    return client.post(VERIFY_URL, json={"email": email, "answer": answer})


def change(client: TestClient, token: str, new_password: str = NEW_PASSWORD):
    return client.post(RESET_URL, json={"reset_token": token, "new_password": new_password})


def reset(client: TestClient, answer: str = ANSWER, email: str = EMAIL, new_password: str = NEW_PASSWORD):
    """답 확인 → 확인증으로 변경까지. 답 확인이 실패하면 그 응답을 돌려준다."""
    checked = verify(client, answer, email)
    if checked.status_code != 200:
        return checked
    return change(client, checked.json()["reset_token"], new_password)


def failures(db: Session) -> int:
    return len(db.scalars(select(PasswordResetAttempt).where(PasswordResetAttempt.email_hash != "")).all())


def make_admin(db: Session, email: str = EMAIL) -> None:
    db.scalar(select(User).where(User.email == email)).role = UserRole.ADMIN
    db.commit()


def user_row(db: Session) -> User:
    db.expire_all()
    return db.scalar(select(User).where(User.email == EMAIL))


# ---------- 1단계: 질문 받기 ----------


def test_question_for_registered_user(client) -> None:
    signup(client)

    response = get_question(client, "Student@Campus.AC.KR")  # 대소문자는 가입 때처럼 무시한다

    assert response.status_code == 200
    assert response.json() == {"question": QUESTION}


def test_custom_question_is_returned_as_written(client) -> None:
    signup(client, question={"custom_question": "내가 처음 키운 화분의 이름은?", "answer": "초록이"})

    assert get_question(client).json() == {"question": "내가 처음 키운 화분의 이름은?"}


def test_unknown_email_gets_same_decoy_question_every_time(client) -> None:
    # 가입하지 않은 이메일에도 준비된 질문 중 하나를 보여준다. 같은 이메일에는 늘 같은 질문이라 다시 물어봐도 티가 나지 않는다.
    first = get_question(client, "nobody@campus.ac.kr")
    second = get_question(client, "nobody@campus.ac.kr")

    assert first.status_code == 200
    assert first.json() == second.json()
    assert first.json()["question"] in PRESET_QUESTIONS.values()


@pytest.mark.parametrize("case", ["admin", "withdrawn", "no_question"])
def test_unusable_accounts_get_decoy_question(client, db_session, case) -> None:
    signup(client, question={"custom_question": "내가 처음 키운 화분의 이름은?", "answer": "초록이"})
    if case == "admin":
        make_admin(db_session)
    elif case == "withdrawn":
        client.post("/users/me/withdraw", json={"password": PASSWORD}, headers=headers_for(client))
    else:
        # 질문 없이 가입한 예전 계정
        security_question_service.delete_for_user(db_session, db_session.scalar(select(User)).id)
        db_session.commit()

    decoy = get_question(client).json()["question"]

    assert decoy in PRESET_QUESTIONS.values()
    assert decoy == password_reset_service._decoy_question(EMAIL)


def test_question_lookup_requires_valid_email(client, db_session) -> None:
    assert client.post(QUESTION_URL, json={"email": "not-an-email"}).status_code == 422
    assert client.post(QUESTION_URL, json={}).status_code == 422
    assert db_session.scalar(select(PasswordResetAttempt)) is None


# ---------- 2단계: 답 확인 ----------


def test_correct_answer_returns_token_without_changing_password(client) -> None:
    signup(client)

    response = verify(client)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"reset_token", "expires_in"} and body["expires_in"] == 600
    # 답 확인만으로는 비밀번호가 바뀌지 않는다.
    assert login(client).status_code == 200


@pytest.mark.parametrize("answer", ["해피 마트", " 해피마트 ", "해피　마트", "ＨＡＰＰＹ"])
def test_answer_ignores_spaces_case_and_width(client, answer) -> None:
    question = {"question_key": "CHILDHOOD_SHOP", "answer": "happy" if answer == "ＨＡＰＰＹ" else "해피마트"}
    signup(client, question=question)

    assert verify(client, answer=answer).status_code == 200


def test_wrong_answer_shows_remaining_attempts(client) -> None:
    signup(client)

    statuses = [verify(client, answer="틀린답").json() for _ in range(4)]

    assert statuses == [wrong(4), wrong(3), wrong(2), wrong(1)]


def test_wrong_answer_and_unknown_email_look_the_same(client) -> None:
    # 없는 이메일도 같은 방식으로 세므로 남은 횟수까지 같다. 가입 여부가 드러나지 않는다.
    signup(client)

    real = [verify(client, answer="틀린답") for _ in range(5)]
    unknown = [verify(client, email="nobody@campus.ac.kr") for _ in range(5)]

    assert [r.status_code for r in real] == [r.status_code for r in unknown] == [400] * 4 + [429]
    assert [r.json() for r in real[:4]] == [r.json() for r in unknown[:4]]
    assert real[4].json() == unknown[4].json()
    assert login(client).status_code == 200


@pytest.mark.parametrize("case", ["admin", "withdrawn", "no_question"])
def test_unusable_accounts_get_same_400_even_with_right_answer(client, db_session, case) -> None:
    signup(client)
    if case == "admin":
        make_admin(db_session)
    elif case == "withdrawn":
        client.post("/users/me/withdraw", json={"password": PASSWORD}, headers=headers_for(client))
    else:
        security_question_service.delete_for_user(db_session, db_session.scalar(select(User)).id)
        db_session.commit()

    response = verify(client)

    assert (response.status_code, response.json()) == (400, wrong(4))


def test_every_failure_compares_bcrypt_once(client, monkeypatch) -> None:
    # 없는 이메일도 실제 계정의 오답과 같은 처리(bcrypt 비교 한 번)를 거친다. (처리 시간으로 가입 여부를 알 수 없게)
    signup(client)
    calls = []
    original = security_question_service.verify_answer
    monkeypatch.setattr(security_question_service, "verify_answer", lambda *args: calls.append(1) or original(*args))

    verify(client, answer="틀린답")
    verify(client, email="nobody@campus.ac.kr")

    assert len(calls) == 2


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-email", "answer": ANSWER},
        {"email": EMAIL, "answer": ""},
        {"email": EMAIL, "answer": "가" * 101},
        {"email": EMAIL},
        {"email": EMAIL, "answer": ANSWER, "new_password": NEW_PASSWORD},
    ],
)
def test_invalid_verify_body_is_422_and_not_counted(client, db_session, body) -> None:
    assert client.post(VERIFY_URL, json=body).status_code == 422
    assert db_session.scalar(select(PasswordResetAttempt)) is None


# ---------- 3단계: 확인증 + 새 비밀번호 ----------


def test_reset_with_token_changes_password_and_invalidates_old_tokens(client) -> None:
    signup(client)
    old_headers = headers_for(client)

    response = reset(client)

    assert response.status_code == 204
    assert login(client).status_code == 401
    assert login(client, password=NEW_PASSWORD).status_code == 200
    # 비밀번호 해시가 바뀌어 예전 토큰은 쓸 수 없다.
    assert client.get("/users/me", headers=old_headers).status_code == 401


def test_token_can_be_used_only_once(client) -> None:
    signup(client)
    token = verify(client).json()["reset_token"]

    assert change(client, token).status_code == 204
    second = change(client, token, new_password="another12345")

    assert (second.status_code, second.json()) == (400, INVALID_TOKEN)
    assert login(client, password=NEW_PASSWORD).status_code == 200


def test_token_dies_when_password_changes_another_way(client) -> None:
    signup(client)
    token = verify(client).json()["reset_token"]
    client.put("/users/me/password", json={"current_password": PASSWORD, "new_password": "changedpass1"}, headers=headers_for(client))

    assert change(client, token).json() == INVALID_TOKEN


def test_expired_token_is_rejected(client, db_session) -> None:
    signup(client)
    user = user_row(db_session)
    token = create_password_reset_token(user.id, user.password_hash, expires_delta=timedelta(seconds=-1))

    assert change(client, token).json() == INVALID_TOKEN
    assert login(client).status_code == 200


def test_forged_and_garbage_tokens_are_rejected(client, db_session) -> None:
    signup(client)
    user = user_row(db_session)
    payload = {"uid": user.id, "rpw": "x", "aud": "password-reset", "exp": datetime.now(UTC) + timedelta(minutes=5)}
    other_key = jwt.encode(payload, "a-different-secret-key-that-is-long-enough", algorithm=ALGORITHM)
    unsigned = jwt.encode(payload, None, algorithm="none")

    for token in [other_key, unsigned, "not-a-token"]:
        assert change(client, token).json() == INVALID_TOKEN
    assert login(client).status_code == 200


def test_access_token_and_reset_token_are_not_interchangeable(client, db_session) -> None:
    signup(client)
    user = user_row(db_session)
    reset_token = verify(client).json()["reset_token"]

    # 로그인 토큰으로는 비밀번호를 재설정할 수 없고, 확인증으로는 로그인한 것처럼 쓸 수 없다.
    assert change(client, create_access_token(user.id, user.password_hash)).json() == INVALID_TOKEN
    assert client.get("/users/me", headers={"Authorization": f"Bearer {reset_token}"}).status_code == 401


def test_token_is_bound_to_its_account(client, db_session) -> None:
    signup(client)
    signup(client, email="other@campus.ac.kr", nickname="다른사람")
    token = verify(client).json()["reset_token"]

    change(client, token)

    assert login(client, email="other@campus.ac.kr").status_code == 200
    assert login(client, password=NEW_PASSWORD).status_code == 200


@pytest.mark.parametrize("case", ["admin", "withdrawn"])
def test_token_rejected_if_account_became_unusable(client, db_session, case) -> None:
    signup(client)
    token = verify(client).json()["reset_token"]
    if case == "admin":
        make_admin(db_session)
    else:
        # 탈퇴하면 비밀번호 해시도 바뀌지만, 계정 상태 검사로도 막는다.
        client.post("/users/me/withdraw", json={"password": PASSWORD}, headers=headers_for(client))

    assert change(client, token).json() == INVALID_TOKEN


@pytest.mark.parametrize(
    "body",
    [
        {"new_password": NEW_PASSWORD},  # 확인증 없음
        {"reset_token": "", "new_password": NEW_PASSWORD},
        {"reset_token": "abc", "new_password": "short"},
        {"reset_token": "abc"},
        # 예전 방식(답 + 새 비밀번호)은 더 받지 않는다.
        {"email": EMAIL, "answer": ANSWER, "new_password": NEW_PASSWORD},
    ],
)
def test_invalid_reset_body_is_422(client, body) -> None:
    signup(client)
    assert client.post(RESET_URL, json=body).status_code == 422
    assert login(client).status_code == 200


def test_suspended_user_can_reset_but_stays_suspended(client, db_session) -> None:
    signup(client)
    user = db_session.scalar(select(User).where(User.email == EMAIL))
    user.suspended_until = (datetime.now(UTC) + timedelta(days=3)).replace(tzinfo=None)
    db_session.commit()

    assert reset(client).status_code == 204
    assert login(client, password=NEW_PASSWORD).status_code == 403


# ---------- 잠금: 이메일당 24시간 5번, IP당 1시간 30회 ----------


def test_fifth_wrong_answer_locks_for_24_hours(client, db_session) -> None:
    signup(client)
    for _ in range(4):
        assert verify(client, answer="틀린답").status_code == 400

    fifth = verify(client, answer="틀린답")
    after = verify(client)  # 잠긴 뒤에는 맞는 답이라도 막는다

    for response in (fifth, after):
        assert response.status_code == 429
        assert 23 * 3600 < int(response.headers["Retry-After"]) <= 24 * 3600
        # 남은 시간을 알려준다. (23시간 59분 또는 24시간)
        assert "시간" in response.json()["detail"] and "뒤에 다시 시도" in response.json()["detail"]
    assert login(client).status_code == 200
    assert failures(db_session) == 5  # 잠긴 동안의 시도는 기록하지 않는다


def test_lock_ends_24_hours_after_last_failure(client, db_session) -> None:
    signup(client)
    for _ in range(5):
        verify(client, answer="틀린답")
    for row in db_session.scalars(select(PasswordResetAttempt)).all():
        row.created_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24, minutes=1)
    db_session.commit()

    assert reset(client).status_code == 204


def test_correct_answer_clears_earlier_failures(client) -> None:
    signup(client)
    for _ in range(4):
        verify(client, answer="틀린답")
    assert verify(client).status_code == 200

    # 맞히기 전의 4번은 더 세지 않는다. 다시 5번 틀려야 잠긴다.
    assert verify(client, answer="틀린답").json() == wrong(4)


def test_ip_limit_30_per_hour_counts_lookups_and_verifies(client) -> None:
    # 이메일을 바꿔 가며 시도해도 같은 IP에서 질문 받기 + 답 확인이 30번을 넘으면 막는다.
    statuses = [get_question(client, f"user{i}@campus.ac.kr").status_code for i in range(15)]
    statuses += [verify(client, email=f"user{i}@campus.ac.kr").status_code for i in range(15)]
    assert statuses == [200] * 15 + [400] * 15

    blocked_lookup = get_question(client, "late@campus.ac.kr")
    blocked_verify = verify(client, email="late@campus.ac.kr")

    assert (blocked_lookup.status_code, blocked_verify.status_code) == (429, 429)
    assert 1 <= int(blocked_lookup.headers["Retry-After"]) <= 3600


def test_attempts_store_email_hash_not_email(client, db_session) -> None:
    verify(client, answer="틀린답")

    row = db_session.scalar(select(PasswordResetAttempt))
    assert EMAIL not in row.email_hash and len(row.email_hash) == 64
    assert row.ip == "testclient" and row.success is False


# ---------- 기록과 다음 로그인 안내 ----------


def test_reset_is_written_to_admin_log_without_admin(client, db_session) -> None:
    user_id = signup(client)["id"]

    verify(client)
    assert db_session.scalar(select(AdminAction)) is None  # 답 확인만으로는 기록하지 않는다
    reset(client)

    db_session.expire_all()
    entry = db_session.scalar(select(AdminAction))
    assert (entry.action, entry.admin_id, entry.target_user_id) == ("RESET_PASSWORD_BY_QUESTION", None, user_id)


def test_admin_log_shows_reset_with_empty_admin(client, db_session, make_admin_headers) -> None:
    signup(client)
    reset(client)
    admin = make_admin_headers()

    items = client.get("/admin/actions", headers=admin).json()["items"]

    assert [(item["action"], item["admin"]) for item in items] == [("RESET_PASSWORD_BY_QUESTION", None)]


def test_next_login_shows_reset_notice_until_dismissed(client) -> None:
    signup(client)
    reset(client)
    headers = headers_for(client, password=NEW_PASSWORD)

    notice = client.get("/users/me", headers=headers).json()["password_reset_notice"]
    assert notice["method"] == "QUESTION" and notice["reset_at"]

    assert client.post("/users/me/password-reset-notice/dismiss", headers=headers).status_code == 204
    assert client.get("/users/me", headers=headers).json()["password_reset_notice"] is None


def test_dismiss_requires_login(client) -> None:
    assert client.post("/users/me/password-reset-notice/dismiss").status_code == 401


# ---------- 서버 명령: python -m app.cli reset-password ----------


def run_reset_cli(email: str) -> int:
    return cli.main(["reset-password", email], session_factory=TestingSessionLocal)


def test_cli_reset_password_shows_new_password_once(client, db_session, capsys, caplog) -> None:
    user_id = signup(client)["id"]
    make_admin(db_session)  # 관리자도 서버 명령으로는 재설정할 수 있다
    old_headers = headers_for(client)
    caplog.set_level(logging.DEBUG)

    assert run_reset_cli(" Student@Campus.AC.KR ") == 0

    out = capsys.readouterr().out
    password = next(line.removeprefix("새 비밀번호: ") for line in out.splitlines() if line.startswith("새 비밀번호: "))
    assert len(password) == password_reset_service.SERVER_PASSWORD_LENGTH
    assert not set(password) & set("0O1lI")
    assert login(client, password=password).status_code == 200
    assert client.get("/users/me", headers=old_headers).status_code == 401
    # 비밀번호는 로그에도 관리 기록에도 남지 않는다.
    assert password not in caplog.text
    db_session.expire_all()
    entry = db_session.scalar(select(AdminAction))
    assert (entry.action, entry.admin_id, entry.target_user_id, entry.reason) == ("RESET_PASSWORD_BY_SERVER", None, user_id, None)
    notice = db_session.scalar(select(PasswordResetNotice))
    assert notice.method == "SERVER"


def test_cli_passwords_are_random(client, capsys) -> None:
    signup(client)
    run_reset_cli(EMAIL)
    run_reset_cli(EMAIL)

    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("새 비밀번호: ")]
    assert len(set(lines)) == 2


def test_cli_reset_unknown_email_fails(client, db_session, capsys) -> None:
    assert run_reset_cli("nobody@campus.ac.kr") == 1
    assert "가입한 사용자가 없습니다" in capsys.readouterr().err
    assert db_session.scalar(select(AdminAction)) is None


def test_server_reset_does_not_lock_question_change(client, db_session) -> None:
    signup(client)
    run_reset_cli(EMAIL)

    assert security_question_service.changeable_at(db_session, user_row(db_session)) is None


# ---------- 비밀번호 지문: 토큰을 열어 봐도 해시를 알 수 없음 ----------


def _hash_pieces(password_hash: str) -> list[str]:
    # bcrypt 해시 "$2b$04$<솔트 22자><해시 31자>"에서 8자씩 잘라 본 조각들
    body = password_hash.split("$")[-1]
    return [body[i : i + 8] for i in range(0, len(body) - 7)]


def test_tokens_never_contain_password_hash_or_its_pieces(client, db_session) -> None:
    signup(client)
    password_hash = user_row(db_session).password_hash
    reset_token = verify(client).json()["reset_token"]
    access_token = login(client).json()["access_token"]

    for token in (reset_token, access_token):
        # 서명 없이도 누구나 열어 볼 수 있는 내용 전체
        payload = jwt.decode(token, options={"verify_signature": False})
        text = str(payload)
        assert password_hash not in text
        assert not any(piece in text for piece in _hash_pieces(password_hash))


def test_fingerprint_is_hmac_with_server_key_not_plain_sha256(client, db_session) -> None:
    import hashlib
    import hmac

    from app.core.config import get_settings

    signup(client)
    password_hash = user_row(db_session).password_hash
    fingerprint = jwt.decode(verify(client).json()["reset_token"], options={"verify_signature": False})["rpw"]

    # 키 없는 SHA-256(예전 방식)으로는 같은 값을 만들 수 없다.
    assert fingerprint != hashlib.sha256(password_hash.encode()).hexdigest()[: len(fingerprint)]
    # 서버 비밀 키로 HMAC한 값이고, 다른 키로는 다른 값이 나온다.
    message = b"password-fingerprint:" + password_hash.encode()
    expected = hmac.new(get_settings().SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()[:32]
    other_key = hmac.new(b"another-secret-key", message, hashlib.sha256).hexdigest()[:32]
    assert fingerprint == expected != other_key
    # 로그인 토큰도 같은 지문을 쓴다.
    assert jwt.decode(login(client).json()["access_token"], options={"verify_signature": False})["pwd"] == expected
