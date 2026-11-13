"""이메일 노출 범위. 이메일은 본인(/users/me, 가입 응답)과 관리자 사용자 관리에서만 응답에 담긴다."""

from app.main import app
from tests.admin_helpers import make_review, report_post, user_id

# 응답에 email 필드가 있어도 되는 API. 여기에 없는 API의 응답 형식에 email이 생기면 테스트가 실패한다.
ALLOWED = {
    ("GET", "/users/me"),
    ("PATCH", "/users/me"),  # 닉네임 변경 응답도 본인 정보(MeResponse)다.
    ("POST", "/auth/signup"),
    ("GET", "/admin/users"),
    ("GET", "/admin/users/{user_id}"),
}


def schema_has_email(schema: dict, components: dict, seen: set[str]) -> bool:
    """응답 형식(JSON 스키마) 어디든 email 속성이 있는지. $ref를 따라 내려간다."""
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        if name in seen:
            return False
        return schema_has_email(components[name], components, seen | {name})
    if "email" in schema.get("properties", {}):
        return True
    children = list(schema.get("properties", {}).values())
    for key in ("items", "additionalProperties"):
        if isinstance(schema.get(key), dict):
            children.append(schema[key])
    for key in ("anyOf", "allOf", "oneOf"):
        children += schema.get(key, [])
    return any(schema_has_email(child, components, seen) for child in children)


def routes_with_email() -> set[tuple[str, str]]:
    spec = app.openapi()
    components = spec.get("components", {}).get("schemas", {})
    found = set()
    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            for status, response in operation.get("responses", {}).items():
                if not status.startswith("2"):
                    continue
                for content in response.get("content", {}).values():
                    if schema_has_email(content.get("schema", {}), components, set()):
                        found.add((method.upper(), path))
    return found


def test_email_only_in_allowed_responses() -> None:
    assert routes_with_email() == ALLOWED


def test_other_users_email_never_in_public_responses(client, make_auth_headers, create_post) -> None:
    # 다른 사람이 볼 수 있는 화면의 API를 실제로 불러, 응답 어디에도 상대 이메일이 없는지 확인한다.
    seller = make_auth_headers("hidden-seller@campus.ac.kr", "판매자")
    buyer = make_auth_headers("hidden-buyer@campus.ac.kr", "구매자")
    review = make_review(client, seller, buyer, create_post)
    post_id = create_post(seller)["id"]
    report_post(client, post_id, buyer)
    conversation = client.post(f"/posts/{post_id}/conversations", headers=buyer).json()
    seller_id = user_id(client, seller)

    responses = [
        client.get("/posts", headers=buyer),
        client.get(f"/posts/{post_id}", headers=buyer),
        client.get(f"/users/{seller_id}/profile", headers=buyer),
        client.get(f"/users/{seller_id}/posts", headers=buyer),
        client.get(f"/users/{seller_id}/reviews", headers=buyer),
        client.get("/conversations", headers=buyer),
        client.get(f"/conversations/{conversation['id']}", headers=buyer),
        client.get("/conversations", headers=seller),
    ]
    assert review["id"]
    for response in responses:
        assert response.status_code == 200, (response.url, response.text)
        assert "hidden-seller@" not in response.text, response.url
        assert "hidden-buyer@" not in response.text, response.url


def test_admin_screens_other_than_user_management_have_no_email(
    client, make_admin_headers, make_auth_headers, create_post
) -> None:
    admin = make_admin_headers()
    seller = make_auth_headers("hidden-seller@campus.ac.kr", "판매자")
    buyer = make_auth_headers("hidden-buyer@campus.ac.kr", "구매자")
    make_review(client, seller, buyer, create_post)
    report_post(client, create_post(seller)["id"], buyer)

    for path in ("/admin/reports", "/admin/posts", "/admin/reviews", "/admin/actions", "/admin/dashboard"):
        assert "hidden-" not in client.get(path, headers=admin).text, path
    assert "hidden-seller@campus.ac.kr" in client.get("/admin/users", headers=admin).text
