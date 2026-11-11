"""관리자 기능 테스트가 함께 쓰는 도구."""

from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.models import AdminAction, Review
from tests.conftest import test_engine


def user_id(client: TestClient, headers: dict) -> int:
    return client.get("/users/me", headers=headers).json()["id"]


def count_queries(client: TestClient, path: str, headers: dict, params: dict | None = None) -> int:
    """GET 요청 한 번에 나간 SQL 수. (관리자 확인 쿼리 1번 포함)"""
    statements: list[str] = []

    def count(*args) -> None:
        statements.append(args[2])

    event.listen(test_engine, "before_cursor_execute", count)
    try:
        response = client.get(path, params=params or {}, headers=headers)
        assert response.status_code == 200, response.text
    finally:
        event.remove(test_engine, "before_cursor_execute", count)
    return len(statements)


def log_count(db: Session) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(AdminAction)) or 0


def last_log(db: Session) -> AdminAction:
    db.expire_all()
    return db.scalars(select(AdminAction).order_by(AdminAction.id.desc())).first()


def report_post(client: TestClient, post_id: int, headers: dict, reason: str = "FRAUD") -> int:
    response = client.post(f"/posts/{post_id}/reports", json={"reason": reason}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def resolve(client: TestClient, report_id: int, headers: dict, **body):
    return client.post(f"/admin/reports/{report_id}/resolve", json=body, headers=headers)


def make_review(client: TestClient, seller: dict, buyer: dict, create_post, content: str = "후기") -> dict:
    """구매자가 판매자에게 남긴 후기."""
    post = create_post(seller, book_title="자료구조")
    conversation = client.post(f"/posts/{post['id']}/conversations", headers=buyer).json()
    client.post(f"/conversations/{conversation['id']}/messages", json={"content": "살게요"}, headers=buyer)
    client.patch(
        f"/posts/{post['id']}/status", json={"status": "SOLD", "buyer_id": user_id(client, buyer)}, headers=seller
    )
    trade_id = client.get(f"/conversations/{conversation['id']}", headers=buyer).json()["trade"]["trade_id"]
    response = client.post(f"/trades/{trade_id}/reviews", json={"rating": "BAD", "content": content}, headers=buyer)
    assert response.status_code == 201, response.text
    return response.json()


def hide_review_directly(db: Session, review_id: int) -> None:
    """신고 처리를 거치지 않고 후기를 숨겨 둔다. (숨긴 후기 목록 테스트용)"""
    from app.services import user_service

    db.get(Review, review_id).hidden_at = user_service.utc_now()
    db.commit()
