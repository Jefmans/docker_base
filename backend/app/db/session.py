# app/db/session.py
from sqlalchemy import create_engine

DATABASE_URL = "postgresql://test:test@postgres:5432/testdb"
engine = create_engine(DATABASE_URL, echo=True)
