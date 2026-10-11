import asyncio
import json
import re
import pytest
from app.middleware import RequestContext


def exchange(headers, chunks):
    sent, delivered = [], []
    incoming = iter({"type": "http.request", "body": body, "more_body": index < len(chunks) - 1}
                    for index, body in enumerate(chunks))
    scope = {"type": "http", "method": "POST", "path": "/probe", "headers": headers}
    async def receive():
        return next(incoming, {"type": "http.disconnect"})
    async def send(message):
        sent.append(message)
    async def app(scope, receive, send):
        delivered.append(await receive())
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"x-correlation-id", b"untrusted-response")]})
        await send({"type": "http.response.body", "body": b"{}"})
    asyncio.run(RequestContext(app)(scope, receive, send))
    return sent, delivered


def test_correlation_buffers_chunks_and_replaces_response_header():
    sent, delivered = exchange([(b"x-correlation-id", b"safe-trace")], [b"one", b"two"])
    assert sent[0]["status"] == 200
    assert sent[0]["headers"] == [(b"x-correlation-id", b"safe-trace")]
    assert delivered == [{"type": "http.request", "body": b"onetwo", "more_body": False}]


def test_invalid_correlation_rejects_before_app_with_safe_trace():
    sent, delivered = exchange([(b"x-correlation-id", b"bad/trace")], [b"{}"])
    trace = dict(sent[0]["headers"])[b"x-correlation-id"].decode()
    assert sent[0]["status"] == 400 and not delivered
    assert re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", trace)
    assert json.loads(sent[1]["body"])["traceId"] == trace


def test_fragmented_oversized_body_without_content_length_is413():
    sent, delivered = exchange([], [b"a" * 65536, b"b"])
    assert sent[0]["status"] == 413 and not delivered
    assert json.loads(sent[1]["body"])["error"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.parametrize("length", [b"-1", b"invalid"])
def test_invalid_content_length_is400(length):
    sent, delivered = exchange([(b"content-length", length)], [b"{}"])
    assert sent[0]["status"] == 400 and not delivered


def test_exact_body_limit_is_allowed():
    sent, delivered = exchange([], [b"a" * 32768, b"b" * 32768])
    assert sent[0]["status"] == 200 and len(delivered[0]["body"]) == 65536
