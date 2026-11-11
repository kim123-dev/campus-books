"""후기 숨김 해제: 사유 필수, 404·409, 받은 사람 화면과 매너 점수에 다시 들어감, 관리 기록."""

import pytest
from sqlalchemy import select

from app.models import AdminAction, Review
from tests.admin_helpers import hide_review_directly, last_log, log_count, make_review, user_id


@pytest.fixture
def setup(client, db_session, make_admin_headers, make_auth_headers, create_post) -> dict:
    admin = make_admin_headers()
    seller = make_auth_headers("seller@campus.ac.kr", "판매자")
    buyer = make_auth_headers("buyer@campus.ac.kr", "구매자")
    review = make_review(client, seller, buyer, create_post, content="별로였어요")
    hide_review_directly(db_session, review["id"])
    return {"admin": admin, "review_id": review["id"], "seller_id": user_id(client, seller), "buyer_id": user_id(client, buyer)}


def unhide(client, headers, review_id, reason="신고 내용과 달랐음"):
    return client.post(f"/admin/reviews/{review_id}/unhide", json={"reason": reason}, headers=headers)


def visible_reviews(client, seller_id) -> list[str]:
    return [r["content"] for r in client.get(f"/users/{seller_id}/reviews").json()["items"]]


def test_unhide_shows_review_again_and_logs(client, db_session, setup) -> None:
    assert visible_reviews(client, setup["seller_id"]) == []

    response = unhide(client, setup["admin"], setup["review_id"])

    assert response.status_code == 204, response.text
    assert visible_reviews(client, setup["seller_id"]) == ["별로였어요"]
    db_session.expire_all()
    assert db_session.get(Review, setup["review_id"]).hidden_at is None
    entry = last_log(db_session)
    assert (entry.action, entry.target_type, entry.target_id, entry.target_user_id, entry.reason) == (
        "UNHIDE_REVIEW", "REVIEW", setup["review_id"], setup["buyer_id"], "신고 내용과 달랐음",
    )
    assert entry.detail["book_title"] == "자료구조"


def test_unhide_errors(client, db_session, setup) -> None:
    admin = setup["admin"]
    assert client.post(f"/admin/reviews/{setup['review_id']}/unhide", json={"reason": " "}, headers=admin).status_code == 422
    assert unhide(client, admin, 9999).status_code == 404
    assert unhide(client, admin, setup["review_id"]).status_code == 204

    again = unhide(client, admin, setup["review_id"])

    assert again.status_code == 409
    assert again.json()["detail"] == "숨긴 후기가 아닙니다."
    assert list(db_session.scalars(select(AdminAction.action))) == ["UNHIDE_REVIEW"]


def test_not_hidden_review_is_conflict(client, db_session, make_admin_headers, make_auth_headers, create_post) -> None:
    admin = make_admin_headers()
    review = make_review(
        client, make_auth_headers("s@campus.ac.kr", "판매자"), make_auth_headers("b@campus.ac.kr", "구매자"), create_post
    )

    assert unhide(client, admin, review["id"]).status_code == 409
    assert log_count(db_session) == 0
