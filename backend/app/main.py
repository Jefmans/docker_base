from fastapi import FastAPI
from app.routers import health, upload, extract, process
from app.db import Base, engine  # Ensure engine is correctly configured

# Auto-create tables
Base.metadata.create_all(bind=engine)



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
app.include_router(process.router)