"""학교: 목록·시드, 관리자 추가·수정·비활성, 내 학교(7일 제한), 글의 학교 저장·해제, 목록 필터, 삭제·탈퇴 시 정리."""

from collections.abc import Callable
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import PostSchool, School, UserSchool
from app.services import school_service
from tests.conftest import TEST_PASSWORD


@pytest.fixture
def seller(make_auth_headers: Callable[..., dict[str, str]]) -> dict[str, str]:
    return make_auth_headers("seller@campus.ac.kr", "판매자")


@pytest.fixture
def buyer(make_auth_headers: Callable[..., dict[str, str]]) -> dict[str, str]:
    return make_auth_headers("buyer@campus.ac.kr", "구매자")


@pytest.fixture
def admin(make_admin_headers: Callable[..., dict[str, str]]) -> dict[str, str]:
    return make_admin_headers()


@pytest.fixture
def schools(db_session: Session) -> dict[str, int]:
    """기본 학교(시드) + 활성 학교 하나 + 비활성 학교 하나."""
    school_service.seed_default(db_session)
    other = School(name="부산대학교", sort_order=1)
    closed = School(name="닫힌대학교", is_active=False)
    db_session.add_all([other, closed])
    db_session.commit()
    default = db_session.scalar(select(School.id).where(School.name == school_service.DEFAULT_SCHOOL_NAME))
    return {"default": default, "other": other.id, "closed": closed.id}


def school_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(School)) or 0


# ---------- 목록·시드 ----------


def test_seed_adds_default_school_once(db_session: Session) -> None:
    school_service.seed_default(db_session)
    school_service.seed_default(db_session)
    names = db_session.scalars(select(School.name)).all()
    assert names == ["울산과학대학교"]


def test_public_list_shows_only_active_in_order(client: TestClient, schools: dict) -> None:
    response = client.get("/schools")
    assert response.status_code == 200
    assert response.json()["items"] == [
        {"id": schools["default"], "name": "울산과학대학교"},
        {"id": schools["other"], "name": "부산대학교"},
    ]


# ---------- 관리자 ----------


def test_admin_adds_renames_and_deactivates(client: TestClient, admin: dict, schools: dict, db_session: Session) -> None:
    created = client.post("/admin/schools", json={"name": "  서울대학교 ", "sort_order": 5}, headers=admin)
    assert created.status_code == 201
    assert created.json()["name"] == "서울대학교" and created.json()["is_active"] is True
    assert client.post("/admin/schools", json={"name": "서울대학교"}, headers=admin).status_code == 409

    school_id = created.json()["id"]
    renamed = client.patch(f"/admin/schools/{school_id}", json={"name": "서울과기대"}, headers=admin)
    assert renamed.status_code == 200 and renamed.json()["name"] == "서울과기대"
    assert client.patch(f"/admin/schools/{school_id}", json={"name": "부산대학교"}, headers=admin).status_code == 409
    assert client.patch(f"/admin/schools/{school_id}", json={"is_active": False}, headers=admin).json()["is_active"] is False
    assert client.patch("/admin/schools/999999", json={"name": "없음"}, headers=admin).status_code == 404

    # 관리자 목록에는 비활성도 보이고, 공개 목록에는 안 보인다.
    assert len(client.get("/admin/schools", headers=admin).json()["items"]) == 4
    assert all(s["name"] != "서울과기대" for s in client.get("/schools").json()["items"])


def test_admin_school_api_requires_admin(client: TestClient, seller: dict, schools: dict) -> None:
    assert client.post("/admin/schools", json={"name": "x"}).status_code == 401
    assert client.post("/admin/schools", json={"name": "x"}, headers=seller).status_code == 403
    assert client.patch(f"/admin/schools/{schools['other']}", json={"name": "x"}, headers=seller).status_code == 403


# ---------- 내 학교 ----------


def test_my_school_set_change_limit_and_clear(client: TestClient, seller: dict, schools: dict, db_session: Session) -> None:
    assert client.get("/users/me/school", headers=seller).json() == {"school": None, "changeable_at": None}

    # 처음 정할 때는 바로 정할 수 있다.
    first = client.put("/users/me/school", json={"school_id": schools["default"]}, headers=seller)
    assert first.status_code == 200
    assert first.json()["school"] == {"id": schools["default"], "name": "울산과학대학교"}
    assert first.json()["changeable_at"] is not None

    # 7일 안에 다시 바꾸면 기존 오류 형식(detail)으로 거절한다.
    again = client.put("/users/me/school", json={"school_id": schools["other"]}, headers=seller)
    assert again.status_code == 400
    assert again.json()["detail"].startswith("학교는 7일에 한 번만 바꿀 수 있습니다.")
    same = client.put("/users/me/school", json={"school_id": schools["default"]}, headers=seller)
    assert same.status_code == 400 and same.json()["detail"] == "지금 설정한 학교와 같습니다."

    # 7일이 지나면 비울 수 있다. 비운 뒤에도 다시 7일을 기다린다.
    row = db_session.scalar(select(UserSchool))
    row.changed_at = row.changed_at - timedelta(days=8)
    db_session.commit()
    cleared = client.put("/users/me/school", json={"school_id": None}, headers=seller)
    assert cleared.status_code == 200 and cleared.json()["school"] is None and cleared.json()["changeable_at"] is not None
    assert db_session.scalar(select(func.count()).select_from(UserSchool)) == 1


def test_my_school_rejects_missing_and_inactive(client: TestClient, seller: dict, schools: dict) -> None:
    assert client.put("/users/me/school", json={"school_id": 999999}, headers=seller).status_code == 404
    inactive = client.put("/users/me/school", json={"school_id": schools["closed"]}, headers=seller)
    assert inactive.status_code == 400 and inactive.json()["detail"] == "지금은 선택할 수 없는 학교입니다."
    # 실패한 요청은 7일 제한을 시작하지 않는다.
    assert client.put("/users/me/school", json={"school_id": schools["other"]}, headers=seller).status_code == 200
    # 필드를 빼면 422 (실수로 비우지 않게)
    assert client.put("/users/me/school", json={}, headers=seller).status_code == 422
    assert client.get("/users/me/school").status_code == 401


# ---------- 글의 학교 ----------


def test_post_create_and_update_school(client: TestClient, seller: dict, create_post, schools: dict) -> None:
    post = create_post(seller, school_id=schools["default"])
    assert post["school"] == {"id": schools["default"], "name": "울산과학대학교"}
    plain = create_post(seller)
    assert plain["school"] is None

    changed = client.patch(f"/posts/{post['id']}", json={"school_id": schools["other"]}, headers=seller)
    assert changed.status_code == 200 and changed.json()["school"]["id"] == schools["other"]
    # 보내지 않으면 그대로
    kept = client.patch(f"/posts/{post['id']}", json={"price": 1000}, headers=seller)
    assert kept.json()["school"]["id"] == schools["other"]
    # null이면 해제
    cleared = client.patch(f"/posts/{post['id']}", json={"school_id": None}, headers=seller)
    assert cleared.status_code == 200 and cleared.json()["school"] is None
    assert client.get(f"/posts/{post['id']}").json()["school"] is None


def test_post_rejects_missing_and_inactive_school(
    client: TestClient, seller: dict, post_payload: dict, create_post, schools: dict, db_session: Session
) -> None:
    assert client.post("/posts", json={**post_payload, "school_id": 999999}, headers=seller).status_code == 404
    inactive = client.post("/posts", json={**post_payload, "school_id": schools["closed"]}, headers=seller)
    assert inactive.status_code == 400 and inactive.json()["detail"] == "지금은 선택할 수 없는 학교입니다."
    post = create_post(seller)
    assert client.patch(f"/posts/{post['id']}", json={"school_id": schools["closed"]}, headers=seller).status_code == 400
    assert client.get(f"/posts/{post['id']}").json()["school"] is None

    # 글의 학교가 나중에 비활성이 돼도 그대로 두는 수정(같은 번호)은 막지 않는다.
    with_school = create_post(seller, school_id=schools["other"])
    db_session.execute(update(School).where(School.id == schools["other"]).values(is_active=False))
    db_session.commit()
    resent = client.patch(f"/posts/{with_school['id']}", json={"school_id": schools["other"], "price": 500}, headers=seller)
    assert resent.status_code == 200 and resent.json()["school"]["id"] == schools["other"]


def test_list_filter_by_school(client: TestClient, seller: dict, create_post, schools: dict) -> None:
    a = create_post(seller, title="A", school_id=schools["default"])
    b = create_post(seller, title="B", school_id=schools["other"])
    c = create_post(seller, title="C")  # 학교 없는 글

    every = client.get("/posts").json()
    assert {p["id"] for p in every["items"]} == {a["id"], b["id"], c["id"]}
    by_default = client.get("/posts", params={"school_id": schools["default"]}).json()
    assert [p["id"] for p in by_default["items"]] == [a["id"]] and by_default["total"] == 1
    assert by_default["items"][0]["school"] == {"id": schools["default"], "name": "울산과학대학교"}
    # 학교 없는 글은 전체에서만 보인다.
    assert c["id"] not in {p["id"] for p in client.get("/posts", params={"school_id": schools["other"]}).json()["items"]}
    assert client.get("/posts", params={"school_id": 0}).status_code == 422


def test_deleting_post_and_withdrawing_clean_up(
    client: TestClient, seller: dict, create_post, schools: dict, db_session: Session
) -> None:
    deleted = create_post(seller, school_id=schools["default"])
    create_post(seller, school_id=schools["other"])
    client.put("/users/me/school", json={"school_id": schools["default"]}, headers=seller)
    assert client.delete(f"/posts/{deleted['id']}", headers=seller).status_code == 204
    assert db_session.scalar(select(func.count()).select_from(PostSchool)) == 1

    assert client.post("/users/me/withdraw", json={"password": TEST_PASSWORD}, headers=seller).status_code == 204
    assert db_session.scalar(select(func.count()).select_from(PostSchool)) == 0
    assert db_session.scalar(select(func.count()).select_from(UserSchool)) == 0
    # 학교 자체는 남는다.
    assert school_count(db_session) == 3
