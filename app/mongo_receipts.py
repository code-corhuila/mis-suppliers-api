from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4
from zoneinfo import ZoneInfo

import pymongo
from pymongo.errors import DuplicateKeyError

from app.core import Failure
from app.mongo import MongoSuppliers
from app.receipts import NewReceipt


class MongoReceipts:
    def __init__(self, client):
        self.base = MongoSuppliers(client)
        self.db = self.base.db

    def health(self):
        with pymongo.timeout(5):
            if not {"receipts", "receipt_requests"}.issubset(self.db.list_collection_names()):
                raise Failure(503, "SERVICE_UNAVAILABLE", "Migraciones de recepciones pendientes.")
            for collection, names in ((self.db.receipts, ("uq_reference", "uq_workflow")),
                                      (self.db.receipt_requests, ("uq_receipt_intention",))):
                indexes = collection.index_information()
                if any(not indexes.get(name, {}).get("unique") for name in names):
                    raise Failure(503, "SERVICE_UNAVAILABLE", "Indice de recepciones ausente.")

    @staticmethod
    def now():
        now = datetime.now(timezone.utc)
        return now.replace(microsecond=now.microsecond // 1000 * 1000)

    @staticmethod
    def resource(document):
        fields = list(NewReceipt.__dataclass_fields__) + ["status", "createdBy", "createdAt", "changedBy", "changedAt", "traceId"]
        value = {field: document[field] for field in fields}
        value["id"] = document["_id"]
        for field in ("createdAt", "changedAt"):
            if value[field] is not None:
                value[field] = value[field].astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        return value

    def intention(self, actor, key, operation):
        return {"actor": actor, "operation": operation, "requestKey": key}

    def remember(self, scope, fingerprint, resource, session):
        self.db.receipt_requests.insert_one({"_id": str(uuid4()), **scope, "requestHash": fingerprint,
            "receiptId": resource["id"], "response": resource, "createdAt": self.now()}, session=session)

    def prepare(self, actor, key, request, trace):
        scope, fingerprint = self.intention(actor, key, "prepareReceipt"), request.fingerprint()
        def write(session):
            previous = self.db.receipt_requests.find_one(scope, session=session)
            if previous:
                return self.base.replay(previous, fingerprint)
            request.fresh(self.now().astimezone(ZoneInfo("America/Bogota")).date())
            supplier = self.db.suppliers.find_one({"_id": request.supplierId}, session=session)
            if not supplier or supplier["active"] is not True:
                raise Failure(422, "BUSINESS_RULE_VIOLATION", "Proveedor no disponible.", "supplierId")
            document = {"_id": str(uuid4()), **asdict(request), "status": "PENDING", "createdBy": actor,
                "createdAt": self.now(), "changedBy": None, "changedAt": None, "traceId": trace}
            self.db.receipts.insert_one(document, session=session)
            resource = self.resource(document)
            self.remember(scope, fingerprint, resource, session)
            return resource, True
        with pymongo.timeout(5):
            try:
                return self.base.transaction(write)
            except DuplicateKeyError:
                previous = self.db.receipt_requests.find_one(scope)
                if previous:
                    return self.base.replay(previous, fingerprint)
                raise Failure(422, "BUSINESS_RULE_VIOLATION", "Referencia o saga ya registrada.") from None

    def find(self, receipt_id):
        with pymongo.timeout(5):
            document = self.db.receipts.find_one({"_id": receipt_id})
            if not document:
                raise Failure(404, "NOT_FOUND", "Recepcion inexistente.")
            return self.resource(document)

    def transition(self, actor, key, receipt_id, action):
        scope = self.intention(actor, key, "confirmReceipt" if action == "confirm" else "voidReceipt")
        fingerprint = sha256(receipt_id.encode()).hexdigest()
        target = "CONFIRMED" if action == "confirm" else "VOIDED"
        def write(session):
            previous = self.db.receipt_requests.find_one(scope, session=session)
            if previous:
                return self.base.replay(previous, fingerprint)[0]
            document = self.db.receipts.find_one({"_id": receipt_id}, session=session)
            if not document:
                raise Failure(404, "NOT_FOUND", "Recepcion inexistente.")
            if document["status"] != target:
                if document["status"] == "VOIDED":
                    raise Failure(422, "BUSINESS_RULE_VIOLATION", "Recepcion anulada.")
                changed = {"status": target, "changedBy": actor, "changedAt": self.now()}
                self.db.receipts.update_one({"_id": receipt_id}, {"$set": changed}, session=session)
                document.update(changed)
            resource = self.resource(document)
            self.remember(scope, fingerprint, resource, session)
            return resource
        with pymongo.timeout(5):
            try:
                return self.base.transaction(write)
            except DuplicateKeyError:
                previous = self.db.receipt_requests.find_one(scope)
                if previous:
                    return self.base.replay(previous, fingerprint)[0]
                raise
