from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
import json
import re
from uuid import UUID
from typing import Protocol

from app.core import Failure, invalid


def identifier(value, field):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError()
    except ValueError:
        raise invalid(field) from None
    return value


@dataclass(frozen=True)
class NewReceipt:
    supplierId: str
    medicationId: str
    reference: str
    lotNumber: str
    expiresOn: str
    quantity: int
    workflowId: str
    initiatedBy: str

    @classmethod
    def parse(cls, body):
        fields = set(cls.__dataclass_fields__)
        if not isinstance(body, dict) or set(body) - fields:
            raise invalid("body")
        if fields - set(body):
            raise invalid(sorted(fields - set(body))[0])
        values = dict(body)
        for field in ("supplierId", "medicationId", "workflowId", "initiatedBy"):
            values[field] = identifier(body[field], field)
        for field in ("reference", "lotNumber"):
            value = body[field]
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,40}", value.strip()):
                raise invalid(field)
            values[field] = value.strip().upper()
        try:
            if not isinstance(body["expiresOn"], str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", body["expiresOn"]):
                raise ValueError()
            date.fromisoformat(body["expiresOn"])
        except ValueError:
            raise invalid("expiresOn") from None
        if type(body["quantity"]) is not int or not 1 <= body["quantity"] <= 1000000:
            raise invalid("quantity")
        return cls(**values)

    def fresh(self, today):
        if date.fromisoformat(self.expiresOn) <= today:
            raise Failure(422, "LOT_EXPIRED", "Lote vencido.", "expiresOn")

    def fingerprint(self):
        return sha256(json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Receipts(Protocol):
    def prepare(self, actor: str, key: str, request: NewReceipt, trace: str) -> tuple[dict, bool]: ...
    def find(self, receipt_id: str) -> dict: ...
    def transition(self, actor: str, key: str, receipt_id: str, action: str) -> dict: ...


class ReceiptService:
    def __init__(self, store: Receipts):
        self.store = store

    @staticmethod
    def key(value):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", value):
            raise invalid("Idempotency-Key")
        return value

    def prepare(self, actor, key, body, trace):
        return self.store.prepare(actor, self.key(key), NewReceipt.parse(body), trace)

    def find(self, receipt_id):
        return self.store.find(identifier(receipt_id, "id"))

    def transition(self, actor, key, receipt_id, action):
        if action not in {"confirm", "void"}:
            raise Failure(404, "NOT_FOUND", "Operacion inexistente.")
        return self.store.transition(actor, self.key(key), identifier(receipt_id, "id"), action)
