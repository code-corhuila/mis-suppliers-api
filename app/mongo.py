from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

import pymongo
from pymongo import MongoClient, ReadPreference
from pymongo.errors import DuplicateKeyError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from app.core import Failure, NewSupplier


class MongoSuppliers:
    def __init__(self, client: MongoClient):
        self.client = client
        self.db = client["suppliers"]

    def health(self) -> None:
        with pymongo.timeout(5):
            if not self.client.admin.command("hello").get("isWritablePrimary"):
                raise Failure(503, "SERVICE_UNAVAILABLE", "Replica set no listo.")
            names = set(self.db.list_collection_names())
            if not {"suppliers", "creation_requests"}.issubset(names):
                raise Failure(503, "SERVICE_UNAVAILABLE", "Migraciones pendientes.")
            if not self.db.suppliers.index_information().get("uq_document", {}).get("unique"):
                raise Failure(503, "SERVICE_UNAVAILABLE", "Indice de negocio ausente.")
            if not self.db.creation_requests.index_information().get("uq_intention", {}).get("unique"):
                raise Failure(503, "SERVICE_UNAVAILABLE", "Indice de intencion ausente.")

    @staticmethod
    def resource(document: dict) -> dict:
        date = document["createdAt"].astimezone(timezone.utc)
        return {"id": document["_id"], **{field: document[field] for field in
                ("documentNumber", "name", "phone", "email", "address", "active")},
                "createdAt": date.isoformat(timespec="milliseconds").replace("+00:00", "Z")}

    @staticmethod
    def replay(previous: dict, fingerprint: str) -> tuple[dict, bool]:
        if previous["requestHash"] != fingerprint:
            raise Failure(409, "IDEMPOTENCY_CONFLICT", "Clave usada con otros datos.")
        return previous["response"], False

    def transaction(self, callback):
        with self.client.start_session() as session:
            return session.with_transaction(callback, read_concern=ReadConcern("snapshot"),
                write_concern=WriteConcern("majority", wtimeout=5000),
                read_preference=ReadPreference.PRIMARY, max_commit_time_ms=5000)

    def create(self, actor: str, key: str, request: NewSupplier) -> tuple[dict, bool]:
        intention = {"actor": actor, "operation": "createSupplier", "requestKey": key}
        fingerprint = request.fingerprint()

        def write(session):
            previous = self.db.creation_requests.find_one(intention, session=session)
            if previous:
                return self.replay(previous, fingerprint)
            now = datetime.now(timezone.utc)
            now = now.replace(microsecond=now.microsecond // 1000 * 1000)
            document = {"_id": str(uuid4()), **asdict(request), "active": True,
                        "createdAt": now, "createdBy": actor}
            self.db.suppliers.insert_one(document, session=session)
            resource = self.resource(document)
            self.db.creation_requests.insert_one({"_id": str(uuid4()), **intention,
                "requestHash": fingerprint, "supplierId": document["_id"], "response": resource,
                "createdAt": now}, session=session)
            return resource, True

        with pymongo.timeout(5):
            try:
                return self.transaction(write)
            except DuplicateKeyError:
                # Tras abortar, se consulta el resultado confirmado de la intencion concurrente.
                previous = self.db.creation_requests.find_one(intention)
                if previous:
                    return self.replay(previous, fingerprint)
                if self.db.suppliers.find_one({"documentNumber": request.documentNumber}):
                    raise Failure(422, "BUSINESS_RULE_VIOLATION", "Documento ocupado.", "documentNumber") from None
                raise

    def find(self, supplier_id: str) -> dict:
        with pymongo.timeout(5):
            document = self.db.suppliers.find_one({"_id": supplier_id})
            if not document:
                raise Failure(404, "NOT_FOUND", "Proveedor inexistente.")
            return self.resource(document)

    def list(self, page: int, limit: int) -> dict:
        def read(session):
            total = self.db.suppliers.count_documents({}, session=session)
            offset = (page - 1) * limit
            documents = [] if offset >= total else list(self.db.suppliers.find({}, session=session)
                .sort([("createdAt", -1), ("_id", -1)]).skip(offset).limit(limit))
            return {"data": [self.resource(doc) for doc in documents],
                    "meta": {"page": page, "limit": limit, "total": total,
                             "totalPages": (total + limit - 1) // limit}}
        with pymongo.timeout(5):
            return self.transaction(read)
