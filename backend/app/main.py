from fastapi import FastAPI
from starlette.middleware.proxy_headers import ProxyHeadersMiddleware

from app.routers import health

app = FastAPI()
app.add_middleware(ProxyHeadersMiddleware)

app.include_router(health.router)
