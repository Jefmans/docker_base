from fastapi import FastAPI
from app.routers import health, upload, extract, process, query, agent
from app.db.db import engine
from app.db.base import Base  
# from app.db.models import research_node_orm, question_orm, node_question_orm, chunk_orm, node_chunk_orm

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
# app.include_router(query_agent.router)
app.include_router(agent.router) 

