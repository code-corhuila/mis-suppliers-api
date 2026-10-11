from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock
import pytest
from pymongo.errors import DuplicateKeyError
from pymongo import ReadPreference
from app.core import Failure, NewSupplier
from app.mongo import MongoSuppliers


def request():
    return NewSupplier("PRV-001", "Proveedor", None, None, None)


def test_resource_hides_audit_and_returns_utc():
    doc = {"_id": "synthetic", "createdBy": "private-actor", "createdAt": datetime(2026, 1, 1, tzinfo=timezone.utc),
           "documentNumber": "PRV-001", "name": "Proveedor", "phone": None, "email": None, "address": None, "active": True}
    result = MongoSuppliers.resource(doc)
    assert result["id"] == "synthetic" and result["createdAt"] == "2026-01-01T00:00:00.000Z"
    assert "_id" not in result and "createdBy" not in result


def test_replay_returns_stored_snapshot():
    snapshot = {"id": "original", "name": "Nombre original"}
    assert MongoSuppliers.replay({"requestHash": "hash", "response": snapshot}, "hash") == (snapshot, False)


def test_replay_rejects_different_fingerprint():
    with pytest.raises(Failure) as error:
        MongoSuppliers.replay({"requestHash": "first", "response": {}}, "other")
    assert error.value.status == 409


def test_transaction_uses_snapshot_majority_and_primary():
    client = MagicMock(); session = client.start_session.return_value.__enter__.return_value
    callback = Mock(); session.with_transaction.return_value = ("result", True)
    assert MongoSuppliers(client).transaction(callback) == ("result", True)
    args, options = session.with_transaction.call_args
    assert args == (callback,) and options["read_concern"].document == {"level": "snapshot"}
    assert options["write_concern"].document == {"w": "majority", "wtimeout": 5000}
    assert options["read_preference"] == ReadPreference.PRIMARY and options["max_commit_time_ms"] == 5000


def test_duplicate_intention_recovers_committed_snapshot():
    store = MongoSuppliers(MagicMock()); store.transaction = Mock(side_effect=DuplicateKeyError("collision"))
    snapshot = {"id": "committed"}
    store.db.creation_requests.find_one.return_value = {"requestHash": request().fingerprint(), "response": snapshot}
    assert store.create("actor", "key-12345", request()) == (snapshot, False)
    store.db.suppliers.find_one.assert_not_called()


def test_duplicate_document_without_intention_is_business_rejection():
    store = MongoSuppliers(MagicMock()); store.transaction = Mock(side_effect=DuplicateKeyError("collision"))
    store.db.creation_requests.find_one.return_value = None
    store.db.suppliers.find_one.return_value = {"documentNumber": "PRV-001"}
    with pytest.raises(Failure) as error:
        store.create("actor", "key-12345", request())
    assert error.value.status == 422 and error.value.field == "documentNumber"


def test_missing_supplier_returns404():
    store = MongoSuppliers(MagicMock()); store.db.suppliers.find_one.return_value = None
    with pytest.raises(Failure) as error:
        store.find("missing")
    assert error.value.status == 404
