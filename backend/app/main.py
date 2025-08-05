from fastapi import FastAPI
from app.routers import health, upload, extract, process, query, query_agent, agent
from app.db.db import Base, engine  # Ensure engine is correctly configured
from app.db.models import research_node_orm  # force table registration

# Auto-create tables
Base.metadata.create_all(bind=engine)



app = FastAPI(
    title="My API",
    # docs_url="/backend/docs",
    # redoc_url="/backend/redoc",
    # openapi_url="/backend/openapi.json",
    root_path="/backend"
)

# Optional: If you're mounting routes, align them too
app.include_router(health.router)
app.include_router(upload.router)
app.include_router(extract.router)
app.include_router(process.router)
app.include_router(query.router)
app.include_router(query_agent.router)
app.include_router(agent.router)
