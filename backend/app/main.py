from fastapi import FastAPI
from app.routers import health

app = FastAPI(
    title="My API",
    docs_url="/docs",                # Exposed at /api/docs (after Traefik prefix strip)
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

app.include_router(health.router)
