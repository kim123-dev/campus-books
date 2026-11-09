"""관리자 신고 처리: 목록, 각 조치(기각·글 삭제·기간 정지)의 효과, 처리 기록, 중복 처리."""

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models import Conversation, Post, Report, User, Wishlist
from app.services import report_service, user_service
from tests.conftest import test_engine
from tests.test_post_images import make_image, upload


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
def post(seller: dict, create_post) -> dict:
    return create_post(seller, title="수상한 글", description="입금 먼저 해주세요")


def user_id(client: TestClient, headers: dict) -> int:
    return client.get("/users/me", headers=headers).json()["id"]


def report_post(client: TestClient, post_id: int, headers: dict, reason: str = "FRAUD") -> int:
    response = client.post(f"/posts/{post_id}/reports", json={"reason": reason}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def report_user(client: TestClient, target_id: int, headers: dict) -> int:
    response = client.post(f"/users/{target_id}/reports", json={"reason": "ABUSE"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def resolve(client: TestClient, report_id: int, headers: dict, **body):
    return client.post(f"/admin/reports/{report_id}/resolve", json=body, headers=headers)


def list_reports(client: TestClient, headers: dict, **params) -> dict:
    response = client.get("/admin/reports", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def saved(db: Session, report_id: int) -> Report:
    db.expire_all()
    return db.get(Report, report_id)


def user_by_email(db: Session, email: str) -> User:
    db.expire_all()
    return db.scalar(select(User).where(User.email == email))


# ---------- 목록 ----------


def test_list_item_fields(client, admin, seller, reporter, post) -> None:
    report_id = report_post(client, post["id"], reporter)
    report_post_body = client.post(
        f"/users/{user_id(client, seller)}/reports", json={"reason": "OTHER", "description": "욕설"}, headers=reporter
    )
    assert report_post_body.status_code == 201

    body = list_reports(client, admin)

    assert body["total"] == 2
    item = next(i for i in body["items"] if i["id"] == report_id)
    assert item["target_type"] == "POST" and item["target_id"] == post["id"]
    assert item["reason"] == "FRAUD"
    assert (item["post_title_snapshot"], item["post_content_snapshot"]) == ("수상한 글", "입금 먼저 해주세요")
    assert item["post_exists"] is True
    assert item["reporter"] == {"id": user_id(client, reporter), "nickname": "신고자"}
    assert item["reported_user"] == {"id": user_id(client, seller), "nickname": "판매자", "suspended_until": None}
    assert item["status"] == "PENDING" and item["resolution"] is None
    assert item["other_pending_count"] == 1  # 같은 판매자에 대한 사용자 신고 1건
    user_item = next(i for i in body["items"] if i["id"] != report_id)
    assert user_item["post_exists"] is None and user_item["description"] == "욕설"


def test_list_has_no_email(client, admin, reporter, post) -> None:
    report_post(client, post["id"], reporter)

    text = client.get("/admin/reports", headers=admin).text

    assert "@" not in text


def test_list_pending_first_then_newest(client, admin, make_auth_headers, seller, create_post) -> None:
    reporters = [make_auth_headers(f"r{i}@campus.ac.kr", f"신고자{i}") for i in range(3)]
    posts = [create_post(seller)["id"] for _ in range(3)]
    ids = [report_post(client, post_id, headers) for post_id, headers in zip(posts, reporters)]
    resolve(client, ids[2], admin, action="DISMISS")  # 가장 최근 신고를 처리

    order = [i["id"] for i in list_reports(client, admin)["items"]]

    assert order == [ids[1], ids[0], ids[2]]


def test_list_status_filter_and_pagination(client, admin, make_auth_headers, seller, create_post) -> None:
    reporter = make_auth_headers("r@campus.ac.kr", "신고자")
    ids = [report_post(client, create_post(seller)["id"], reporter) for _ in range(3)]
    resolve(client, ids[0], admin, action="DISMISS")

    pending = list_reports(client, admin, status="PENDING", size=1)
    resolved = list_reports(client, admin, status="RESOLVED")

    assert pending["total"] == 2 and [i["id"] for i in pending["items"]] == [ids[2]]
    assert list_reports(client, admin, status="PENDING", size=1, page=2)["items"][0]["id"] == ids[1]
    assert [i["id"] for i in resolved["items"]] == [ids[0]]


@pytest.mark.parametrize("params", [{"status": "DONE"}, {"page": 0}, {"size": 0}, {"size": 101}])
def test_list_invalid_params_return_422(client, admin, params) -> None:
    assert client.get("/admin/reports", params=params, headers=admin).status_code == 422


def test_list_query_count_does_not_grow(client, admin, make_auth_headers, seller, create_post, monkeypatch) -> None:
    # 신고를 여러 건 만들기 위해 신고 횟수 제한만 넉넉하게 바꾼다.
    monkeypatch.setattr(report_service, "REPORT_RATE_LIMIT", report_service.ReportRateLimit(100, 3600))

    def count_queries() -> int:
        statements: list[str] = []

        def count(*args) -> None:
            statements.append(args[2])

        event.listen(test_engine, "before_cursor_execute", count)
        try:
            assert client.get("/admin/reports", headers=admin).status_code == 200
        finally:
            event.remove(test_engine, "before_cursor_execute", count)
        return len(statements)

    reporter = make_auth_headers("r@campus.ac.kr", "신고자")
    report_post(client, create_post(seller)["id"], reporter)
    few = count_queries()
    for _ in range(4):
        report_post(client, create_post(seller)["id"], reporter)
    report_user(client, user_id(client, seller), reporter)

    # 신고가 늘어도 같다. (관리자 확인 1 + 개수 + 목록·사용자 JOIN + 남은 글 + 미처리 수)
    assert count_queries() == few == 5


# ---------- 기각 ----------


def test_dismiss_saves_record(client, db_session, admin, reporter, post) -> None:
    report_id = report_post(client, post["id"], reporter)

    response = resolve(client, report_id, admin, action="DISMISS", note="  증거 부족  ")

    assert response.status_code == 200
    assert response.json() == {"action": "DISMISS", "resolved_ids": [report_id], "suspended_until": None}
    record = saved(db_session, report_id)
    assert (record.status, record.action, record.resolution_note) == ("RESOLVED", "DISMISS", "증거 부족")
    assert record.resolved_by_id == user_id(client, admin)
    assert record.resolved_at is not None
    assert client.get(f"/posts/{post['id']}").status_code == 200  # 기각은 아무것도 바꾸지 않는다


def test_resolution_shown_in_list(client, admin, reporter, post) -> None:
    report_id = report_post(client, post["id"], reporter)
    resolve(client, report_id, admin, action="DISMISS", note="확인함")

    item = list_reports(client, admin)["items"][0]

    assert item["status"] == "RESOLVED"
    resolution = item["resolution"]
    assert (resolution["action"], resolution["note"]) == ("DISMISS", "확인함")
    assert resolution["resolved_by"] == {"id": user_id(client, admin), "nickname": "관리자"}
    assert resolution["resolved_with_report_id"] is None


def test_blank_note_is_saved_as_none(client, db_session, admin, reporter, post) -> None:
    report_id = report_post(client, post["id"], reporter)
    resolve(client, report_id, admin, action="DISMISS", note="   ")

    assert saved(db_session, report_id).resolution_note is None


# ---------- 글 삭제 ----------


def test_delete_post_removes_post_photos_and_wishlists(
    client, db_session, admin, seller, reporter, post, image_dir: Path
) -> None:
    assert upload(client, post["id"], seller, make_image()).status_code == 201
    client.post(f"/posts/{post['id']}/wishlist", headers=reporter)
    conversation = client.post(f"/posts/{post['id']}/conversations", headers=reporter).json()
    assert len(list(image_dir.iterdir())) == 2  # 사진 + 썸네일
    report_id = report_post(client, post["id"], reporter)

    response = resolve(client, report_id, admin, action="DELETE_POST")

    assert response.status_code == 200
    assert client.get(f"/posts/{post['id']}").status_code == 404
    assert list(image_dir.iterdir()) == []
    db_session.expire_all()
    assert db_session.scalars(select(Wishlist)).all() == []
    # 대화 기록은 분쟁 확인을 위해 남기고 글 연결만 끊는다. (작성자 삭제와 같은 규칙)
    kept = db_session.get(Conversation, conversation["id"])
    assert kept is not None and kept.post_id is None
    # 신고 사본은 남아 관리자가 무엇을 지웠는지 볼 수 있다.
    record = saved(db_session, report_id)
    assert (record.action, record.post_title_snapshot) == ("DELETE_POST", "수상한 글")
    assert list_reports(client, admin)["items"][0]["post_exists"] is False


def test_delete_post_resolves_other_reports_on_same_post(
    client, db_session, admin, make_auth_headers, seller, reporter, post, create_post
) -> None:
    other = make_auth_headers("other@campus.ac.kr", "다른사람")
    first = report_post(client, post["id"], reporter)
    second = report_post(client, post["id"], other)
    other_post_report = report_post(client, create_post(seller)["id"], reporter)  # 같은 판매자의 다른 글

    response = resolve(client, first, admin, action="DELETE_POST")

    assert response.json()["resolved_ids"] == [first, second]
    together = saved(db_session, second)
    assert (together.status, together.action, together.resolved_with_report_id) == ("RESOLVED", "DELETE_POST", first)
    assert saved(db_session, other_post_report).status == "PENDING"


def test_delete_post_for_user_report_returns_400(client, db_session, admin, seller, reporter) -> None:
    report_id = report_user(client, user_id(client, seller), reporter)

    response = resolve(client, report_id, admin, action="DELETE_POST")

    assert response.status_code == 400
    assert response.json()["detail"] == "사용자 신고에는 글 삭제를 할 수 없습니다."
    assert saved(db_session, report_id).status == "PENDING"


def test_delete_post_already_deleted_returns_400(client, db_session, admin, seller, reporter, post) -> None:
    report_id = report_post(client, post["id"], reporter)
    client.delete(f"/posts/{post['id']}", headers=seller)  # 판매자가 먼저 지움

    response = resolve(client, report_id, admin, action="DELETE_POST")

    assert response.status_code == 400
    assert response.json()["detail"] == "이미 삭제된 글입니다. 기각이나 정지로 처리해 주세요."
    assert saved(db_session, report_id).status == "PENDING"  # 실패하면 처리 기록도 남지 않는다
    assert resolve(client, report_id, admin, action="DISMISS").status_code == 200


# ---------- 기간 정지 ----------


def test_suspend_sets_end_and_blocks_writes(client, db_session, admin, seller, reporter, post) -> None:
    report_id = report_post(client, post["id"], reporter)
    before = user_service.utc_now()

    response = resolve(client, report_id, admin, action="SUSPEND", suspend_days=7)

    assert response.status_code == 200
    end = user_service.as_utc(user_by_email(db_session, "seller@campus.ac.kr").suspended_until)
    assert before + timedelta(days=7) <= end <= user_service.utc_now() + timedelta(days=7)
    assert response.json()["suspended_until"] is not None
    # 이미 받은 토큰으로도 쓰기 요청은 403이다.
    write = client.patch(f"/posts/{post['id']}", json={"price": 1000}, headers=seller)
    assert write.status_code == 403
    assert write.json()["detail"].endswith("까지 이용이 정지되었습니다.")
    assert list_reports(client, admin)["items"][0]["reported_user"]["suspended_until"] is not None


def test_suspend_keeps_longer_existing_suspension(client, db_session, admin, make_auth_headers, seller, post) -> None:
    first = report_post(client, post["id"], make_auth_headers("a@campus.ac.kr", "첫째"))
    second = report_post(client, post["id"], make_auth_headers("b@campus.ac.kr", "둘째"))
    resolve(client, first, admin, action="SUSPEND", suspend_days=30)
    long_end = user_by_email(db_session, "seller@campus.ac.kr").suspended_until

    resolve(client, second, admin, action="SUSPEND", suspend_days=1)

    # 나중 처리로 정지 기간이 줄어들지 않는다.
    assert user_by_email(db_session, "seller@campus.ac.kr").suspended_until == long_end


def test_suspend_admin_returns_400(client, db_session, make_admin_headers, admin, reporter, create_post) -> None:
    other_admin = make_admin_headers("admin2@campus.ac.kr", "관리자둘")
    report_id = report_post(client, create_post(other_admin)["id"], reporter)

    response = resolve(client, report_id, admin, action="SUSPEND", suspend_days=1)

    assert response.status_code == 400
    assert response.json()["detail"] == "관리자는 정지할 수 없습니다."


def test_include_same_user_resolves_only_that_users_pending_reports(
    client, db_session, admin, make_auth_headers, seller, reporter, post, create_post
) -> None:
    someone = make_auth_headers("someone@campus.ac.kr", "다른판매자")
    main = report_post(client, post["id"], reporter)
    user_report = report_user(client, user_id(client, seller), reporter)
    other_post = report_post(client, create_post(seller)["id"], make_auth_headers("c@campus.ac.kr", "셋째"))
    unrelated = report_post(client, create_post(someone)["id"], reporter)

    response = resolve(client, main, admin, action="SUSPEND", suspend_days=3, include_same_user=True, note="반복")

    assert response.json()["resolved_ids"] == [main, user_report, other_post]
    for report_id in (user_report, other_post):
        record = saved(db_session, report_id)
        assert (record.action, record.resolved_with_report_id, record.resolution_note) == ("SUSPEND", main, "반복")
    assert saved(db_session, unrelated).status == "PENDING"


def test_without_include_same_user_others_stay_pending(client, db_session, admin, seller, reporter, post) -> None:
    main = report_post(client, post["id"], reporter)
    user_report = report_user(client, user_id(client, seller), reporter)

    assert resolve(client, main, admin, action="DISMISS").json()["resolved_ids"] == [main]
    assert saved(db_session, user_report).status == "PENDING"


# ---------- 요청 검증·중복 ----------


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"action": "BAN"},
        {"action": "SUSPEND"},  # 기간 없음
        {"action": "SUSPEND", "suspend_days": 0},
        {"action": "SUSPEND", "suspend_days": 366},
        {"action": "DISMISS", "suspend_days": 3},  # 정지가 아닌데 기간
        {"action": "DELETE_POST", "include_same_user": True},
        {"action": "DISMISS", "note": "가" * 501},
        {"action": "DISMISS", "resolved_by_id": 1},  # 처리 기록은 서버가 채운다
    ],
)
def test_invalid_resolve_body_returns_422(client, db_session, admin, reporter, post, body) -> None:
    report_id = report_post(client, post["id"], reporter)

    assert client.post(f"/admin/reports/{report_id}/resolve", json=body, headers=admin).status_code == 422
    assert saved(db_session, report_id).status == "PENDING"


@pytest.mark.parametrize("days", [1, 365])
def test_suspend_days_boundary(client, admin, reporter, post, days) -> None:
    report_id = report_post(client, post["id"], reporter)

    assert resolve(client, report_id, admin, action="SUSPEND", suspend_days=days).status_code == 200


def test_missing_report_returns_404(client, admin) -> None:
    response = resolve(client, 9999, admin, action="DISMISS")

    assert response.status_code == 404
    assert response.json()["detail"] == "신고를 찾을 수 없습니다."


def test_resolving_twice_returns_409(client, db_session, make_admin_headers, admin, reporter, post) -> None:
    report_id = report_post(client, post["id"], reporter)
    resolve(client, report_id, admin, action="DISMISS", note="첫 처리")
    other_admin = make_admin_headers("admin2@campus.ac.kr", "관리자둘")

    response = resolve(client, report_id, other_admin, action="SUSPEND", suspend_days=7)

    assert response.status_code == 409
    assert response.json()["detail"] == "이미 처리된 신고입니다."
    record = saved(db_session, report_id)
    assert (record.action, record.resolution_note) == ("DISMISS", "첫 처리")  # 첫 처리 기록이 그대로
    assert user_by_email(db_session, "seller@campus.ac.kr").suspended_until is None


def test_report_resolved_together_cannot_be_resolved_again(client, admin, make_auth_headers, reporter, post) -> None:
    first = report_post(client, post["id"], reporter)
    second = report_post(client, post["id"], make_auth_headers("b@campus.ac.kr", "둘째"))
    resolve(client, first, admin, action="DISMISS", include_same_user=True)

    assert resolve(client, second, admin, action="DISMISS").status_code == 409


def test_post_row_is_really_gone(client, db_session, admin, reporter, post) -> None:
    report_id = report_post(client, post["id"], reporter)
    resolve(client, report_id, admin, action="DELETE_POST")

    db_session.expire_all()
    assert db_session.get(Post, post["id"]) is None
