from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sqlalchemy import Column, String, Integer, Table, TIMESTAMP, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
import uuid

Base = declarative_base()

class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String, nullable=False)
    title = Column(String)
    year = Column(Integer)
    type = Column(String)
    topic = Column(String)
    authors = Column(ARRAY(String))
    isbn = Column(String)
    doi = Column(String)
    publisher = Column(String)
    created_at = Column(TIMESTAMP)



# DATABASE_URL = "postgresql://myuser:mypassword@postgres:5432/myappdb"
DATABASE_URL = "postgresql://test:test@postgres:5432/testdb"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

