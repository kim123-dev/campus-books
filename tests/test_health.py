from fastapi.testclient import TestClient


# 앱이 정상적으로 import/기동되는지 확인하는 가장 기본적인 스모크 테스트
def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
