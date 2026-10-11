import asyncio
import json
import logging
import re
from uuid import uuid4

from starlette.responses import JSONResponse

from app.core import Failure, invalid

logger = logging.getLogger("suppliers.requests")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


class RequestContext:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope["headers"]}
        supplied = headers.get("x-correlation-id")
        bad = supplied is not None and not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", supplied)
        trace = str(uuid4()) if supplied is None or bad else supplied
        scope.setdefault("state", {})["trace_id"] = trace
        status, started = 500, False

        async def correlated(message):
            nonlocal status, started
            if message["type"] == "http.response.start":
                status, started = message["status"], True
                message["headers"] = [(key, value) for key, value in message.get("headers", [])
                                      if key.lower() != b"x-correlation-id"]
                message["headers"].append((b"x-correlation-id", trace.encode("ascii")))
            await send(message)

        async def reject(failure):
            content = {"error": failure.code, "message": str(failure), "traceId": trace}
            if failure.field:
                content["details"] = [{"field": failure.field, "message": "Valor invalido."}]
            await JSONResponse(content, status_code=failure.status)(scope, receive, correlated)

        try:
            if bad:
                raise invalid("X-Correlation-Id")
            length = headers.get("content-length")
            if length is not None:
                if not length.isdigit():
                    raise invalid("Content-Length")
                if int(length) > 65536:
                    raise Failure(413, "PAYLOAD_TOO_LARGE", "Cuerpo demasiado grande.")
            data = bytearray()
            async with asyncio.timeout(15):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(data) + len(chunk) > 65536:
                        raise Failure(413, "PAYLOAD_TOO_LARGE", "Cuerpo demasiado grande.")
                    data.extend(chunk)
                    if not message.get("more_body", False):
                        break
            delivered = False

            async def buffered():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(data), "more_body": False}
                return await receive()

            await self.app(scope, buffered, correlated)
        except Failure as failure:
            await reject(failure)
        except TimeoutError:
            await reject(Failure(408, "REQUEST_TIMEOUT", "Tiempo de lectura agotado."))
        except Exception:
            if started:
                raise
            await reject(Failure(500, "INTERNAL_ERROR", "Error interno."))
        finally:
            logger.info(json.dumps(
                {"event": "http_request", "traceId": trace, "method": scope["method"], "status": status}))
