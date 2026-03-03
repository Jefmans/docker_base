from sqlalchemy import Column, Integer, String

from app.db.base import Base


class ImageRecord(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(String, index=True)
    source_pdf = Column(String)
    page_number = Column(Integer)
    xref = Column(Integer)
    filename = Column(String, unique=True)
    caption = Column(String)
