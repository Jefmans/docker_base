from app.models import Image
from app.schemas import ImageMetadata  # Pydantic schema

def save_image_metadata_list(db, metadata_list):
    for meta in metadata_list:
        db.add(Image(
            book_id=meta.book_id,
            source_pdf=meta.source_pdf,
            page_number=meta.page_number,
            xref=meta.xref,
            filename=meta.filename,
            caption=meta.caption,
            embedding=meta.embedding
        ))
    db.commit()
