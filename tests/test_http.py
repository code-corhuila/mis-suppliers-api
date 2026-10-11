from uuid import uuid4
from fastapi.testclient import TestClient
import pytest

from app.core import Failure
from app.main import create_app


class Tokens:
    def authenticate(self, header):
        role = header.removeprefix("Bearer ") if header else ""
        if role not in {"ADMIN", "INVENTORY", "SUPERVISOR", "CONSULTATION"}:
            raise Failure(401, "UNAUTHORIZED", "Autenticacion requerida.")
        return {"sub": str(uuid4()), "roles": [role]}


class Store:
    def health(self):
        pass
    def create(self, actor, key, request):
        return {"id": str(uuid4()), "documentNumber": request.documentNumber}, True
    def list(self, page, limit):
        return {"data": [], "meta": {"page": page, "limit": limit, "total": 0, "totalPages": 0}}
    def find(self, supplier_id):
        raise Failure(404, "NOT_FOUND", "Proveedor inexistente.")


@pytest.fixture
def client():
    with TestClient(create_app(Store(), Tokens())) as client:
        yield client


def test_public_health_and_protected_read(client):
    assert client.get("/health").status_code == 200
    denied = client.get("/api/v1/suppliers")
    assert denied.status_code == 401
    assert denied.json()["traceId"] == denied.headers["X-Correlation-Id"]


@pytest.mark.parametrize("role", ["INVENTORY", "SUPERVISOR", "CONSULTATION"])
def test_no_role_header_escalation(client, role):
    response = client.post("/api/v1/suppliers", headers={"Authorization": "Bearer " + role,
        "X-User-Role": "ADMIN", "Idempotency-Key": "test-key-001"},
        json={"documentNumber": "PRV-001", "name": "Proveedor sintetico"})
    assert response.status_code == 403


def test_admin_creation_and_location(client):
    response = client.post("/api/v1/suppliers", headers={"Authorization": "Bearer ADMIN",
        "Idempotency-Key": "test-key-001", "X-Correlation-Id": "trace-001"},
        json={"documentNumber": "prv-001", "name": "Proveedor sintetico"})
    assert response.status_code == 201
    assert response.headers["Location"].endswith(response.json()["id"])
    assert response.json()["documentNumber"] == "PRV-001"
    assert response.headers["X-Correlation-Id"] == "trace-001"


def test_invalid_json_and_unknown_fields(client):
    headers = {"Authorization": "Bearer ADMIN", "Idempotency-Key": "test-key-001", "Content-Type": "application/json"}
    for content in ("{invalid", '{"documentNumber":"PRV-001","name":"Nombre","active":false}'):
        response = client.post("/api/v1/suppliers", headers=headers, content=content)
        assert response.status_code == 400
        assert response.json()["traceId"] == response.headers["X-Correlation-Id"]


def test_bad_correlation_and_body_limit(client):
    assert client.get("/health", headers={"X-Correlation-Id": "bad/value"}).status_code == 400
    response = client.post("/api/v1/suppliers", content="x" * 65537)
    assert response.status_code == 413
    assert response.json()["traceId"] == response.headers["X-Correlation-Id"]


def test_streamed_body_limit_without_content_length(client):
    response = client.post("/api/v1/suppliers", content=iter([b"x" * 40000, b"x" * 40000]))
    assert response.status_code == 413


def test_invalid_page_and_missing_resource(client):
    headers = {"Authorization": "Bearer CONSULTATION"}
    assert client.get("/api/v1/suppliers?page=0", headers=headers).status_code == 400
    assert client.get("/api/v1/suppliers/" + str(uuid4()), headers=headers).status_code == 404
