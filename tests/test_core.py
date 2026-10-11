import pytest
from app.core import Failure, NewSupplier, SupplierService


def body(**changes):
    return {"documentNumber": "PRV-001", "name": "Proveedor sintetico", **changes}


def test_normalization_and_optional_omission():
    result = NewSupplier.parse(body(documentNumber=" prv-001 ", name=" Proveedor sintetico "))
    assert result.documentNumber == "PRV-001"
    assert result.name == "Proveedor sintetico"
    assert (result.phone, result.email, result.address) == (None, None, None)


def test_normalized_fingerprint_is_stable():
    first = NewSupplier.parse(body(email=" OPERADOR@EXAMPLE.COM "))
    second = NewSupplier.parse(body(email="operador@example.com"))
    assert first.email == "operador@example.com"
    assert first.fingerprint() == second.fingerprint()
    assert first.fingerprint() != NewSupplier.parse(body(name="Otro proveedor")).fingerprint()


@pytest.mark.parametrize("changes", [
    {"documentNumber": "A_1"}, {"documentNumber": "A" * 41}, {"documentNumber": "\u00df"},
    {"name": " "}, {"name": 123}, {"name": "x" * 161}, {"phone": None}, {"phone": ""},
    {"email": "invalid"}, {"email": None}, {"address": "x" * 241}, {"active": False},
])
def test_rejects_invalid_data(changes):
    with pytest.raises(Failure) as failure:
        NewSupplier.parse(body(**changes))
    assert failure.value.status == 400


class Store:
    def create(self, *args):
        return {}, True
    def list(self, page, limit):
        return {"page": page, "limit": limit}
    def find(self, supplier_id):
        return {"id": supplier_id}


@pytest.mark.parametrize("key", [None, "short", " with-space", "bad/key!", "x" * 129])
def test_invalid_idempotency_key(key):
    with pytest.raises(Failure) as failure:
        SupplierService(Store()).create("actor", key, body())
    assert failure.value.field == "Idempotency-Key"


@pytest.mark.parametrize("page,limit", [("0", "20"), ("1", "0"), ("1", "101"), ("", "20"), ("1.5", "20")])
def test_invalid_pagination(page, limit):
    with pytest.raises(Failure):
        SupplierService(Store()).list(page, limit)


def test_default_pagination():
    assert SupplierService(Store()).list(None, None) == {"page": 1, "limit": 20}


@pytest.mark.parametrize("supplier_id", ["not-uuid", "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA", "1-1-1-1-1"])
def test_noncanonical_uuid(supplier_id):
    with pytest.raises(Failure):
        SupplierService(Store()).find(supplier_id)


def test_create_delegates_normalized_request_and_returns_port_result():
    from unittest.mock import Mock
    store = Mock()
    store.create.return_value = ({"id": "synthetic"}, True)
    request = body(documentNumber=" prv-001 ")
    assert SupplierService(store).create("actor", "valid-key-123", request) == ({"id": "synthetic"}, True)
    store.create.assert_called_once_with("actor", "valid-key-123", NewSupplier.parse(request))


def test_find_accepts_canonical_uuid_and_preserves_identifier():
    supplier_id = "11111111-1111-4111-8111-111111111111"
    assert SupplierService(Store()).find(supplier_id) == {"id": supplier_id}
