from fastapi import FastAPI
from app.routers import health

app = FastAPI(
    title="My API",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# Prefix router to align everything under `/api`
app.include_router(health.router, prefix="/api")
