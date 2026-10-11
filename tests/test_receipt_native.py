from dataclasses import replace
import os
from uuid import uuid4
from zoneinfo import ZoneInfo
import pytest
from pymongo import MongoClient
from pymongo.errors import WriteError
from app.core import Failure, NewSupplier
from app.mongo_receipts import MongoReceipts
from app.receipts import NewReceipt


@pytest.fixture
def context():
    password = os.getenv("MONGO_TEST_PASSWORD")
    if not password:
        pytest.skip("Replica set desechable: ejecutar Test-Persistence.ps1")
    client = MongoClient("mongodb://mongo:27017/suppliers?authSource=suppliers&replicaSet=rs0",
        username="suppliers_app", password=password, tz_aware=True, serverSelectionTimeoutMS=2000, timeoutMS=5000)
    try:
        store = MongoReceipts(client); actor = str(uuid4())
        supplier, _ = store.base.create(actor, "supplier-" + uuid4().hex,
            NewSupplier("RC-" + uuid4().hex.upper(), "Sintetico", None, None, None))
        request = NewReceipt(supplier["id"], str(uuid4()), "REC-" + uuid4().hex.upper(),
            "LOT-1", "2099-01-01", 10, str(uuid4()), str(uuid4()))
        yield store, actor, request
    finally:
        client.close()


def test_native_lifecycle_preserves_original_snapshots_and_audit(context):
    store, actor, request = context; store.health()
    pending, created = store.prepare(actor, "prepare-001", request, "native-trace")
    assert created and pending["status"] == "PENDING" and pending["changedAt"] is None
    confirmed = store.transition(actor, "confirm-001", pending["id"], "confirm")
    assert confirmed["status"] == "CONFIRMED" and confirmed["changedBy"] == actor
    assert confirmed["changedAt"] and confirmed["traceId"] == "native-trace"
    assert store.prepare(actor, "prepare-001", request, "other-trace") == (pending, False)
    voided = store.transition(actor, "void-001", pending["id"], "void")
    assert voided["status"] == "VOIDED"
    assert store.transition(actor, "confirm-001", pending["id"], "confirm") == confirmed
    assert store.transition(actor, "void-002", pending["id"], "void") == voided
    assert store.find(pending["id"]) == voided
    with pytest.raises(Failure) as error:
        store.transition(actor, "confirm-002", pending["id"], "confirm")
    assert error.value.status == 422


def test_native_prepare_key_conflict_does_not_duplicate_document(context):
    store, actor, request = context
    store.prepare(actor, "prepare-001", request, "trace")
    with pytest.raises(Failure) as error:
        store.prepare(actor, "prepare-001", replace(request, quantity=11), "trace")
    assert error.value.status == 409
    assert store.db.receipts.count_documents({"workflowId": request.workflowId}) == 1


@pytest.mark.parametrize("constraint", ["reference", "workflow"])
def test_native_unique_reference_and_saga_do_not_consume_new_key(context, constraint):
    store, actor, request = context
    store.prepare(actor, "prepare-001", request, "trace")
    other = replace(request, workflowId=str(uuid4())) if constraint == "reference" else replace(request, reference="ALT-" + uuid4().hex.upper())
    with pytest.raises(Failure) as error:
        store.prepare(actor, "prepare-002", other, "trace")
    assert error.value.status == 422
    assert store.db.receipt_requests.count_documents({"actor": actor, "requestKey": "prepare-002"}) == 0


@pytest.mark.parametrize("fault", ["expired", "inactive"])
def test_native_rejections_leave_no_receipt_or_intention(context, fault):
    store, actor, request = context
    if fault == "expired":
        request = replace(request, expiresOn=store.now().astimezone(ZoneInfo("America/Bogota")).date().isoformat())
    else:
        store.db.suppliers.update_one({"_id": request.supplierId}, {"$set": {"active": False}})
    with pytest.raises(Failure) as error:
        store.prepare(actor, "prepare-001", request, "trace")
    assert error.value.status == 422
    assert store.db.receipts.count_documents({"workflowId": request.workflowId}) == 0
    assert store.db.receipt_requests.count_documents({"actor": actor}) == 0


def invalid_intention(store):
    store.remember = lambda scope, fingerprint, resource, session: store.db.receipt_requests.insert_one({"_id": str(uuid4())}, session=session)


def test_native_invalid_intention_rolls_back_preparation(context):
    store, actor, request = context; invalid_intention(store)
    with pytest.raises(WriteError) as error:
        store.prepare(actor, "prepare-001", request, "trace")
    assert error.value.code == 121
    assert store.db.receipts.count_documents({"workflowId": request.workflowId}) == 0


def test_native_invalid_intention_rolls_back_transition_and_audit(context):
    store, actor, request = context
    pending, _ = store.prepare(actor, "prepare-001", request, "trace")
    invalid_intention(store)
    with pytest.raises(WriteError) as error:
        store.transition(actor, "confirm-001", pending["id"], "confirm")
    assert error.value.code == 121
    assert store.find(pending["id"]) == pending
    assert store.db.receipt_requests.count_documents({"actor": actor, "operation": "confirmReceipt"}) == 0
