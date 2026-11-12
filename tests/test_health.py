from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_response_model_in_openapi() -> None:
    document = create_app().openapi()
    assert "HealthResponse" in document["components"]["schemas"]
    ref = document["paths"]["/health"]["get"]["responses"]["200"]["content"]["application/json"]
    assert ref["schema"] == {"$ref": "#/components/schemas/HealthResponse"}
