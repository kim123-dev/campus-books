"""거래 후기 신고와 관리자 처리(후기 숨김·작성자 정지)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Report, Review, User
from app.services import user_service


@pytest.fixture
def admin(make_admin_headers) -> dict:
    return make_admin_headers()


@pytest.fixture
def seller(make_auth_headers) -> dict:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def buyer(make_auth_headers) -> dict:
    return make_auth_headers("buyer@campus.ac.kr", "구매자")


@pytest.fixture
def stranger(make_auth_headers) -> dict:
    return make_auth_headers("stranger@campus.ac.kr", "제삼자")


def user_id(client: TestClient, headers: dict) -> int:
    return client.get("/users/me", headers=headers).json()["id"]


@pytest.fixture
def review(client: TestClient, seller: dict, buyer: dict, create_post) -> dict:
    """구매자가 판매자에게 남긴 후기."""
    post = create_post(seller, book_title="자료구조")
    conversation = client.post(f"/posts/{post['id']}/conversations", headers=buyer).json()
    client.post(f"/conversations/{conversation['id']}/messages", json={"content": "살게요"}, headers=buyer)
    client.patch(
        f"/posts/{post['id']}/status", json={"status": "SOLD", "buyer_id": user_id(client, buyer)}, headers=seller
    )
    trade_id = client.get(f"/conversations/{conversation['id']}", headers=buyer).json()["trade"]["trade_id"]
    response = client.post(
        f"/trades/{trade_id}/reviews", json={"rating": "BAD", "content": "욕설이 담긴 후기"}, headers=buyer
    )
    assert response.status_code == 201, response.text
    return response.json()


def report(client: TestClient, review_id: int, headers: dict, reason: str = "ABUSE"):
    return client.post(f"/reviews/{review_id}/reports", json={"reason": reason}, headers=headers)


def resolve(client: TestClient, report_id: int, headers: dict, **body):
    # 기각 외의 조치는 사유가 필수라, 따로 정하지 않으면 테스트용 사유를 넣는다.
    if body.get("action") not in (None, "DISMISS"):
        body.setdefault("note", "테스트 사유")
    return client.post(f"/admin/reports/{report_id}/resolve", json=body, headers=headers)


def admin_items(client: TestClient, headers: dict) -> list[dict]:
    return client.get("/admin/reports", headers=headers).json()["items"]


# ---------- 신고 ----------


def test_reviewee_and_others_can_report(
    client: TestClient, db_session: Session, seller: dict, buyer: dict, stranger: dict, review: dict
) -> None:
    assert report(client, review["id"], seller).status_code == 201
    assert report(client, review["id"], stranger).status_code == 201

    saved = db_session.scalars(select(Report)).all()
    # 피신고자는 후기를 쓴 사람(구매자)이다.
    assert {(r.target_type, r.target_id, r.reported_user_id) for r in saved} == {
        ("REVIEW", review["id"], user_id(client, buyer))
    }


def test_report_rules(
    client: TestClient, db_session: Session, seller: dict, buyer: dict, stranger: dict, review: dict
) -> None:
    own = report(client, review["id"], buyer)
    assert own.status_code == 400
    assert own.json() == {"detail": "내가 쓴 후기는 신고할 수 없습니다."}
    assert report(client, 999, seller).status_code == 404
    assert report(client, review["id"], {}).status_code == 401
    report(client, review["id"], seller)
    assert report(client, review["id"], seller).status_code == 409
    # 정지 중에는 신고할 수 없다.
    user_service.suspend(db_session.get(User, user_id(client, stranger)), 3)
    db_session.commit()
    assert report(client, review["id"], stranger).status_code == 403


def test_withdrawn_reviewer_has_no_reported_user(
    client: TestClient, db_session: Session, seller: dict, buyer: dict, review: dict
) -> None:
    client.post("/users/me/withdraw", json={"password": "password123"}, headers=buyer)

    assert report(client, review["id"], seller).status_code == 201
    assert db_session.scalar(select(Report.reported_user_id)) is None


# ---------- 관리자 목록 ----------


def test_admin_list_shows_review(client: TestClient, admin: dict, seller: dict, review: dict) -> None:
    report(client, review["id"], seller)

    item = admin_items(client, admin)[0]

    assert item["target_type"] == "REVIEW"
    assert item["review"] == {
        "rating": "BAD",
        "content": "욕설이 담긴 후기",
        "book_title": "자료구조",
        "reviewee": {"id": user_id(client, seller), "nickname": "판매자"},
        "hidden": False,
    }
    assert item["reported_user"]["nickname"] == "구매자"
    assert item["post_exists"] is None


# ---------- 처리 ----------


def test_hide_review_hides_and_resolves_same_review_reports(
    client: TestClient, db_session: Session, admin: dict, seller: dict, stranger: dict, review: dict
) -> None:
    first = report(client, review["id"], seller).json()["id"]
    second = report(client, review["id"], stranger).json()["id"]

    response = resolve(client, first, admin, action="HIDE_REVIEW")

    assert response.status_code == 200, response.text
    assert response.json()["resolved_ids"] == [first, second]
    db_session.expire_all()
    assert db_session.get(Review, review["id"]).hidden_at is not None
    # 숨긴 후기는 프로필 목록·매너 학점에서 빠지고, 더 신고할 수 없다.
    seller_id = user_id(client, seller)
    assert client.get(f"/users/{seller_id}/reviews").json()["total"] == 0
    assert client.get(f"/users/{seller_id}/profile").json()["manner"]["total"] == 0
    assert report(client, review["id"], admin).status_code == 404
    assert {item["review"]["hidden"] for item in admin_items(client, admin)} == {True}


def test_suspend_reviewer(
    client: TestClient, db_session: Session, admin: dict, seller: dict, buyer: dict, review: dict
) -> None:
    report_id = report(client, review["id"], seller).json()["id"]

    response = resolve(client, report_id, admin, action="SUSPEND", suspend_days=3)

    assert response.status_code == 200, response.text
    db_session.expire_all()
    assert user_service.active_suspension_end(db_session.get(User, user_id(client, buyer))) is not None
    # 정지만 했으면 후기는 그대로 보인다.
    assert db_session.get(Review, review["id"]).hidden_at is None


def test_action_must_match_target(
    client: TestClient, admin: dict, seller: dict, buyer: dict, create_post, review: dict
) -> None:
    review_report = report(client, review["id"], seller).json()["id"]
    post = create_post(seller, title="다른 글")
    post_report = client.post(f"/posts/{post['id']}/reports", json={"reason": "SPAM"}, headers=buyer).json()["id"]

    delete_on_review = resolve(client, review_report, admin, action="DELETE_POST")
    assert delete_on_review.status_code == 400
    assert delete_on_review.json() == {"detail": "후기 신고에는 글 삭제를 할 수 없습니다."}
    hide_on_post = resolve(client, post_report, admin, action="HIDE_REVIEW")
    assert hide_on_post.status_code == 400
    assert hide_on_post.json() == {"detail": "후기 숨김은 후기 신고에만 쓸 수 있습니다."}
    # 후기 숨김은 그 후기 하나에 대한 조치라 "같은 사용자 함께 처리"를 쓸 수 없다.
    assert resolve(client, review_report, admin, action="HIDE_REVIEW", include_same_user=True).status_code == 422


# ---------- 프로필의 is_mine ----------


def test_is_mine_on_profile_reviews(client: TestClient, seller: dict, buyer: dict, review: dict) -> None:
    path = f"/users/{user_id(client, seller)}/reviews"

    assert client.get(path).json()["items"][0]["is_mine"] is None
    assert client.get(path, headers=buyer).json()["items"][0]["is_mine"] is True
    assert client.get(path, headers=seller).json()["items"][0]["is_mine"] is False
