from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request, Response, FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
import time 

# metics 
REQUEST_COUNT = Counter('total_requests', 'Total Number of requests', ['method', 'path','status'])
REQUEST_LATENCY = Histogram('request_latency_seconds', 'Request latency in seconds', ['method', 'path', 'status'])

class PrometheusMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status=str(response.status_code)).inc()
        REQUEST_LATENCY.labels(method=request.method, endpoint=request.url.path, status=str(response.status_code)).observe(process_time).observe(process_time)
        return response
    
def setup_metrics(app: FastAPI):
    app.add_middleware(PrometheusMiddleware)
    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
