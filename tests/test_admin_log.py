"""관리 기록: 신고 처리마다 한 줄, 강제 조치는 사유 필수, 실패하면 기록 없음, 목록·필터·쿼리 수."""

import pytest
from sqlalchemy import select

from app.models import Post, Report, User
from app.services import report_service
from tests.admin_helpers import (
    count_queries,
    last_log,
    log_count,
    make_review,
    report_post,
    resolve,
    user_id,
)


@pytest.fixture
def admin(make_admin_headers) -> dict:
    return make_admin_headers()


@pytest.fixture
def seller(make_auth_headers) -> dict:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def reporter(make_auth_headers) -> dict:
    return make_auth_headers("reporter@campus.ac.kr", "신고자")


@pytest.fixture
def post(seller, create_post) -> dict:
    return create_post(seller, title="수상한 글", book_title="선형대수")


# ---------- 신고 처리 → 기록 한 줄 ----------


def test_dismiss_writes_one_log_without_reason(client, db_session, admin, seller, reporter, post) -> None:
    report_id = report_post(client, post["id"], reporter)

    assert resolve(client, report_id, admin, action="DISMISS").status_code == 200

    assert log_count(db_session) == 1
    entry = last_log(db_session)
    assert (entry.action, entry.target_type, entry.target_id) == ("DISMISS_REPORT", "REPORT", report_id)
    assert entry.admin_id == user_id(client, admin)
    assert entry.target_user_id == user_id(client, seller)
    assert entry.reason is None
    assert entry.detail == {"report_id": report_id}


def test_delete_post_log_keeps_post_copy(client, db_session, admin, seller, reporter, make_auth_headers, post) -> None:
    first = report_post(client, post["id"], reporter)
    second = report_post(client, post["id"], make_auth_headers("r2@campus.ac.kr", "신고자2"))

    response = resolve(client, first, admin, action="DELETE_POST", note="사기 글")

    assert response.status_code == 200
    assert log_count(db_session) == 1  # 함께 처리된 신고가 있어도 기록은 한 줄
    entry = last_log(db_session)
    assert (entry.action, entry.target_type, entry.target_id) == ("DELETE_POST", "POST", post["id"])
    assert entry.target_user_id == user_id(client, seller)
    assert entry.reason == "사기 글"
    assert entry.detail == {
        "report_id": first,
        "resolved_ids": [first, second],
        "post_title": "수상한 글",
        "book_title": "선형대수",
    }


def test_suspend_log_has_days_and_end(client, db_session, admin, seller, reporter, post) -> None:
    report_id = report_post(client, post["id"], reporter)

    body = resolve(client, report_id, admin, action="SUSPEND", suspend_days=7, note="반복 사기").json()

    entry = last_log(db_session)
    assert (entry.action, entry.target_type, entry.target_id) == ("SUSPEND", "USER", user_id(client, seller))
    assert entry.reason == "반복 사기"
    assert entry.detail["days"] == 7
    assert entry.detail["suspended_until"].startswith(body["suspended_until"][:16])


def test_hide_review_log_targets_writer(client, db_session, admin, make_auth_headers, create_post) -> None:
    seller = make_auth_headers("s2@campus.ac.kr", "판매자2")
    buyer = make_auth_headers("b2@campus.ac.kr", "구매자2")
    review = make_review(client, seller, buyer, create_post)
    report_id = client.post(f"/reviews/{review['id']}/reports", json={"reason": "ABUSE"}, headers=seller).json()["id"]

    assert resolve(client, report_id, admin, action="HIDE_REVIEW", note="욕설").status_code == 200

    entry = last_log(db_session)
    assert (entry.action, entry.target_type, entry.target_id) == ("HIDE_REVIEW", "REVIEW", review["id"])
    assert entry.target_user_id == user_id(client, buyer)  # 후기를 쓴 사람


# ---------- 강제 조치는 사유 필수 ----------


@pytest.mark.parametrize(
    "body",
    [
        {"action": "DELETE_POST"},
        {"action": "SUSPEND", "suspend_days": 3},
        {"action": "SUSPEND", "suspend_days": 3, "note": "   "},
        {"action": "HIDE_REVIEW"},
    ],
    ids=["delete", "suspend", "suspend-blank", "hide"],
)
def test_forced_action_without_reason_is_422(client, db_session, admin, seller, reporter, post, body) -> None:
    report_id = report_post(client, post["id"], reporter)

    response = resolve(client, report_id, admin, **body)

    assert response.status_code == 422
    assert "사유" in response.text
    # 아무것도 바뀌지 않고 기록도 없다.
    db_session.expire_all()
    assert db_session.get(Report, report_id).status == "PENDING"
    assert db_session.get(Post, post["id"]) is not None
    assert db_session.scalar(select(User).where(User.email == "seller@campus.ac.kr")).suspended_until is None
    assert log_count(db_session) == 0


def test_failed_resolution_writes_no_log(client, db_session, admin, reporter, post) -> None:
    report_id = report_post(client, post["id"], reporter)
    resolve(client, report_id, admin, action="DISMISS")

    assert resolve(client, report_id, admin, action="DISMISS").status_code == 409
    assert resolve(client, 9999, admin, action="DISMISS").status_code == 404
    assert log_count(db_session) == 1


# ---------- 목록 ----------


def list_actions(client, headers, **params) -> dict:
    response = client.get("/admin/actions", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_list_fields_newest_first(client, admin, seller, reporter, post, create_post) -> None:
    first = report_post(client, post["id"], reporter)
    second = report_post(client, create_post(seller)["id"], reporter)
    resolve(client, first, admin, action="DISMISS", note="문제 없음")
    resolve(client, second, admin, action="SUSPEND", suspend_days=1, note="경고")

    body = list_actions(client, admin)

    assert body["total"] == 2
    assert [item["action"] for item in body["items"]] == ["SUSPEND", "DISMISS_REPORT"]
    item = body["items"][1]
    assert item["admin"] == {"id": user_id(client, admin), "nickname": "관리자", "withdrawn": False}
    assert item["target_user"] == {"id": user_id(client, seller), "nickname": "판매자", "withdrawn": False}
    assert (item["target_type"], item["target_id"], item["reason"]) == ("REPORT", first, "문제 없음")
    assert item["detail"] == {"report_id": first}


def test_list_filters_and_pagination(client, admin, make_auth_headers, seller, reporter, post, create_post) -> None:
    other = make_auth_headers("other@campus.ac.kr", "다른사람")
    ids = [report_post(client, post["id"], reporter), report_post(client, create_post(other)["id"], reporter)]
    resolve(client, ids[0], admin, action="DISMISS")
    resolve(client, ids[1], admin, action="DISMISS")

    by_user = list_actions(client, admin, target_user_id=user_id(client, other))
    assert [i["target_id"] for i in by_user["items"]] == [ids[1]]
    assert list_actions(client, admin, action="SUSPEND")["total"] == 0
    assert list_actions(client, admin, admin_id=user_id(client, admin))["total"] == 2
    page2 = list_actions(client, admin, size=1, page=2)
    assert page2["total"] == 2 and [i["target_id"] for i in page2["items"]] == [ids[0]]


@pytest.mark.parametrize("params", [{"action": "HACK"}, {"page": 0}, {"size": 101}, {"target_user_id": 0}])
def test_list_invalid_params_422(client, admin, params) -> None:
    assert client.get("/admin/actions", params=params, headers=admin).status_code == 422


def test_list_has_no_email(client, admin, reporter, post) -> None:
    resolve(client, report_post(client, post["id"], reporter), admin, action="DISMISS")

    assert "@" not in client.get("/admin/actions", headers=admin).text


def test_list_query_count_does_not_grow(client, admin, seller, reporter, create_post, monkeypatch) -> None:
    monkeypatch.setattr(report_service, "REPORT_RATE_LIMIT", report_service.ReportRateLimit(100, 3600))
    resolve(client, report_post(client, create_post(seller)["id"], reporter), admin, action="DISMISS")
    few = count_queries(client, "/admin/actions", admin)
    for _ in range(4):
        resolve(client, report_post(client, create_post(seller)["id"], reporter), admin, action="DISMISS")

    # 관리자 확인 1 + 개수 1 + 목록·관리자·대상 JOIN 1
    assert count_queries(client, "/admin/actions", admin) == few == 3
