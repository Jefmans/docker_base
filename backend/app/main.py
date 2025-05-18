from fastapi import FastAPI
from app.routers import health

app = FastAPI(
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

app.include_router(health.router)
