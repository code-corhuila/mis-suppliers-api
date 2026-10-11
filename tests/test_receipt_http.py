from dataclasses import asdict
from uuid import uuid4
from fastapi.testclient import TestClient
import pytest
from app.core import Failure
from app.main import create_app


@pytest.fixture
def payload():
    return {"supplierId": str(uuid4()), "medicationId": str(uuid4()), "reference": "REC-001", "lotNumber": "LOT-001",
            "expiresOn": "2099-01-01", "quantity": 10, "workflowId": str(uuid4()), "initiatedBy": str(uuid4())}


class Tokens:
    actor = str(uuid4())
    def authenticate(self, header):
        value = header.removeprefix("Bearer ") if header else ""
        if value == "workflow":
            return {"sub": self.actor, "roles": ["INVENTORY"], "service": "mis-workflow"}
        if value not in {"ADMIN", "INVENTORY", "SUPERVISOR", "CONSULTATION"}:
            raise Failure(401, "UNAUTHORIZED", "Autenticacion requerida.")
        return {"sub": self.actor, "roles": [value]}


class Suppliers:
    def health(self):
        pass


class Receipts:
    def __init__(self):
        self.resource = None
    def health(self):
        pass
    def prepare(self, actor, key, request, trace):
        self.resource = {"id": str(uuid4()), **asdict(request), "status": "PENDING", "createdBy": actor,
            "createdAt": "2026-10-11T12:00:00Z", "changedBy": None, "changedAt": None, "traceId": trace}
        return self.resource, True
    def find(self, receipt_id):
        if not self.resource or self.resource["id"] != receipt_id:
            raise Failure(404, "NOT_FOUND", "Recepcion inexistente.")
        return self.resource
    def transition(self, actor, key, receipt_id, action):
        resource = self.find(receipt_id)
        return {**resource, "status": "CONFIRMED" if action == "confirm" else "VOIDED"}


@pytest.fixture
def client():
    with TestClient(create_app(Suppliers(), Tokens(), Receipts())) as client:
        yield client


@pytest.mark.parametrize("role", ["ADMIN", "INVENTORY", "SUPERVISOR", "CONSULTATION"])
def test_humans_cannot_write_even_with_forged_headers(client, payload, role):
    headers = {"Authorization": "Bearer " + role, "X-Service": "mis-workflow", "X-User-Role": "INVENTORY", "Idempotency-Key": "receipt-001"}
    assert client.post("/api/v1/receipts", headers=headers, json=payload).status_code == 403
    assert client.post("/api/v1/receipts/" + str(uuid4()) + "/void", headers=headers).status_code == 403


def test_workflow_prepares_with_location_and_correlation(client, payload):
    response = client.post("/api/v1/receipts", json=payload, headers={"Authorization": "Bearer workflow", "Idempotency-Key": "receipt-001", "X-Correlation-Id": "receipt-trace"})
    assert response.status_code == 201
    assert response.headers["Location"] == "/api/v1/receipts/" + response.json()["id"]
    assert response.json()["traceId"] == response.headers["X-Correlation-Id"] == "receipt-trace"
    for role in ("ADMIN", "INVENTORY", "SUPERVISOR"):
        assert client.get(response.headers["Location"], headers={"Authorization": "Bearer " + role}).status_code == 200
    assert client.get(response.headers["Location"], headers={"Authorization": "Bearer CONSULTATION"}).status_code == 403
    confirmed = client.post(response.headers["Location"] + "/confirm", headers={"Authorization": "Bearer workflow", "Idempotency-Key": "confirm-001"}, json={})
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "CONFIRMED"


def test_missing_auth_invalid_body_and_unknown_id(client, payload):
    assert client.post("/api/v1/receipts", json=payload).status_code == 401
    headers = {"Authorization": "Bearer workflow", "Idempotency-Key": "receipt-001"}
    assert client.post("/api/v1/receipts", headers=headers, content="invalid").status_code == 400
    assert client.post("/api/v1/receipts", headers=headers, json={**payload, "unknown": 1}).status_code == 400
    assert client.get("/api/v1/receipts/bad", headers=headers).status_code == 400
    assert client.get("/api/v1/receipts/" + str(uuid4()), headers=headers).status_code == 404
    assert client.post("/api/v1/receipts/" + str(uuid4()) + "/confirm", headers=headers, json={"status": "CONFIRMED"}).status_code == 400


def test_unknown_transition_is404(client, payload):
    headers = {"Authorization": "Bearer workflow", "Idempotency-Key": "receipt-001"}
    prepared = client.post("/api/v1/receipts", headers=headers, json=payload)
    assert client.post(prepared.headers["Location"] + "/activate", headers=headers).status_code == 404


def test_missing_receipt_port_fails_closed():
    with TestClient(create_app(Suppliers(), Tokens())) as app:
        path = "/api/v1/receipts/" + str(uuid4())
        response = app.get(path, headers={"Authorization": "Bearer ADMIN"})
        assert response.status_code == 503 and response.json()["error"] == "SERVICE_UNAVAILABLE"
        assert response.json()["traceId"] == response.headers["X-Correlation-Id"]
