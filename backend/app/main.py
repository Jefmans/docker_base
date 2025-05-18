from fastapi import FastAPI
from fastapi.middleware.proxy_headers import ProxyHeadersMiddleware

from app.routers import health

app = FastAPI()
app.add_middleware(ProxyHeadersMiddleware)

app.include_router(health.router)
