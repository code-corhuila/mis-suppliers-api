from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Protocol
from uuid import UUID

from email_validator import EmailNotValidError, validate_email


class Failure(Exception):
    def __init__(self, status: int, code: str, message: str, field: str | None = None):
        super().__init__(message)
        self.status, self.code, self.field = status, code, field


def invalid(field: str) -> Failure:
    return Failure(400, "VALIDATION_ERROR", "Datos invalidos.", field)


def text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise invalid(field)
    value = value.strip()
    if not value or len(value) > maximum:
        raise invalid(field)
    return value


@dataclass(frozen=True)
class NewSupplier:
    documentNumber: str
    name: str
    phone: str | None
    email: str | None
    address: str | None

    @classmethod
    def parse(cls, body: object) -> "NewSupplier":
        if not isinstance(body, dict):
            raise invalid("body")
        allowed = {"documentNumber", "name", "phone", "email", "address"}
        if set(body) - allowed:
            raise invalid(sorted(set(body) - allowed)[0])
        document = text(body.get("documentNumber"), "documentNumber", 40)
        if not re.fullmatch(r"[A-Za-z0-9-]+", document):
            raise invalid("documentNumber")
        optional = {field: text(body[field], field, limit) if field in body else None
                    for field, limit in (("phone", 30), ("email", 254), ("address", 240))}
        if optional["email"] is not None:
            try:
                validate_email(optional["email"], check_deliverability=False)
            except EmailNotValidError:
                raise invalid("email") from None
            optional["email"] = optional["email"].lower()
        return cls(document.upper(), text(body.get("name"), "name", 160), **optional)

    def fingerprint(self) -> str:
        ordered = [self.documentNumber, self.name, self.phone, self.email, self.address]
        canonical = json.dumps(ordered, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return sha256(canonical).hexdigest()


class Suppliers(Protocol):
    def create(self, actor: str, key: str, request: NewSupplier) -> tuple[dict, bool]: ...
    def find(self, supplier_id: str) -> dict: ...
    def list(self, page: int, limit: int) -> dict: ...
    def health(self) -> None: ...


class SupplierService:
    def __init__(self, suppliers: Suppliers):
        self.suppliers = suppliers

    def create(self, actor: str, key: str | None, body: object) -> tuple[dict, bool]:
        if key is None or not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", key):
            raise invalid("Idempotency-Key")
        return self.suppliers.create(actor, key, NewSupplier.parse(body))

    def find(self, supplier_id: str) -> dict:
        try:
            if str(UUID(supplier_id)) != supplier_id:
                raise ValueError()
        except ValueError:
            raise invalid("id") from None
        return self.suppliers.find(supplier_id)

    def list(self, page: str | None, limit: str | None) -> dict:
        def number(raw: str | None, field: str, default: int) -> int:
            if raw is None:
                return default
            try:
                if not re.fullmatch(r"[0-9]+", raw):
                    raise ValueError()
                return int(raw)
            except ValueError:
                raise invalid(field) from None
        p, size = number(page, "page", 1), number(limit, "limit", 20)
        if p < 1:
            raise invalid("page")
        if not 1 <= size <= 100:
            raise invalid("limit")
        return self.suppliers.list(p, size)
