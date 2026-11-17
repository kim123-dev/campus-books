"""거래 약속(만남 약속 카드): 제안·변경·수락·거절·취소, 동시 제안, 만남 장소, 종 알림 계산."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentStatus, MeetingPlace, Message, MessageReportSnapshot, School, User
from app.services import appointment_service, conversation_service, school_service, user_service
from app.services.conversation_service import RateLimit
from tests.conftest import TEST_PASSWORD

KST = user_service.KST


@pytest.fixture
def seller(make_auth_headers) -> dict:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def buyer(make_auth_headers) -> dict:
    return make_auth_headers("buyer@campus.ac.kr", "구매자")


@pytest.fixture
def stranger(make_auth_headers) -> dict:
    return make_auth_headers("stranger@campus.ac.kr", "제삼자")


@pytest.fixture
def post(seller: dict, create_post) -> dict:
    return create_post(seller)


@pytest.fixture
def conversation(client: TestClient, buyer: dict, post: dict) -> dict:
    response = client.post(f"/posts/{post['id']}/conversations", headers=buyer)
    assert response.status_code == 201, response.text
    return response.json()


def tomorrow_kst() -> str:
    return (user_service.utc_now().astimezone(KST) + timedelta(days=1)).date().isoformat()


def propose(client: TestClient, conversation_id: int, headers: dict, **overrides):
    body = {"date": tomorrow_kst(), "time": "15:00", "place_name": "학생회관 앞", **overrides}
    body = {key: value for key, value in body.items() if value is not None}
    return client.post(f"/conversations/{conversation_id}/appointments", json=body, headers=headers)


def proposed(client: TestClient, conversation_id: int, headers: dict, **overrides) -> dict:
    response = propose(client, conversation_id, headers, **overrides)
    assert response.status_code == 201, response.text
    return response.json()


def act(client: TestClient, appointment_id: int, action: str, headers: dict):
    return client.post(f"/appointments/{appointment_id}/{action}", headers=headers)


def messages(client: TestClient, conversation_id: int, headers: dict) -> list[dict]:
    return client.get(f"/conversations/{conversation_id}/messages", headers=headers).json()["items"]


def user_by_email(db: Session, email: str) -> User:
    return db.scalar(select(User).where(User.email == email))


def set_starts_at(db: Session, appointment_id: int, value: datetime) -> None:
    """약속 시각을 직접 바꾼다. DB에는 시간대 없이 UTC로 저장한다."""
    db.execute(
        update(Appointment).where(Appointment.id == appointment_id).values(starts_at=value.astimezone(UTC).replace(tzinfo=None))
    )
    db.commit()


@pytest.fixture
def no_rate_limit(monkeypatch) -> None:
    monkeypatch.setattr(conversation_service, "MESSAGE_RATE_LIMIT", RateLimit(10_000, 10))


# ---------- 제안 ----------


def test_propose_creates_card_message_with_korean_summary(client, conversation, buyer, seller) -> None:
    body = proposed(client, conversation["id"], buyer, time="15:00")

    card = body["appointment"]
    assert card["event"] == "PROPOSE" and card["status"] == "PROPOSED"
    assert card["is_mine"] is True and card["is_past"] is False and card["replaces_id"] is None
    assert card["place_name"] == "학생회관 앞" and card["meeting_place_id"] is None
    assert body["content"].startswith("[약속 제안] ") and body["content"].endswith(" 15:00 · 학생회관 앞")
    assert body["is_mine"] is True and body["has_image"] is False

    # 상대 화면: 같은 메시지가 상대 말풍선으로, 받은 쪽(is_mine false)이라 수락·거절할 수 있다.
    theirs = messages(client, conversation["id"], seller)
    assert [m["appointment"]["is_mine"] for m in theirs] == [False]
    # 쪽지함 미리보기·안 읽은 수도 일반 쪽지와 같다.
    item = client.get("/conversations", headers=seller).json()["items"][0]
    assert item["last_message"]["content"] == body["content"]


def test_time_is_read_as_kst_and_stored_as_utc(client, conversation, buyer, db_session) -> None:
    day = tomorrow_kst()
    body = proposed(client, conversation["id"], buyer, date=day, time="00:30")

    expected = datetime.fromisoformat(f"{day}T00:30:00+09:00").astimezone(UTC)
    assert datetime.fromisoformat(body["appointment"]["starts_at"].replace("Z", "+00:00")) == expected
    stored = db_session.scalar(select(Appointment.starts_at))
    assert user_service.as_utc(stored) == expected


def test_seconds_are_dropped(client, conversation, buyer) -> None:
    body = proposed(client, conversation["id"], buyer, time="15:00:59")
    assert body["appointment"]["starts_at"].startswith(f"{tomorrow_kst()}T06:00:00")


@pytest.mark.parametrize(
    "overrides",
    [
        {"place_name": None},  # 장소 없음
        {"place_name": "   "},  # 공백만
        {"place_name": "가" * 101},
        {"meeting_place_id": 1},  # 목록 장소와 직접 입력을 함께
        {"time": "25:00"},
        {"date": "2026-02-30"},
    ],
)
def test_invalid_input_returns_422(client, conversation, buyer, overrides) -> None:
    assert propose(client, conversation["id"], buyer, **overrides).status_code == 422


def test_unknown_field_returns_422(client, conversation, buyer) -> None:
    assert propose(client, conversation["id"], buyer, status="ACCEPTED").status_code == 422


def test_past_or_too_far_time_returns_400(client, conversation, buyer) -> None:
    yesterday = (user_service.utc_now().astimezone(KST) - timedelta(days=1)).date().isoformat()
    past = propose(client, conversation["id"], buyer, date=yesterday)
    assert past.status_code == 400 and past.json()["detail"] == "약속 시각은 지금 이후로 정해 주세요."

    far = (user_service.utc_now().astimezone(KST) + timedelta(days=appointment_service.MAX_DAYS_AHEAD + 1)).date().isoformat()
    assert propose(client, conversation["id"], buyer, date=far).status_code == 400


def test_sold_or_deleted_post_rejects_new_proposal(client, conversation, post, seller, buyer) -> None:
    existing = proposed(client, conversation["id"], buyer)
    client.patch(f"/posts/{post['id']}/status", json={"status": "SOLD"}, headers=seller)
    sold = propose(client, conversation["id"], buyer)
    assert sold.status_code == 400
    assert sold.json()["detail"] == "판매 완료되었거나 삭제된 글에서는 새 약속을 제안할 수 없습니다."
    # 이미 잡힌 약속은 그대로 보이고 수락할 수 있다.
    assert act(client, existing["appointment"]["id"], "accept", seller).status_code == 201

    client.patch(f"/posts/{post['id']}/status", json={"status": "ON_SALE"}, headers=seller)
    assert client.delete(f"/posts/{post['id']}", headers=seller).status_code == 204
    assert propose(client, conversation["id"], seller).status_code == 400
    assert [m["appointment"]["status"] for m in messages(client, conversation["id"], buyer)] == ["ACCEPTED", "ACCEPTED"]


def test_reserved_post_allows_proposal(client, conversation, post, seller) -> None:
    client.patch(f"/posts/{post['id']}/status", json={"status": "RESERVED"}, headers=seller)
    assert propose(client, conversation["id"], seller).status_code == 201


def test_access_rules(client, conversation, buyer, stranger) -> None:
    assert propose(client, conversation["id"], {}).status_code == 401
    assert propose(client, conversation["id"], stranger).status_code == 403
    assert propose(client, 9999, buyer).status_code == 404
    card = proposed(client, conversation["id"], buyer)["appointment"]
    assert act(client, card["id"], "accept", stranger).status_code == 403
    assert act(client, 9999, "accept", buyer).status_code == 404
    assert act(client, card["id"], "cancel", {}).status_code == 401


def test_blocked_or_withdrawn_partner_returns_400(client, conversation, buyer, seller) -> None:
    card = proposed(client, conversation["id"], buyer)["appointment"]
    seller_id = client.get("/users/me", headers=seller).json()["id"]
    client.post(f"/users/{seller_id}/block", headers=buyer)
    assert propose(client, conversation["id"], buyer).status_code == 400
    assert act(client, card["id"], "accept", seller).status_code == 400
    client.delete(f"/users/{seller_id}/block", headers=buyer)

    client.post("/users/me/withdraw", json={"password": TEST_PASSWORD}, headers=seller)
    assert propose(client, conversation["id"], buyer).status_code == 400


def test_suspended_user_gets_403(client, conversation, buyer, db_session) -> None:
    user = user_by_email(db_session, "buyer@campus.ac.kr")
    user.suspended_until = (user_service.utc_now() + timedelta(days=1)).astimezone(UTC).replace(tzinfo=None)
    db_session.commit()
    assert propose(client, conversation["id"], buyer).status_code == 403


def test_rate_limit_applies_like_messages(client, conversation, buyer, monkeypatch) -> None:
    monkeypatch.setattr(conversation_service, "MESSAGE_RATE_LIMIT", RateLimit(2, 10))
    client.post(f"/conversations/{conversation['id']}/messages", json={"content": "안녕하세요"}, headers=buyer)
    assert propose(client, conversation["id"], buyer).status_code == 201
    assert propose(client, conversation["id"], buyer).status_code == 429


# ---------- 수락·거절·취소 ----------


def test_accept_adds_message_and_updates_card(client, conversation, buyer, seller) -> None:
    card = proposed(client, conversation["id"], buyer)["appointment"]
    response = act(client, card["id"], "accept", seller)

    assert response.status_code == 201
    body = response.json()
    assert body["content"].startswith("[약속 수락] ")
    assert body["appointment"]["event"] == "ACCEPT" and body["appointment"]["status"] == "ACCEPTED"
    # 제안 카드도 지금 상태(수락됨)로 다시 내려온다.
    items = messages(client, conversation["id"], buyer)
    assert [(m["appointment"]["event"], m["appointment"]["status"]) for m in items] == [
        ("PROPOSE", "ACCEPTED"),
        ("ACCEPT", "ACCEPTED"),
    ]


def test_proposer_cannot_respond_to_own(client, conversation, buyer) -> None:
    card = proposed(client, conversation["id"], buyer)["appointment"]
    response = act(client, card["id"], "accept", buyer)
    assert response.status_code == 400 and response.json()["detail"] == "내가 제안한 약속은 수락하거나 거절할 수 없습니다."


def test_decline_then_respond_again_is_409(client, conversation, buyer, seller) -> None:
    card = proposed(client, conversation["id"], buyer)["appointment"]
    declined = act(client, card["id"], "decline", seller)
    assert declined.status_code == 201 and declined.json()["appointment"]["status"] == "DECLINED"
    assert declined.json()["content"].startswith("[약속 거절] ")
    assert act(client, card["id"], "accept", seller).status_code == 409
    assert act(client, card["id"], "cancel", buyer).status_code == 409
    # 거절된 약속은 진행 중이 아니므로, 다음 제안은 변경이 아닌 새 제안이다.
    assert proposed(client, conversation["id"], seller)["appointment"]["replaces_id"] is None


def test_accept_twice_is_409(client, conversation, buyer, seller) -> None:
    card = proposed(client, conversation["id"], buyer)["appointment"]
    assert act(client, card["id"], "accept", seller).status_code == 201
    assert act(client, card["id"], "accept", seller).status_code == 409
    assert act(client, card["id"], "decline", seller).status_code == 409


@pytest.mark.parametrize("accept_first", [False, True])
def test_proposer_can_cancel_proposed_or_accepted(client, conversation, buyer, seller, accept_first) -> None:
    card = proposed(client, conversation["id"], buyer)["appointment"]
    if accept_first:
        act(client, card["id"], "accept", seller)
    assert act(client, card["id"], "cancel", seller).status_code == 400  # 제안한 사람만
    canceled = act(client, card["id"], "cancel", buyer)
    assert canceled.status_code == 201
    assert canceled.json()["appointment"]["status"] == "CANCELED"
    assert canceled.json()["content"].startswith("[약속 취소] ")
    assert act(client, card["id"], "cancel", buyer).status_code == 409


def test_started_appointment_cannot_change_and_shows_past(client, conversation, buyer, seller, db_session) -> None:
    card = proposed(client, conversation["id"], buyer)["appointment"]
    set_starts_at(db_session, card["id"], user_service.utc_now() - timedelta(minutes=1))

    assert act(client, card["id"], "accept", seller).json()["detail"] == "약속 시각이 지나 바꿀 수 없습니다."
    assert act(client, card["id"], "cancel", buyer).status_code == 400
    item = messages(client, conversation["id"], seller)[0]["appointment"]
    assert item["status"] == "PROPOSED" and item["is_past"] is True  # "지남"은 저장하지 않고 계산


# ---------- 변경 ----------


def test_new_proposal_replaces_active_one(client, conversation, buyer, seller, no_rate_limit) -> None:
    first = proposed(client, conversation["id"], buyer)["appointment"]
    act(client, first["id"], "accept", seller)
    # 받은 쪽(판매자)도 시간을 바꾸자고 새 카드를 보낼 수 있다.
    second = proposed(client, conversation["id"], seller, time="18:00")

    assert second["content"].startswith("[약속 변경] ")
    assert second["appointment"]["replaces_id"] == first["id"]
    statuses = [(m["appointment"]["id"], m["appointment"]["status"]) for m in messages(client, conversation["id"], buyer)]
    assert statuses == [(first["id"], "REPLACED"), (first["id"], "REPLACED"), (second["appointment"]["id"], "PROPOSED")]
    assert act(client, first["id"], "cancel", buyer).status_code == 409


def test_past_accepted_is_not_marked_replaced(client, conversation, buyer, seller, db_session) -> None:
    first = proposed(client, conversation["id"], buyer)["appointment"]
    act(client, first["id"], "accept", seller)
    set_starts_at(db_session, first["id"], user_service.utc_now() - timedelta(days=1))

    second = proposed(client, conversation["id"], buyer)["appointment"]
    assert second["replaces_id"] is None
    assert db_session.get(Appointment, first["id"]).status == AppointmentStatus.ACCEPTED


# ---------- 동시 제안 ----------


def test_db_allows_only_one_active_appointment_per_conversation(client, conversation, buyer, db_session) -> None:
    card = proposed(client, conversation["id"], buyer)["appointment"]
    existing = db_session.get(Appointment, card["id"])
    db_session.add(
        Appointment(
            conversation_id=existing.conversation_id,
            proposer_id=existing.proposer_id,
            starts_at=existing.starts_at,
            place_name="다른 곳",
            status=AppointmentStatus.PROPOSED,
            active_conversation_id=existing.conversation_id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_concurrent_proposal_returns_409_and_leaves_one_active(
    client, conversation, buyer, seller, db_session, monkeypatch
) -> None:
    proposed(client, conversation["id"], buyer)
    message_count = db_session.scalar(select(func.count()).select_from(Message))
    # 다른 요청이 "진행 중인 약속 없음"을 읽은 직후 상대의 제안이 먼저 저장된 상황을 만든다.
    monkeypatch.setattr(appointment_service, "_active", lambda db, conversation_id: None)

    response = propose(client, conversation["id"], seller)

    assert response.status_code == 409
    assert response.json()["detail"].startswith("방금 다른 약속 제안이 먼저 등록되었습니다.")
    active = db_session.scalar(
        select(func.count()).select_from(Appointment).where(Appointment.active_conversation_id.is_not(None))
    )
    assert active == 1
    # 실패한 제안의 쪽지는 남지 않는다. (같은 트랜잭션에서 되돌림)
    assert db_session.scalar(select(func.count()).select_from(Message)) == message_count


# ---------- 신고·나가기와 함께 ----------


def test_card_message_can_be_reported_with_summary(client, conversation, buyer, seller, db_session) -> None:
    card = proposed(client, conversation["id"], buyer)
    response = client.post(f"/messages/{card['id']}/reports", json={"reason": "ABUSE"}, headers=seller)
    assert response.status_code == 201, response.text
    # 신고 증거에는 서버가 만든 한국어 요약(장소 포함)이 그대로 남는다.
    assert db_session.scalar(select(MessageReportSnapshot.content)) == card["content"]


# ---------- 만남 장소 ----------


@pytest.fixture
def school_post(client, seller, buyer, create_post, db_session) -> dict:
    """학교가 있는 글과 그 대화방, 장소 목록(활성 2·비활성 1)과 다른 학교 장소 하나."""
    school_service.seed_default(db_session)
    school_id = db_session.scalar(select(School.id))
    other = School(name="부산대학교")
    db_session.add(other)
    db_session.flush()
    places = [
        MeetingPlace(school_id=school_id, name="도서관 1층", sort_order=2),
        MeetingPlace(school_id=school_id, name="학생회관 앞", sort_order=1),
        MeetingPlace(school_id=school_id, name="닫은 장소", is_active=False),
        MeetingPlace(school_id=other.id, name="다른 학교 정문"),
    ]
    db_session.add_all(places)
    db_session.commit()
    post = create_post(seller, school_id=school_id)
    conversation = client.post(f"/posts/{post['id']}/conversations", headers=buyer).json()
    return {"conversation": conversation, "places": {p.name: p.id for p in places}}


def test_meeting_places_follow_post_school(client, school_post, buyer, stranger) -> None:
    url = f"/conversations/{school_post['conversation']['id']}/meeting-places"
    assert [p["name"] for p in client.get(url, headers=buyer).json()["items"]] == ["학생회관 앞", "도서관 1층"]
    assert client.get(url, headers=stranger).status_code == 403
    assert client.get(url).status_code == 401


def test_meeting_places_empty_without_school(client, conversation, buyer) -> None:
    response = client.get(f"/conversations/{conversation['id']}/meeting-places", headers=buyer)
    assert response.status_code == 200 and response.json() == {"items": []}


def test_propose_with_place_from_list_keeps_name(client, school_post, buyer) -> None:
    places = school_post["places"]
    body = proposed(client, school_post["conversation"]["id"], buyer, place_name=None, meeting_place_id=places["도서관 1층"])
    assert body["appointment"]["place_name"] == "도서관 1층"
    assert body["appointment"]["meeting_place_id"] == places["도서관 1층"]


@pytest.mark.parametrize("name", ["닫은 장소", "다른 학교 정문"])
def test_inactive_or_other_school_place_returns_400(client, school_post, buyer, name) -> None:
    response = propose(client, school_post["conversation"]["id"], buyer, place_name=None, meeting_place_id=school_post["places"][name])
    assert response.status_code == 400


def test_place_id_without_post_school_returns_400(client, conversation, buyer) -> None:
    assert propose(client, conversation["id"], buyer, place_name=None, meeting_place_id=999).status_code == 400


# ---------- 종 알림 (계산) ----------


def accepted(client, conversation, buyer, seller) -> int:
    card = proposed(client, conversation["id"], buyer)["appointment"]
    assert act(client, card["id"], "accept", seller).status_code == 201
    return card["id"]


def kst(day: str, hm: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{hm}:00+09:00")


def reminder_ids(db: Session, email: str, now: datetime) -> list[int]:
    return [r.appointment_id for r in appointment_service.list_reminders(db, user_by_email(db, email), now=now)]


def test_reminder_window_is_kst_day_start_to_one_hour_after(client, conversation, buyer, seller, db_session) -> None:
    appointment_id = accepted(client, conversation, buyer, seller)
    set_starts_at(db_session, appointment_id, kst("2026-11-20", "23:30"))

    seen = lambda now: appointment_id in reminder_ids(db_session, "buyer@campus.ac.kr", now)  # noqa: E731
    assert not seen(kst("2026-11-19", "23:59"))  # 전날
    assert seen(kst("2026-11-20", "00:00"))  # 당일 0시부터
    assert seen(kst("2026-11-21", "00:30"))  # 약속 1시간 뒤까지(자정을 넘어도)
    assert not seen(kst("2026-11-21", "00:31"))


def test_reminder_shows_to_both_and_only_accepted(client, conversation, buyer, seller, db_session, no_rate_limit) -> None:
    appointment_id = accepted(client, conversation, buyer, seller)
    set_starts_at(db_session, appointment_id, kst("2026-11-20", "15:00"))
    now = kst("2026-11-20", "09:00")
    assert reminder_ids(db_session, "buyer@campus.ac.kr", now) == [appointment_id]
    assert reminder_ids(db_session, "seller@campus.ac.kr", now) == [appointment_id]

    # 진행 중인 약속을 새 제안으로 바꾸면(제안 상태) 알림에서 빠진다.
    set_starts_at(db_session, appointment_id, user_service.utc_now() + timedelta(hours=2))
    proposed(client, conversation["id"], buyer)
    assert reminder_ids(db_session, "buyer@campus.ac.kr", user_service.utc_now()) == []


def test_reminder_api_and_canceled_disappears(client, conversation, buyer, seller, db_session) -> None:
    appointment_id = accepted(client, conversation, buyer, seller)
    set_starts_at(db_session, appointment_id, user_service.utc_now() + timedelta(minutes=10))
    body = client.get("/users/me/appointment-reminders", headers=seller).json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["appointment_id"] == appointment_id and item["conversation_id"] == conversation["id"]
    assert item["partner_nickname"] == "구매자" and item["place_name"] == "학생회관 앞"
    assert item["post_title"] == conversation["post"]["title"]

    act(client, appointment_id, "cancel", buyer)
    assert client.get("/users/me/appointment-reminders", headers=seller).json()["total"] == 0
    assert client.get("/users/me/appointment-reminders").status_code == 401


def test_reminder_excludes_leaver_and_withdrawn_partner(client, conversation, buyer, seller, db_session) -> None:
    appointment_id = accepted(client, conversation, buyer, seller)
    set_starts_at(db_session, appointment_id, kst("2026-11-20", "15:00"))
    now = kst("2026-11-20", "09:00")

    client.post(f"/conversations/{conversation['id']}/leave", headers=buyer)
    assert reminder_ids(db_session, "buyer@campus.ac.kr", now) == []  # 나간 사람
    assert reminder_ids(db_session, "seller@campus.ac.kr", now) == [appointment_id]  # 상대에게는 그대로

    client.post("/users/me/withdraw", json={"password": TEST_PASSWORD}, headers=buyer)
    assert reminder_ids(db_session, "seller@campus.ac.kr", now) == []  # 상대가 탈퇴
