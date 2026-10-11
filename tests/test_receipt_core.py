from datetime import date
from uuid import uuid4

import pytest

from app.core import Failure
from app.receipts import NewReceipt, ReceiptService


@pytest.fixture
def payload():
    return {"supplierId": str(uuid4()), "medicationId": str(uuid4()), "reference": "REC-001", "lotNumber": "LOT-001",
            "expiresOn": "2099-01-01", "quantity": 10, "workflowId": str(uuid4()), "initiatedBy": str(uuid4())}


@pytest.mark.parametrize("field,value", [
    ("quantity", 0), ("quantity", -1), ("quantity", 1000001), ("quantity", True), ("quantity", 1.5), ("quantity", "10"),
    ("reference", "a/b"), ("reference", ""), ("reference", "a" * 41), ("lotNumber", "lote\u00f1"),
    ("expiresOn", "0000-01-01"), ("expiresOn", "2026-02-30"), ("expiresOn", "2026-1-1"), ("expiresOn", None),
    ("supplierId", "bad"), ("medicationId", None), ("workflowId", "bad"), ("initiatedBy", "bad")])
def test_invalid_receipt(payload, field, value):
    with pytest.raises(Failure) as error:
        NewReceipt.parse({**payload, field: value})
    assert error.value.status == 400


def test_missing_unknown_and_non_object(payload):
    for body in (None, [], {**payload, "unknown": 1}, {k: v for k, v in payload.items() if k != "workflowId"}):
        with pytest.raises(Failure):
            NewReceipt.parse(body)


def test_normalization_fingerprint_and_civil_expiration(payload):
    request = NewReceipt.parse(payload)
    normalized = NewReceipt.parse({**payload, "reference": " rec-001 ", "lotNumber": "lot-001"})
    assert request.fingerprint() == normalized.fingerprint()
    assert request.fingerprint() != NewReceipt.parse({**payload, "quantity": 11}).fingerprint()
    request.fresh(date(2098, 12, 31))
    with pytest.raises(Failure) as error:
        request.fresh(date(2099, 1, 1))
    assert error.value.code == "LOT_EXPIRED"


@pytest.mark.parametrize("key", [None, "short", "a/bcdefgh", "a" * 129])
def test_invalid_intention_key(key):
    with pytest.raises(Failure):
        ReceiptService.key(key)


def test_prepare_delegates_actor_key_normalized_body_and_trace(payload):
    from unittest.mock import Mock
    store = Mock(); store.prepare.return_value = ({"id": "synthetic"}, True)
    request = {**payload, "reference": " rec-001 "}
    result = ReceiptService(store).prepare("actor", "receipt-key-001", request, "safe-trace")
    assert result == ({"id": "synthetic"}, True)
    store.prepare.assert_called_once_with("actor", "receipt-key-001", NewReceipt.parse(request), "safe-trace")


def test_find_delegates_canonical_identifier():
    from unittest.mock import Mock
    store = Mock(); receipt_id = str(uuid4()); store.find.return_value = {"id": receipt_id}
    assert ReceiptService(store).find(receipt_id) == {"id": receipt_id}
    store.find.assert_called_once_with(receipt_id)


@pytest.mark.parametrize("action", ["confirm", "void"])
def test_transition_delegates_allowed_action(action):
    from unittest.mock import Mock
    store = Mock(); receipt_id = str(uuid4()); store.transition.return_value = {"id": receipt_id}
    assert ReceiptService(store).transition("actor", "transition-key", receipt_id, action) == {"id": receipt_id}
    store.transition.assert_called_once_with("actor", "transition-key", receipt_id, action)


def test_unknown_action_rejects_before_store():
    from unittest.mock import Mock
    store = Mock()
    with pytest.raises(Failure) as error:
        ReceiptService(store).transition("actor", "transition-key", str(uuid4()), "activate")
    assert error.value.status == 404
    store.transition.assert_not_called()


@pytest.mark.parametrize("receipt_id", ["invalid", "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"])
def test_noncanonical_find_rejects_before_store(receipt_id):
    from unittest.mock import Mock
    store = Mock()
    with pytest.raises(Failure) as error:
        ReceiptService(store).find(receipt_id)
    assert error.value.status == 400
    store.find.assert_not_called()
