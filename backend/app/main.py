from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.proxy_headers import ProxyHeadersMiddleware
from app.routers import health

app = FastAPI()

# Make FastAPI aware of reverse proxy headers
app.add_middleware(ProxyHeadersMiddleware)

# Your actual routes
app.include_router(health.router)
