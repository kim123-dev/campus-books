"""비밀번호 재설정: 본인 확인 질문(이메일 → 질문 → 답 + 새 비밀번호)과 서버 명령(python -m app.cli reset-password)."""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cli
from app.models import AdminAction, PasswordResetAttempt, PasswordResetNotice, User, UserRole
from app.schemas.security_question import PRESET_QUESTIONS
from app.services import password_reset_service
from tests.conftest import SECURITY_QUESTION, TestingSessionLocal

EMAIL = "student@campus.ac.kr"
PASSWORD = "password123"
NEW_PASSWORD = "newpassword456"
ANSWER = SECURITY_QUESTION["answer"]
QUESTION = PRESET_QUESTIONS[SECURITY_QUESTION["question_key"]]
QUESTION_URL = "/auth/password-reset/question"
RESET_URL = "/auth/password-reset"
SAME_FAILURE = {"detail": "이메일 또는 답이 맞지 않습니다."}


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


def reset(client: TestClient, answer: str = ANSWER, email: str = EMAIL, new_password: str = NEW_PASSWORD):
    return client.post(RESET_URL, json={"email": email, "answer": answer, "new_password": new_password})


def failures(db: Session) -> int:
    return len(db.scalars(select(PasswordResetAttempt).where(PasswordResetAttempt.email_hash != "")).all())


def make_admin(db: Session, email: str = EMAIL) -> None:
    db.scalar(select(User).where(User.email == email)).role = UserRole.ADMIN
    db.commit()


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
        decoy = get_question(client).json()["question"]
    elif case == "withdrawn":
        client.post("/users/me/withdraw", json={"password": PASSWORD}, headers=headers_for(client))
        decoy = get_question(client).json()["question"]
    else:
        # 질문 없이 가입한 예전 계정
        user = db_session.scalar(select(User))
        from app.services import security_question_service

        security_question_service.delete_for_user(db_session, user.id)
        db_session.commit()
        decoy = get_question(client).json()["question"]

    assert decoy in PRESET_QUESTIONS.values()
    assert decoy == password_reset_service._decoy_question(EMAIL)


def test_question_lookup_requires_valid_email(client, db_session) -> None:
    assert client.post(QUESTION_URL, json={"email": "not-an-email"}).status_code == 422
    assert client.post(QUESTION_URL, json={}).status_code == 422
    assert db_session.scalar(select(PasswordResetAttempt)) is None


# ---------- 2단계: 답 + 새 비밀번호 ----------


def test_reset_changes_password_and_invalidates_old_tokens(client, db_session) -> None:
    signup(client)
    old_headers = headers_for(client)

    response = reset(client)

    assert response.status_code == 204
    assert login(client).status_code == 401
    assert login(client, password=NEW_PASSWORD).status_code == 200
    # 비밀번호 해시가 바뀌어 예전 토큰은 쓸 수 없다.
    assert client.get("/users/me", headers=old_headers).status_code == 401


@pytest.mark.parametrize("answer", ["해피 마트", " 해피마트 ", "해피　마트", "ＨＡＰＰＹ"])
def test_answer_ignores_spaces_case_and_width(client, answer) -> None:
    question = {"question_key": "CHILDHOOD_SHOP", "answer": "happy" if answer == "ＨＡＰＰＹ" else "해피마트"}
    signup(client, question=question)

    assert reset(client, answer=answer).status_code == 204


def test_wrong_answer_and_unknown_email_get_same_400(client, db_session) -> None:
    signup(client)

    wrong = reset(client, answer="틀린답")
    unknown = reset(client, email="nobody@campus.ac.kr")

    assert (wrong.status_code, unknown.status_code) == (400, 400)
    assert wrong.json() == unknown.json() == SAME_FAILURE
    assert login(client).status_code == 200


@pytest.mark.parametrize("case", ["admin", "withdrawn"])
def test_admin_and_withdrawn_cannot_reset_by_question(client, db_session, case) -> None:
    signup(client)
    if case == "admin":
        make_admin(db_session)
    else:
        client.post("/users/me/withdraw", json={"password": PASSWORD}, headers=headers_for(client))

    response = reset(client)  # 맞는 답이어도 같은 400

    assert response.json() == SAME_FAILURE
    if case == "admin":
        assert login(client).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-email", "answer": ANSWER, "new_password": NEW_PASSWORD},
        {"email": EMAIL, "answer": "", "new_password": NEW_PASSWORD},
        {"email": EMAIL, "answer": "가" * 101, "new_password": NEW_PASSWORD},
        {"email": EMAIL, "answer": ANSWER, "new_password": "short"},
        {"email": EMAIL, "answer": ANSWER},
        {"email": EMAIL, "answer": ANSWER, "new_password": NEW_PASSWORD, "extra": 1},
    ],
)
def test_invalid_body_is_422_and_not_counted(client, db_session, body) -> None:
    assert client.post(RESET_URL, json=body).status_code == 422
    assert db_session.scalar(select(PasswordResetAttempt)) is None


def test_suspended_user_can_reset_but_stays_suspended(client, db_session) -> None:
    signup(client)
    user = db_session.scalar(select(User).where(User.email == EMAIL))
    user.suspended_until = (datetime.now(UTC) + timedelta(days=3)).replace(tzinfo=None)
    db_session.commit()

    assert reset(client).status_code == 204
    assert login(client, password=NEW_PASSWORD).status_code == 403


# ---------- 잠금: 이메일당 24시간 5번, IP당 1시간 30회 ----------


def test_five_wrong_answers_lock_for_24_hours(client, db_session) -> None:
    signup(client)
    for _ in range(5):
        assert reset(client, answer="틀린답").status_code == 400

    response = reset(client)  # 6번째는 맞는 답이라도 막는다

    assert response.status_code == 429
    assert 23 * 3600 < int(response.headers["Retry-After"]) <= 24 * 3600
    assert login(client).status_code == 200
    assert failures(db_session) == 5  # 잠긴 동안의 시도는 기록하지 않는다


def test_unknown_email_is_locked_the_same_way(client) -> None:
    statuses = [reset(client, email="nobody@campus.ac.kr").status_code for _ in range(6)]

    assert statuses == [400] * 5 + [429]


def test_lock_ends_24_hours_after_last_failure(client, db_session) -> None:
    signup(client)
    for _ in range(5):
        reset(client, answer="틀린답")
    for row in db_session.scalars(select(PasswordResetAttempt)).all():
        row.created_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24, minutes=1)
    db_session.commit()

    assert reset(client).status_code == 204


def test_success_clears_earlier_failures(client, db_session) -> None:
    signup(client)
    for _ in range(4):
        reset(client, answer="틀린답")
    assert reset(client).status_code == 204

    # 성공 전의 4번은 더 세지 않는다. 다시 5번 틀려야 잠긴다.
    statuses = [reset(client, answer="틀린답", new_password="another12345").status_code for _ in range(5)]
    assert statuses == [400] * 5
    assert reset(client, answer="틀린답").status_code == 429


def test_ip_limit_30_per_hour_counts_lookups_and_resets(client) -> None:
    # 이메일을 바꿔 가며 시도해도 같은 IP에서 질문 받기 + 재설정이 30번을 넘으면 막는다.
    statuses = [get_question(client, f"user{i}@campus.ac.kr").status_code for i in range(15)]
    statuses += [reset(client, email=f"user{i}@campus.ac.kr").status_code for i in range(15)]
    assert statuses == [200] * 15 + [400] * 15

    blocked_lookup = get_question(client, "late@campus.ac.kr")
    blocked_reset = reset(client, email="late@campus.ac.kr")

    assert (blocked_lookup.status_code, blocked_reset.status_code) == (429, 429)
    assert 1 <= int(blocked_lookup.headers["Retry-After"]) <= 3600


def test_attempts_store_email_hash_not_email(client, db_session) -> None:
    reset(client, answer="틀린답")

    row = db_session.scalar(select(PasswordResetAttempt))
    assert EMAIL not in row.email_hash and len(row.email_hash) == 64
    assert row.ip == "testclient" and row.success is False


# ---------- 기록과 다음 로그인 안내 ----------


def test_reset_is_written_to_admin_log_without_admin(client, db_session) -> None:
    user_id = signup(client)["id"]

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

    db_session.expire_all()
    user = db_session.scalar(select(User))
    from app.services import security_question_service

    assert security_question_service.changeable_at(db_session, user) is None
