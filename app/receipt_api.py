import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.core import Failure, invalid
from app.receipts import ReceiptService


def router(identity):
    routes = APIRouter()
    def service(request, claims, write):
        if write:
            allowed = claims.get("service") == "mis-workflow" and "INVENTORY" in claims["roles"]
        else:
            allowed = bool({"ADMIN", "INVENTORY", "SUPERVISOR"}.intersection(claims["roles"]))
        if not allowed:
            raise Failure(403, "FORBIDDEN", "Permisos insuficientes.")
        if request.app.state.receipts is None:
            raise Failure(503, "SERVICE_UNAVAILABLE", "Recepciones no disponibles.")
        return ReceiptService(request.app.state.receipts)
    async def body(request, empty=False):
        raw = await request.body()
        if empty and not raw:
            return {}
        if request.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            raise invalid("body")
        try:
            return json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise invalid("body") from None
    @routes.post("/api/v1/receipts")
    async def prepare(request: Request, claims=Depends(identity)):
        domain = service(request, claims, True)
        resource, created = await run_in_threadpool(domain.prepare, claims["sub"],
            request.headers.get("Idempotency-Key"), await body(request), request.state.trace_id)
        return JSONResponse(resource, status_code=201 if created else 200, headers={"Location": "/api/v1/receipts/" + resource["id"]})
    @routes.get("/api/v1/receipts/{receipt_id}")
    def find(receipt_id: str, request: Request, claims=Depends(identity)):
        return service(request, claims, False).find(receipt_id)
    @routes.post("/api/v1/receipts/{receipt_id}/{action}")
    async def transition(receipt_id: str, action: str, request: Request, claims=Depends(identity)):
        domain = service(request, claims, True)
        if await body(request, empty=True) != {}:
            raise invalid("body")
        return await run_in_threadpool(domain.transition, claims["sub"], request.headers.get("Idempotency-Key"), receipt_id, action)
    return routes
