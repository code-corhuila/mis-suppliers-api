import os
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4
import pytest
from pymongo import MongoClient
from pymongo.errors import WriteError
from app.core import Failure, NewSupplier
from app.mongo import MongoSuppliers


@pytest.fixture
def store():
    password = os.getenv("MONGO_TEST_PASSWORD")
    if not password:
        pytest.skip("Replica set desechable: ejecutar Test-Persistence.ps1")
    client = MongoClient("mongodb://mongo:27017/suppliers?authSource=suppliers&replicaSet=rs0",
        username="suppliers_app", password=password, tz_aware=True, serverSelectionTimeoutMS=2000, timeoutMS=5000)
    try:
        yield MongoSuppliers(client)
    finally:
        client.close()


def request():
    return NewSupplier("NATIVE-" + uuid4().hex.upper(), "Proveedor sintetico", None, None, None)


def test_native_create_replay_and_conflict(store):
    actor, key, body = str(uuid4()), "native-" + uuid4().hex, request()
    first, created = store.create(actor, key, body)
    assert created and store.db.suppliers.count_documents({"_id": first["id"]}) == 1
    store.db.suppliers.update_one({"_id": first["id"]}, {"$set": {"name": "Modificado solo en prueba"}})
    assert store.create(actor, key, body) == (first, False)
    other = NewSupplier(body.documentNumber, "Otra intencion", None, None, None)
    with pytest.raises(Failure) as error:
        store.create(actor, key, other)
    assert error.value.status == 409
    assert store.db.creation_requests.count_documents({"actor": actor, "requestKey": key}) == 1


def test_native_duplicate_document_does_not_consume_key(store):
    actor, body = str(uuid4()), request()
    store.create(actor, "native-" + uuid4().hex, body)
    key = "duplicate-" + uuid4().hex
    with pytest.raises(Failure) as error:
        store.create(actor, key, body)
    assert error.value.status == 422
    assert store.db.creation_requests.count_documents({"actor": actor, "requestKey": key}) == 0


def test_native_invalid_intention_rolls_back_supplier(store):
    body = request(); real = store.db
    intentions = Mock(wraps=real.creation_requests)
    intentions.insert_one.side_effect = lambda doc, **kwargs: real.creation_requests.insert_one({"_id": doc["_id"]}, **kwargs)
    store.db = SimpleNamespace(suppliers=real.suppliers, creation_requests=intentions)
    with pytest.raises(WriteError) as error:
        store.create(str(uuid4()), "atomic-" + uuid4().hex, body)
    assert error.value.code == 121
    assert real.suppliers.count_documents({"documentNumber": body.documentNumber}) == 0


def test_native_health_lookup_and_out_of_range_page(store):
    store.health()
    resource, _ = store.create(str(uuid4()), "read-" + uuid4().hex, request())
    assert store.find(resource["id"]) == resource
    page = store.list(1, 100)
    assert page["meta"]["total"] == store.db.suppliers.count_documents({})
    assert store.list(1000000, 100)["data"] == []
