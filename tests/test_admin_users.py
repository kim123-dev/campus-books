"""관리자 사용자 관리·글·후기 목록: 필터·검색·상세 개수·정지 이력·쿼리 수."""

from datetime import timedelta

from sqlalchemy import select

from app.models import User
from app.services import user_service
from tests.admin_helpers import (
    count_queries,
    hide_review_directly,
    make_review,
    report_post,
    resolve,
    user_id,
)


def get_users(client, headers, **params) -> dict:
    response = client.get("/admin/users", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def nicknames(body: dict) -> list[str]:
    return [item["nickname"] for item in body["items"]]


def suspend_directly(db, email: str, days: int = 3) -> None:
    db.scalar(select(User).where(User.email == email)).suspended_until = (
        user_service.utc_now() + timedelta(days=days)
    ).replace(tzinfo=None)
    db.commit()


def withdraw(client, headers) -> None:
    response = client.post("/users/me/withdraw", json={"password": "password123"}, headers=headers)
    assert response.status_code == 204, response.text


# ---------- 사용자 목록 ----------


def test_list_shows_email_and_counts_newest_first(client, make_admin_headers, make_auth_headers, create_post) -> None:
    admin = make_admin_headers()
    seller = make_auth_headers("seller@campus.ac.kr", "판매자")
    buyer = make_auth_headers("buyer@campus.ac.kr", "구매자")
    post_id = create_post(seller)["id"]
    create_post(seller)
    report_post(client, post_id, buyer)

    body = get_users(client, admin)

    assert body["total"] == 3
    assert nicknames(body) == ["구매자", "판매자", "관리자"]
    seller_item = body["items"][1]
    assert seller_item["email"] == "seller@campus.ac.kr"
    assert seller_item["post_count"] == 2
    assert seller_item["pending_report_count"] == 1
    assert seller_item["role"] == "USER"
    assert seller_item["withdrawn"] is False
    assert seller_item["suspended_until"] is None


def test_status_filters(client, db_session, make_admin_headers, make_auth_headers) -> None:
    admin = make_admin_headers()
    make_auth_headers("bad@campus.ac.kr", "정지된사람")
    make_auth_headers("old@campus.ac.kr", "정지끝난사람")
    leaver = make_auth_headers("leaver@campus.ac.kr", "탈퇴자")
    suspend_directly(db_session, "bad@campus.ac.kr")
    suspend_directly(db_session, "old@campus.ac.kr", days=-1)
    withdraw(client, leaver)

    assert nicknames(get_users(client, admin)) == ["정지끝난사람", "정지된사람", "관리자"]
    suspended = get_users(client, admin, status="SUSPENDED")
    assert nicknames(suspended) == ["정지된사람"]
    assert suspended["items"][0]["suspended_until"] is not None
    assert nicknames(get_users(client, admin, status="ADMIN")) == ["관리자"]
    withdrawn = get_users(client, admin, status="WITHDRAWN")["items"]
    # 탈퇴한 계정은 이메일을 내보내지 않고 이름은 "탈퇴한 사용자"다.
    assert [(u["nickname"], u["email"], u["withdrawn"]) for u in withdrawn] == [("탈퇴한 사용자", None, True)]


def test_search_by_nickname_email_or_number(client, make_admin_headers, make_auth_headers) -> None:
    admin = make_admin_headers()
    make_auth_headers("kim@campus.ac.kr", "김철수")
    lee_id = user_id(client, make_auth_headers("lee@other.ac.kr", "이영희"))

    assert nicknames(get_users(client, admin, q="철수")) == ["김철수"]
    assert nicknames(get_users(client, admin, q="OTHER.ac")) == ["이영희"]  # 대소문자 무시
    assert nicknames(get_users(client, admin, q=f"#{lee_id}")) == ["이영희"]
    assert get_users(client, admin, q="%")["total"] == 0  # %는 와일드카드가 아니다
    assert nicknames(get_users(client, admin, q="campus", status="ADMIN")) == ["관리자"]


def test_withdrawn_user_found_only_by_number(client, make_admin_headers, make_auth_headers) -> None:
    admin = make_admin_headers()
    leaver = make_auth_headers("leaver@campus.ac.kr", "탈퇴자")
    leaver_id = user_id(client, leaver)
    withdraw(client, leaver)

    assert get_users(client, admin, status="WITHDRAWN", q="withdrawn")["total"] == 0
    assert get_users(client, admin, status="WITHDRAWN", q=str(leaver_id))["total"] == 1


def test_user_list_query_count_is_fixed(client, make_admin_headers, make_auth_headers, create_post) -> None:
    admin = make_admin_headers()
    few = count_queries(client, "/admin/users", admin)
    for i in range(3):
        create_post(make_auth_headers(f"u{i}@campus.ac.kr", f"사용자{i}"))

    # 관리자 확인 1 + 개수 1 + 목록(글 수·미처리 신고 수 포함) 1
    assert count_queries(client, "/admin/users", admin) == few == 3


def test_user_list_validation(client, make_admin_headers) -> None:
    admin = make_admin_headers()
    assert client.get("/admin/users", params={"status": "HACK"}, headers=admin).status_code == 422
    assert client.get("/admin/users", params={"q": "x" * 101}, headers=admin).status_code == 422


# ---------- 사용자 상세 ----------


def test_user_detail_counts_and_suspension_history(
    client, db_session, make_admin_headers, make_auth_headers, create_post
) -> None:
    admin = make_admin_headers()
    seller = make_auth_headers("seller@campus.ac.kr", "판매자")
    buyer = make_auth_headers("buyer@campus.ac.kr", "구매자")
    seller_id = user_id(client, seller)
    review = make_review(client, seller, buyer, create_post)
    hide_review_directly(db_session, review["id"])
    report_id = report_post(client, create_post(seller)["id"], buyer)
    report_post(client, create_post(seller)["id"], buyer)
    assert resolve(client, report_id, admin, action="SUSPEND", suspend_days=3, note="사기 의심").status_code == 200

    response = client.get(f"/admin/users/{seller_id}", headers=admin)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == "seller@campus.ac.kr"
    assert body["counts"] == {
        "posts": 3,
        "reports_received": 2,
        "reports_pending": 1,  # 다른 글에 대한 신고는 따로 처리한다
        "reviews_received": 1,
        "reviews_hidden": 1,
        "reviews_written": 0,
    }
    assert body["suspended_until"] is not None
    assert [(s["action"], s["reason"]) for s in body["suspensions"]] == [("SUSPEND", "사기 의심")]


def test_user_detail_query_count(client, make_admin_headers, auth_headers) -> None:
    admin = make_admin_headers()
    # 관리자 확인 1 + 사용자 1 + 개수들 1 + 정지 이력 1
    assert count_queries(client, f"/admin/users/{user_id(client, auth_headers)}", admin) == 4


def test_user_detail_withdrawn_and_missing(client, make_admin_headers, make_auth_headers) -> None:
    admin = make_admin_headers()
    leaver = make_auth_headers("leaver@campus.ac.kr", "탈퇴자")
    leaver_id = user_id(client, leaver)
    withdraw(client, leaver)

    body = client.get(f"/admin/users/{leaver_id}", headers=admin).json()
    assert (body["nickname"], body["email"], body["withdrawn"]) == ("탈퇴한 사용자", None, True)
    assert client.get("/admin/users/9999", headers=admin).status_code == 404


def test_reports_filter_by_reported_user(client, make_admin_headers, make_auth_headers, create_post) -> None:
    admin = make_admin_headers()
    a = make_auth_headers("a@campus.ac.kr", "가가")
    b = make_auth_headers("b@campus.ac.kr", "나나")
    report_post(client, create_post(a)["id"], b)
    report_post(client, create_post(b)["id"], a)

    body = client.get("/admin/reports", params={"reported_user_id": user_id(client, a)}, headers=admin).json()

    assert body["total"] == 1
    assert body["items"][0]["reported_user"]["nickname"] == "가가"


# ---------- 글·후기 목록 ----------


def test_post_list_filters_and_pending_count(client, make_admin_headers, make_auth_headers, create_post) -> None:
    admin = make_admin_headers()
    seller = make_auth_headers("seller@campus.ac.kr", "판매자")
    other = make_auth_headers("other@campus.ac.kr", "다른사람")
    reported = create_post(seller, title="수상한 글", book_title="회로이론")["id"]
    sold = create_post(seller, title="팔린 글")["id"]
    create_post(other, title="다른 글")
    report_post(client, reported, other)
    client.patch(f"/posts/{sold}/status", json={"status": "SOLD"}, headers=seller)

    def titles(**params) -> list[str]:
        body = client.get("/admin/posts", params=params, headers=admin).json()
        return [item["title"] for item in body["items"]]

    assert titles() == ["다른 글", "팔린 글", "수상한 글"]
    assert titles(q="회로") == ["수상한 글"]
    assert titles(status="SOLD") == ["팔린 글"]
    assert titles(seller_id=user_id(client, other)) == ["다른 글"]
    first = client.get("/admin/posts", params={"q": "수상"}, headers=admin).json()["items"][0]
    assert first["pending_report_count"] == 1
    assert first["seller"] == {"id": user_id(client, seller), "nickname": "판매자", "withdrawn": False}


def test_post_list_query_count_is_fixed(client, make_admin_headers, auth_headers, create_post) -> None:
    admin = make_admin_headers()
    create_post(auth_headers)
    few = count_queries(client, "/admin/posts", admin)
    for _ in range(3):
        create_post(auth_headers)

    assert count_queries(client, "/admin/posts", admin) == few == 3


def test_review_list_includes_hidden(client, db_session, make_admin_headers, make_auth_headers, create_post) -> None:
    admin = make_admin_headers()
    seller = make_auth_headers("seller@campus.ac.kr", "판매자")
    buyer = make_auth_headers("buyer@campus.ac.kr", "구매자")
    review = make_review(client, seller, buyer, create_post, content="별로였어요")
    hide_review_directly(db_session, review["id"])

    body = client.get("/admin/reviews", params={"hidden": "true"}, headers=admin).json()
    assert body["total"] == 1
    item = body["items"][0]
    assert (item["content"], item["book_title"]) == ("별로였어요", "자료구조")
    assert (item["reviewer"]["nickname"], item["reviewee"]["nickname"]) == ("구매자", "판매자")
    assert item["hidden_at"] is not None
    assert client.get("/admin/reviews", params={"hidden": "false"}, headers=admin).json()["total"] == 0
    seller_id = item["reviewee"]["id"]
    assert client.get("/admin/reviews", params={"reviewee_id": seller_id}, headers=admin).json()["total"] == 1
    assert client.get("/admin/reviews", params={"reviewer_id": seller_id}, headers=admin).json()["total"] == 0


def test_review_list_query_count_is_fixed(client, make_admin_headers, make_auth_headers, create_post) -> None:
    admin = make_admin_headers()
    seller = make_auth_headers("seller@campus.ac.kr", "판매자")
    buyer = make_auth_headers("buyer@campus.ac.kr", "구매자")
    make_review(client, seller, buyer, create_post)
    few = count_queries(client, "/admin/reviews", admin)
    make_review(client, seller, buyer, create_post)
    make_review(client, seller, buyer, create_post)

    assert count_queries(client, "/admin/reviews", admin) == few == 3
