from contextlib import asynccontextmanager
import json
import os

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from starlette.exceptions import HTTPException
from starlette.concurrency import run_in_threadpool

from app.core import SupplierService, Failure, invalid
from app.middleware import RequestContext
from app.mongo import MongoSuppliers
from app.security import Tokens
from app.mongo_receipts import MongoReceipts
from app.receipt_api import router as receipt_router


def error(request: Request, failure: Failure) -> JSONResponse:
    content = {"error": failure.code, "message": str(failure), "traceId": request.state.trace_id}
    if failure.field:
        content["details"] = [{"field": failure.field, "message": "Valor invalido."}]
    return JSONResponse(content, status_code=failure.status)


def create_app(store=None, tokens=None, receipts=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        client = None
        if store is None:
            client = MongoClient(os.environ["SUPPLIERS_MONGO_HOST"], username="suppliers_app",
                password=os.environ["SUPPLIERS_MONGO_PASSWORD"], authSource="suppliers",
                replicaSet="rs0", maxPoolSize=10, waitQueueTimeoutMS=2000,
                serverSelectionTimeoutMS=2000, connectTimeoutMS=2000, socketTimeoutMS=5000,
                timeoutMS=5000, tz_aware=True)
            app.state.store = MongoSuppliers(client)
        else:
            app.state.store = store
        app.state.tokens = tokens or Tokens(os.environ["SUPPLIERS_JWKS_URL"])
        app.state.receipts = receipts if receipts is not None else MongoReceipts(client) if client is not None else None
        try:
            await run_in_threadpool(app.state.store.health)
            if app.state.receipts is not None:
                await run_in_threadpool(app.state.receipts.health)
            yield
        finally:
            if client:
                client.close()

    app = FastAPI(title="MediStock - Proveedores", lifespan=lifespan, docs_url=None,
                  redoc_url=None, openapi_url=None)

    app.add_middleware(RequestContext)

    @app.exception_handler(Failure)
    async def failure(request, exception):
        return error(request, exception)

    @app.exception_handler(PyMongoError)
    async def database(request, exception):
        return error(request, Failure(503, "SERVICE_UNAVAILABLE", "Datos no disponibles."))

    @app.exception_handler(RequestValidationError)
    async def validation(request, exception):
        return error(request, invalid("body"))

    @app.exception_handler(HTTPException)
    async def http_error(request, exception):
        status = exception.status_code
        code = "NOT_FOUND" if status == 404 else "METHOD_NOT_ALLOWED" if status == 405 else "VALIDATION_ERROR"
        return error(request, Failure(status, code, "Solicitud no disponible."))

    def identity(request: Request):
        return request.app.state.tokens.authenticate(request.headers.get("Authorization"))

    app.include_router(receipt_router(identity))

    @app.get("/health")
    def health(request: Request):
        request.app.state.store.health()
        if request.app.state.receipts is not None:
            request.app.state.receipts.health()
        return {"status": "UP"}

    @app.post("/api/v1/suppliers")
    async def create(request: Request, claims=Depends(identity)):
        if "ADMIN" not in claims["roles"]:
            raise Failure(403, "FORBIDDEN", "Permisos insuficientes.")
        if request.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            raise invalid("body")
        try:
            body = json.loads(await request.body())
        except (ValueError, UnicodeDecodeError):
            raise invalid("body") from None
        resource, created = await run_in_threadpool(SupplierService(request.app.state.store).create,
            claims["sub"], request.headers.get("Idempotency-Key"), body)
        return JSONResponse(resource, status_code=201 if created else 200,
                            headers={"Location": "/api/v1/suppliers/" + resource["id"]})

    @app.get("/api/v1/suppliers")
    def listing(request: Request, page: str | None = None, limit: str | None = None, claims=Depends(identity)):
        return SupplierService(request.app.state.store).list(page, limit)

    @app.get("/api/v1/suppliers/{supplier_id}")
    def find(request: Request, supplier_id: str, claims=Depends(identity)):
        return SupplierService(request.app.state.store).find(supplier_id)

    return app


app = create_app()
