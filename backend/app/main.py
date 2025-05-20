from fastapi import FastAPI
from app.routers import health, upload, extract

app = FastAPI(
    title="My API",
    docs_url="/backend/docs",
    redoc_url="/backend/redoc",
    openapi_url="/backend/openapi.json"
)

# Optional: If you're mounting routes, align them too
app.include_router(health.router, prefix="/backend")
app.include_router(upload.router, prefix="/backend")
app.include_router(extract.router, prefix="/backend")
