import os
import time

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)
from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_COUNT = Counter('total_requests', 'Total Number of requests', ['method', 'path', 'status'])
REQUEST_LATENCY = Histogram('request_latency_seconds', 'Request latency in seconds', ['method', 'path', 'status'])


class PrometheusMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        # The route template ("/api/v1/profiles/{username}/memories"), not the raw URL, so
        # each username or asset does not become a separate time series.
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        REQUEST_COUNT.labels(method=request.method, path=path, status=str(response.status_code)).inc()
        REQUEST_LATENCY.labels(method=request.method, path=path, status=str(response.status_code)).observe(process_time)
        return response


def setup_metrics(app: FastAPI):
    app.add_middleware(PrometheusMiddleware)

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        # With several Uvicorn workers each process counts its own requests; in
        # multiprocess mode the counts of all workers are added up on every scrape.
        if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)
            return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
