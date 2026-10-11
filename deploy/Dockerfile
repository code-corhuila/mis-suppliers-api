FROM python:3.12-slim-bookworm AS dependencies
WORKDIR /build
COPY requirements.txt requirements-dev.txt .
RUN pip install --no-cache-dir --target=/deps -r requirements-dev.txt
COPY app app
COPY tests tests
COPY docs docs
RUN PYTHONPATH=/deps python tests/check_contracts.py
RUN PYTHONPATH=/deps python -m pytest -q
FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=dependencies /build/app app
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080","--timeout-keep-alive","30","--timeout-graceful-shutdown","20","--no-access-log"]
