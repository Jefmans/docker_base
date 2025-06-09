from pydantic import BaseModel
from typing import List, Optional

class ImageCreate(BaseModel):
    book_id: str
    source_pdf: str
    page_number: int
    xref: int
    filename: str
    caption: Optional[str] = ""
    embedding: Optional[List[float]] = None
