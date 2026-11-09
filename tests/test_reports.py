from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Report
from app.services import report_service

REASONS = ["SPAM", "FRAUD", "ABUSE", "INAPPROPRIATE", "OTHER"]


@pytest.fixture
def seller(make_auth_headers) -> dict:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def reporter(make_auth_headers) -> dict:
    return make_auth_headers("reporter@campus.ac.kr", "신고자")


@pytest.fixture
def post(seller: dict, create_post) -> dict:
    return create_post(seller, title="수상한 글", description="입금 먼저 해주세요")


def user_id(client: TestClient, headers: dict) -> int:
    return client.get("/users/me", headers=headers).json()["id"]


def report_post(client: TestClient, post_id: int, headers: dict, **body):
    return client.post(f"/posts/{post_id}/reports", json={"reason": "SPAM", **body}, headers=headers)


def report_user(client: TestClient, target_id: int, headers: dict, **body):
    return client.post(f"/users/{target_id}/reports", json={"reason": "ABUSE", **body}, headers=headers)


def reports(db: Session) -> list[Report]:
    db.expire_all()
    return list(db.scalars(select(Report).order_by(Report.id)))


# ---------- 접수 ----------


@pytest.mark.parametrize("reason", REASONS)
def test_report_post_with_each_reason(client, db_session, seller, reporter, post, reason) -> None:
    response = report_post(client, post["id"], reporter, reason=reason, description="설명")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "created_at"}  # 대상·처리 결과는 돌려주지 않는다.
    saved = reports(db_session)[0]
    assert (saved.target_type, saved.target_id, saved.reason) == ("POST", post["id"], reason)
    assert saved.reported_user_id == user_id(client, seller)
    assert saved.reporter_id == user_id(client, reporter)
    assert saved.status == "PENDING"


def test_report_post_saves_snapshot(client, db_session, reporter, post) -> None:
    report_post(client, post["id"], reporter)

    saved = reports(db_session)[0]
    assert (saved.post_title_snapshot, saved.post_content_snapshot) == ("수상한 글", "입금 먼저 해주세요")


def test_report_user(client, db_session, seller, reporter) -> None:
    target = user_id(client, seller)

    response = report_user(client, target, reporter, description="욕설을 했어요")

    assert response.status_code == 201
    saved = reports(db_session)[0]
    assert (saved.target_type, saved.target_id, saved.reported_user_id) == ("USER", target, target)
    assert saved.post_title_snapshot is None


# ---------- 입력 검증 ----------


def test_other_reason_requires_description(client, reporter, post) -> None:
    for description in (None, "", "   "):
        response = report_post(client, post["id"], reporter, reason="OTHER", description=description)
        assert response.status_code == 422


def test_description_optional_for_other_reasons(client, db_session, reporter, post) -> None:
    assert report_post(client, post["id"], reporter, reason="FRAUD", description="  ").status_code == 201
    assert reports(db_session)[0].description is None


@pytest.mark.parametrize(("length", "status"), [(500, 201), (501, 422)])
def test_description_length_boundary(client, reporter, post, length, status) -> None:
    assert report_post(client, post["id"], reporter, description="가" * length).status_code == status


def test_description_is_stripped(client, db_session, reporter, post) -> None:
    report_post(client, post["id"], reporter, description="  앞뒤 공백  ")

    assert reports(db_session)[0].description == "앞뒤 공백"


@pytest.mark.parametrize("body", [{}, {"reason": "UNKNOWN"}, {"reason": "SPAM", "extra": 1}])
def test_invalid_body_returns_422(client, reporter, post, body) -> None:
    assert client.post(f"/posts/{post['id']}/reports", json=body, headers=reporter).status_code == 422


# ---------- 권한·대상 ----------


def test_report_requires_login(client, seller, post) -> None:
    assert client.post(f"/posts/{post['id']}/reports", json={"reason": "SPAM"}).status_code == 401
    assert client.post(f"/users/{user_id(client, seller)}/reports", json={"reason": "SPAM"}).status_code == 401


def test_report_missing_targets_returns_404(client, reporter) -> None:
    assert report_post(client, 9999, reporter).status_code == 404
    response = report_user(client, 9999, reporter)
    assert response.status_code == 404 and response.json()["detail"] == "사용자를 찾을 수 없습니다."


def test_report_own_post_returns_400(client, db_session, seller, post) -> None:
    response = report_post(client, post["id"], seller)

    assert response.status_code == 400
    assert response.json()["detail"] == "본인 글은 신고할 수 없습니다."
    assert reports(db_session) == []


def test_report_self_returns_400(client, reporter) -> None:
    response = report_user(client, user_id(client, reporter), reporter)

    assert response.status_code == 400
    assert response.json()["detail"] == "자기 자신은 신고할 수 없습니다."


# ---------- 중복 ----------


def test_duplicate_post_report_returns_409(client, db_session, reporter, post) -> None:
    report_post(client, post["id"], reporter, reason="SPAM")

    response = report_post(client, post["id"], reporter, reason="FRAUD")  # 사유를 바꿔도 같은 대상

    assert response.status_code == 409
    assert response.json()["detail"] == "이미 신고한 대상입니다."
    assert len(reports(db_session)) == 1


def test_duplicate_user_report_returns_409(client, seller, reporter) -> None:
    target = user_id(client, seller)
    report_user(client, target, reporter)

    assert report_user(client, target, reporter).status_code == 409


def test_post_and_user_reports_are_different_targets(client, seller, reporter, post) -> None:
    # 글 신고와 그 글 작성자 신고는 다른 대상이다.
    assert report_post(client, post["id"], reporter).status_code == 201
    assert report_user(client, user_id(client, seller), reporter).status_code == 201


def test_others_can_report_same_target(client, make_auth_headers, reporter, post) -> None:
    other = make_auth_headers("other@campus.ac.kr", "다른사람")
    report_post(client, post["id"], reporter)

    assert report_post(client, post["id"], other).status_code == 201


def test_duplicate_does_not_count_toward_rate_limit(client, reporter, post, monkeypatch) -> None:
    monkeypatch.setattr(report_service, "REPORT_RATE_LIMIT", report_service.ReportRateLimit(1, 3600))
    report_post(client, post["id"], reporter)

    # 이미 신고한 대상은 횟수 제한보다 먼저 409로 알려준다.
    assert report_post(client, post["id"], reporter).status_code == 409


# ---------- 횟수 제한 ----------


def test_rate_limit_returns_429(client, db_session, seller, reporter, create_post, monkeypatch) -> None:
    monkeypatch.setattr(report_service, "REPORT_RATE_LIMIT", report_service.ReportRateLimit(2, 3600))
    posts = [create_post(seller)["id"] for _ in range(3)]
    assert report_post(client, posts[0], reporter).status_code == 201
    assert report_user(client, user_id(client, seller), reporter).status_code == 201  # 글·사용자 신고를 함께 센다

    response = report_post(client, posts[1], reporter)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "3600"
    assert response.json()["detail"] == "신고를 너무 많이 하고 있습니다. 잠시 후 다시 시도해 주세요."
    assert len(reports(db_session)) == 2


def test_default_rate_limit_is_five_per_hour(client, seller, reporter, create_post) -> None:
    posts = [create_post(seller)["id"] for _ in range(6)]
    for post_id in posts[:5]:
        assert report_post(client, post_id, reporter).status_code == 201

    assert report_post(client, posts[5], reporter).status_code == 429


def test_rate_limit_resets_after_window(client, db_session, seller, reporter, create_post, monkeypatch) -> None:
    monkeypatch.setattr(report_service, "REPORT_RATE_LIMIT", report_service.ReportRateLimit(1, 3600))
    first, second = create_post(seller)["id"], create_post(seller)["id"]
    report_post(client, first, reporter)
    # 저장된 신고를 한 시간 전으로 옮긴다.
    db_now = db_session.scalar(select(func.now()))
    db_session.execute(update(Report).values(created_at=db_now - timedelta(seconds=3601)))
    db_session.commit()

    assert report_post(client, second, reporter).status_code == 201


def test_rate_limit_is_per_user(client, make_auth_headers, seller, reporter, create_post, monkeypatch) -> None:
    monkeypatch.setattr(report_service, "REPORT_RATE_LIMIT", report_service.ReportRateLimit(1, 3600))
    other = make_auth_headers("other@campus.ac.kr", "다른사람")
    report_post(client, create_post(seller)["id"], reporter)

    assert report_post(client, create_post(seller)["id"], other).status_code == 201


# ---------- 글 삭제·개인정보 ----------


def test_report_survives_post_deletion(client, db_session, seller, reporter, post) -> None:
    report_post(client, post["id"], reporter, description="사기 같아요")

    assert client.delete(f"/posts/{post['id']}", headers=seller).status_code == 204

    saved = reports(db_session)[0]
    assert saved.target_id == post["id"] and saved.post_title_snapshot == "수상한 글"


def test_reported_user_sees_no_trace(client, seller, reporter, post) -> None:
    before = {
        url: client.get(url, headers=seller).json()
        for url in (f"/posts/{post['id']}", "/posts", "/users/me", "/users/me/posts")
    }
    report_post(client, post["id"], reporter)
    report_user(client, user_id(client, seller), reporter)

    for url, old in before.items():
        new = client.get(url, headers=seller).json()
        assert new == old, url  # 신고 전후로 신고당한 사람의 응답이 그대로다.
        assert "신고자" not in str(new) and "reporter" not in str(new)
