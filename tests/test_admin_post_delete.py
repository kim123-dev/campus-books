"""관리자 글 직접 삭제: 사유 필수, 작성자 삭제와 같은 정리 규칙, 미처리 신고 함께 처리, 관리 기록."""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import AdminAction, Conversation, Report, Wishlist
from tests.admin_helpers import last_log, log_count, report_post, user_id
from tests.test_post_images import make_image, upload


@pytest.fixture
def admin(make_admin_headers) -> dict:
    return make_admin_headers()


@pytest.fixture
def seller(make_auth_headers) -> dict:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def buyer(make_auth_headers) -> dict:
    return make_auth_headers("buyer@campus.ac.kr", "구매자")


def delete(client, headers, post_id, reason="거래 금지 물품"):
    return client.post(f"/admin/posts/{post_id}/delete", json={"reason": reason}, headers=headers)


def test_delete_cleans_up_like_owner_delete(
    client, db_session, admin, seller, buyer, create_post, image_dir: Path
) -> None:
    post = create_post(seller, title="문제 글", book_title="회로이론")
    assert upload(client, post["id"], seller, make_image()).status_code == 201
    client.post(f"/posts/{post['id']}/wishlist", headers=buyer)
    conversation = client.post(f"/posts/{post['id']}/conversations", headers=buyer).json()

    response = delete(client, admin, post["id"])

    assert response.status_code == 200, response.text
    assert response.json() == {"resolved_report_ids": []}
    assert client.get(f"/posts/{post['id']}").status_code == 404
    assert list(image_dir.iterdir()) == []
    db_session.expire_all()
    assert db_session.scalars(select(Wishlist)).all() == []
    kept = db_session.get(Conversation, conversation["id"])
    assert kept is not None and kept.post_id is None
    entry = last_log(db_session)
    assert (entry.action, entry.target_type, entry.target_id, entry.target_user_id, entry.reason) == (
        "DELETE_POST", "POST", post["id"], user_id(client, seller), "거래 금지 물품",
    )
    assert entry.detail == {"post_title": "문제 글", "book_title": "회로이론"}


def test_pending_reports_on_post_are_resolved_together(
    client, db_session, admin, seller, buyer, make_auth_headers, create_post
) -> None:
    post_id = create_post(seller)["id"]
    other_post = create_post(seller)["id"]
    first = report_post(client, post_id, buyer)
    second = report_post(client, post_id, make_auth_headers("third@campus.ac.kr", "제삼자"))
    unrelated = report_post(client, other_post, buyer)

    response = delete(client, admin, post_id)

    assert response.json() == {"resolved_report_ids": [first, second]}
    db_session.expire_all()
    for report_id in (first, second):
        report = db_session.get(Report, report_id)
        assert (report.status, report.action, report.resolution_note) == ("RESOLVED", "DELETE_POST", "거래 금지 물품")
    assert db_session.get(Report, unrelated).status == "PENDING"
    assert last_log(db_session).detail["resolved_ids"] == [first, second]


def test_delete_errors(client, db_session, admin, seller, create_post) -> None:
    post_id = create_post(seller)["id"]
    assert client.post(f"/admin/posts/{post_id}/delete", json={}, headers=admin).status_code == 422
    assert client.post(f"/admin/posts/{post_id}/delete", json={"reason": "  "}, headers=admin).status_code == 422
    assert delete(client, admin, 9999).status_code == 404
    assert delete(client, admin, post_id).status_code == 200

    again = delete(client, admin, post_id)

    assert again.status_code == 404
    assert list(db_session.scalars(select(AdminAction.action))) == ["DELETE_POST"]


def test_validation_does_not_touch_post(client, db_session, admin, seller, create_post) -> None:
    post_id = create_post(seller)["id"]
    client.post(f"/admin/posts/{post_id}/delete", json={"reason": "x" * 501}, headers=admin)

    assert client.get(f"/posts/{post_id}").status_code == 200
    assert log_count(db_session) == 0
