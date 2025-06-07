from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker




# DATABASE_URL = "postgresql://myuser:mypassword@postgres:5432/myappdb"
DATABASE_URL = "postgresql://test:test@postgres:5432/testdb"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

