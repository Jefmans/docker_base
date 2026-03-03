from app.db.db import ImageRecord
from app.schemas import ImageMetadata

def save_image_metadata_list(db, metadata_list: list[ImageMetadata]):
    filenames = [meta.filename for meta in metadata_list if meta.filename]
    existing = set()
    if filenames:
        existing = {
            filename
            for (filename,) in db.query(ImageRecord.filename).filter(ImageRecord.filename.in_(filenames)).all()
        }

    for meta in metadata_list:
        if meta.filename in existing:
            continue
        record = ImageRecord(
            book_id=meta.book_id,
            source_pdf=meta.source_pdf,
            page_number=meta.page_number,
            xref=meta.xref,
            filename=meta.filename,
            caption=meta.caption,
        )
        db.add(record)
    db.flush()
