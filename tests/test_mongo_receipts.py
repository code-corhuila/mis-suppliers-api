from unittest.mock import MagicMock
import pytest
from app.core import Failure
from app.mongo_receipts import MongoReceipts


@pytest.mark.parametrize("names", [[], ["receipts"]])
def test_health_rejects_missing_collections(names):
    store = MongoReceipts(MagicMock()); store.db.list_collection_names.return_value = names
    with pytest.raises(Failure) as error:
        store.health()
    assert error.value.status == 503


@pytest.mark.parametrize("name", ["uq_reference", "uq_workflow", "uq_receipt_intention"])
def test_health_rejects_missing_unique_index(name):
    store = MongoReceipts(MagicMock())
    store.db.list_collection_names.return_value = ["receipts", "receipt_requests"]
    indexes = {key: {"unique": True} for key in ("uq_reference", "uq_workflow", "uq_receipt_intention")}
    indexes[name] = {"unique": False}
    store.db.receipts.index_information.return_value = indexes
    store.db.receipt_requests.index_information.return_value = indexes
    with pytest.raises(Failure) as error:
        store.health()
    assert error.value.status == 503


def test_missing_receipt_returns404():
    store = MongoReceipts(MagicMock()); store.db.receipts.find_one.return_value = None
    with pytest.raises(Failure) as error:
        store.find("missing")
    assert error.value.status == 404
