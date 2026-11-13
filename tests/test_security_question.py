"""본인 확인 질문: 가입할 때 정하기, 내 정보에서 등록·변경, 답 규칙과 저장 방식."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import PasswordResetNotice, SecurityQuestion, User, UserRole
from app.schemas.security_question import PRESET_QUESTIONS, normalize_answer
from app.services import security_question_service
from tests.conftest import SECURITY_QUESTION

EMAIL = "student@campus.ac.kr"
PASSWORD = "password123"
URL = "/users/me/security-question"
NEW_QUESTION = {"question_key": "SCHOOL_CLUB", "answer": "천체관측반"}


def signup(client: TestClient, question: dict | None = SECURITY_QUESTION):
    body = {"email": EMAIL, "password": PASSWORD, "nickname": "책벌레"}
    if question is not None:
        body["security_question"] = question
    return client.post("/auth/signup", json=body)


def headers(client: TestClient, password: str = PASSWORD) -> dict:
    token = client.post("/auth/login", data={"username": EMAIL, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def set_question(client: TestClient, auth: dict, question: dict = NEW_QUESTION, password: str = PASSWORD):
    return client.put(URL, json={"password": password, "security_question": question}, headers=auth)


def reset(client: TestClient, answer: str, new_password: str = "newpassword456"):
    # 답 확인 → 확인증으로 변경. 답이 틀리면 답 확인 응답(400)을 돌려준다.
    checked = client.post("/auth/password-reset/verify", json={"email": EMAIL, "answer": answer})
    if checked.status_code != 200:
        return checked
    return client.post("/auth/password-reset", json={"reset_token": checked.json()["reset_token"], "new_password": new_password})


# ---------- 가입할 때 ----------


def test_signup_stores_question_and_hashed_answer(client, db_session) -> None:
    assert signup(client).status_code == 201

    row = db_session.scalar(select(SecurityQuestion))
    assert (row.preset_key, row.custom_text) == ("CHILDHOOD_SHOP", None)
    # 답 원문은 어디에도 저장하지 않는다. bcrypt 해시만 남는다.
    assert SECURITY_QUESTION["answer"] not in row.answer_hash and row.answer_hash.startswith("$2b$")
    assert security_question_service.verify_answer("해피 마트", row.answer_hash)


def test_signup_with_custom_question(client, db_session) -> None:
    assert signup(client, {"custom_question": "  내가 처음 키운 화분의 이름은?  ", "answer": "초록이"}).status_code == 201

    row = db_session.scalar(select(SecurityQuestion))
    assert (row.preset_key, row.custom_text) == (None, "내가 처음 키운 화분의 이름은?")


def test_signup_without_question_is_422_and_creates_nothing(client, db_session) -> None:
    assert signup(client, None).status_code == 422
    assert db_session.scalar(select(User)) is None


@pytest.mark.parametrize(
    "question",
    [
        {"answer": "해피마트"},  # 질문을 고르지 않음
        {"question_key": "CHILDHOOD_SHOP", "custom_question": "내가 만든 질문입니다?", "answer": "해피마트"},  # 둘 다
        {"question_key": "FAVORITE_COLOR", "answer": "파랑색"},  # 목록에 없는 질문
        {"question_key": "CHILDHOOD_SHOP", "answer": "가"},  # 1자
        {"question_key": "CHILDHOOD_SHOP", "answer": " 가 "},  # 공백을 빼면 1자
        {"question_key": "CHILDHOOD_SHOP", "answer": "가" * 21},  # 21자
        {"question_key": "CHILDHOOD_SHOP", "answer": "가 " * 50 + "가"},  # 원문 100자 초과
        {"question_key": "CHILDHOOD_SHOP", "answer": "가게 이름"},  # 질문에 그대로 들어 있는 답
        {"custom_question": "초록이의 이름은?", "answer": "초록이"},  # 직접 만든 질문에 답을 넣음
        {"custom_question": "짧음", "answer": "초록이"},  # 질문 5자 미만
        {"custom_question": "가" * 61, "answer": "초록이"},  # 질문 60자 초과
        {"custom_question": "   ", "answer": "초록이"},  # 빈 질문은 보내지 않은 것으로 본다
        {"question_key": "CHILDHOOD_SHOP", "answer": "해피마트", "hint": "x"},  # 모르는 필드
    ],
)
def test_signup_rejects_bad_question(client, db_session, question) -> None:
    assert signup(client, question).status_code == 422
    assert db_session.scalar(select(User)) is None


def test_answer_length_boundaries(client) -> None:
    assert signup(client, {"question_key": "CHILDHOOD_SHOP", "answer": "가 나"}).status_code == 201  # 공백 빼고 2자
    client.post("/users/me/withdraw", json={"password": PASSWORD}, headers=headers(client))
    assert signup(client, {"question_key": "CHILDHOOD_SHOP", "answer": "가" * 20}).status_code == 201


def test_normalize_answer() -> None:
    assert normalize_answer(" Happy  Mart ") == normalize_answer("happymart") == "happymart"
    assert normalize_answer("해피　마트\n") == "해피마트"
    assert normalize_answer("ＡＢＣ１２") == "abc12"


def test_long_unicode_answer_fits_bcrypt() -> None:
    # 20자 이모지·한글은 72바이트를 넘지만, SHA-256으로 줄인 뒤 bcrypt에 넣으므로 끝까지 비교된다.
    answer_a, answer_b = "가" * 19 + "나", "가" * 19 + "다"
    hashed = security_question_service.hash_answer(answer_a)
    assert security_question_service.verify_answer(answer_a, hashed)
    assert not security_question_service.verify_answer(answer_b, hashed)


def test_preset_list_has_nine_questions() -> None:
    assert len(PRESET_QUESTIONS) == 9


# ---------- 내 정보: 보기·등록·변경 ----------


def test_me_shows_question_but_never_answer(client) -> None:
    signup(client)

    body = client.get("/users/me", headers=headers(client)).json()

    assert body["security_question"] == PRESET_QUESTIONS["CHILDHOOD_SHOP"]
    assert body["security_question_changeable_at"] is None
    assert SECURITY_QUESTION["answer"] not in str(body)


def test_change_question_needs_password_and_replaces_answer(client) -> None:
    signup(client)
    auth = headers(client)

    wrong = set_question(client, auth, password="wrongpassword")
    assert (wrong.status_code, wrong.json()["detail"]) == (400, "현재 비밀번호가 올바르지 않습니다.")

    response = set_question(client, auth)
    assert response.status_code == 200
    assert response.json()["security_question"] == PRESET_QUESTIONS["SCHOOL_CLUB"]
    # 예전 답은 바로 쓸 수 없고, 새 답으로 재설정된다.
    assert reset(client, SECURITY_QUESTION["answer"]).status_code == 400
    assert reset(client, NEW_QUESTION["answer"]).status_code == 204


def test_existing_user_without_question_sees_null_and_can_register(client, db_session) -> None:
    signup(client)
    security_question_service.delete_for_user(db_session, db_session.scalar(select(User)).id)
    db_session.commit()
    auth = headers(client)
    assert client.get("/users/me", headers=auth).json()["security_question"] is None

    assert set_question(client, auth, {"custom_question": "내가 처음 키운 화분의 이름은?", "answer": "초록이"}).status_code == 200

    assert client.get("/users/me", headers=auth).json()["security_question"] == "내가 처음 키운 화분의 이름은?"
    assert len(db_session.scalars(select(SecurityQuestion)).all()) == 1


def test_admin_cannot_use_question(client, db_session) -> None:
    signup(client)
    db_session.scalar(select(User)).role = UserRole.ADMIN
    db_session.commit()
    auth = headers(client)

    assert client.get("/users/me", headers=auth).json()["security_question"] is None
    response = set_question(client, auth)
    assert response.status_code == 400
    assert "관리자" in response.json()["detail"]


def test_question_change_locked_7_days_after_question_reset(client, db_session) -> None:
    signup(client)
    assert reset(client, SECURITY_QUESTION["answer"]).status_code == 204
    auth = headers(client, "newpassword456")

    me = client.get("/users/me", headers=auth).json()
    assert me["security_question_changeable_at"] is not None
    response = set_question(client, auth, password="newpassword456")
    assert response.status_code == 400
    assert "7일" in response.json()["detail"]

    # 7일이 지나면 바꿀 수 있다.
    for notice in db_session.scalars(select(PasswordResetNotice)).all():
        notice.reset_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=7, minutes=1)
    db_session.commit()
    assert set_question(client, auth, password="newpassword456").status_code == 200


def test_wrong_password_checked_before_7_day_lock(client) -> None:
    signup(client)
    reset(client, SECURITY_QUESTION["answer"])
    auth = headers(client, "newpassword456")

    assert set_question(client, auth, password="wrongpassword").json()["detail"] == "현재 비밀번호가 올바르지 않습니다."


def test_suspended_user_can_change_question(client, db_session) -> None:
    signup(client)
    auth = headers(client)
    db_session.scalar(select(User)).suspended_until = (datetime.now(UTC) + timedelta(days=3)).replace(tzinfo=None)
    db_session.commit()

    assert set_question(client, auth).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"security_question": NEW_QUESTION},
        {"password": PASSWORD},
        {"password": PASSWORD, "security_question": {"question_key": "SCHOOL_CLUB", "answer": "x"}},
    ],
)
def test_change_question_validates_body(client, body) -> None:
    signup(client)
    assert client.put(URL, json=body, headers=headers(client)).status_code == 422


def test_change_question_requires_login(client) -> None:
    assert client.put(URL, json={"password": PASSWORD, "security_question": NEW_QUESTION}).status_code == 401


def test_withdraw_deletes_question_and_notices(client, db_session) -> None:
    signup(client)
    reset(client, SECURITY_QUESTION["answer"])

    client.post("/users/me/withdraw", json={"password": "newpassword456"}, headers=headers(client, "newpassword456"))

    assert db_session.scalar(select(SecurityQuestion)) is None
    assert db_session.scalar(select(PasswordResetNotice)) is None

