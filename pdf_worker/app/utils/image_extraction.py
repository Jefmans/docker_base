import os
import fitz  # PyMuPDF
from PIL import Image
import io
import re
from itertools import chain
from dataclasses import dataclass, asdict
from typing import List, Tuple, Dict


from app.models import ImageMetadata
from minio import Minio

# --- Setup MinIO ---
minio_client = Minio(
    "minio:9000",
    access_key="minioadmin",
    secret_key="minioadmin123",
    secure=False
)
BUCKET_NAME = "images"


# --- Caption detection regex ---
caption_regex = re.compile(
    r'\b(?:fig(?:s)?\.?|figure(?:s)?|plate(?:s)?|illustration(?:s)?|illus\.?|image(?:s)?|img\.?|'
    r'diagram(?:s)?|diag\.?|chart(?:s)?|graph(?:s)?|photo(?:s)?|phot\.?|table(?:s)?|tab\.?|'
    r'exhibit(?:s)?|ex\.?|panel(?:s)?|graphic(?:s)?|snapshot(?:s)?|rendering(?:s)?|'
    r'infographic(?:s)?|layout(?:s)?)\b',
    re.IGNORECASE
)


def extract_captions_with_bbox(page) -> List[Dict]:
    """Extracts figure captions from the page with bounding boxes."""
    captions = []
    for block in page.get_text("blocks"):
        text = block[4].strip()
        if caption_regex.match(text):
            captions.append({"text": text, "bbox": tuple(block[:4])})
    return captions


def find_closest_caption_to_group(group_bbox: Tuple[float], captions_with_bbox: List[Dict]) -> Dict:
    """Finds the caption closest in vertical position to a group bounding box."""
    group_y_center = (group_bbox[1] + group_bbox[3]) / 2
    return min(captions_with_bbox, key=lambda c: abs((c["bbox"][1] + c["bbox"][3]) / 2 - group_y_center), default=None)


def group_boxes_by_rows(image_boxes: List[Tuple[float]], y_threshold=100) -> List[List[Tuple[float]]]:
    """Groups image boxes by horizontal rows based on vertical proximity."""
    image_boxes.sort(key=lambda b: -b[1])
    groups = [[image_boxes[0]]]
    for box in image_boxes[1:]:
        avg_y_top = sum(b[1] for b in groups[-1]) / len(groups[-1])
        if abs(box[1] - avg_y_top) < y_threshold:
            groups[-1].append(box)
        else:
            groups.append([box])
    return groups


# def save_image(filename: str, image_bytes: bytes, output_dir: str):
#     """Saves an image from bytes to disk."""
#     os.makedirs(output_dir, exist_ok=True)
#     with open(os.path.join(output_dir, filename), "wb") as f:
#         f.write(image_bytes)

def upload_image_to_minio(image_bytes: bytes, filename: str, content_type: str = "image/png"):
    

    stream = io.BytesIO(image_bytes)
    stream.seek(0)  # ✅ Ensure stream is at the beginning

    try:
        minio_client.put_object(
            bucket_name="images",  # make sure this bucket exists
            object_name=filename,
            data=stream,
            length=len(image_bytes),
            content_type=content_type
        )
        print(f"✅ Uploaded to MinIO: {filename}")
    except Exception as e:
        print(f"❌ Error uploading {filename} to MinIO: {e}")
        raise


def process_images_and_captions(
    pdf_path: str,
    page_range: List[int],
    book_id: str = "book",
    size_threshold: int = 200 * 200,
    dpi: int = 300,
    padding: int = 20,
    output_dir: str = "output"
) -> List[ImageMetadata]:
    """Processes a range of PDF pages, saving matched images or screenshots and returning metadata."""

    # os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    metadata_list = []

    # for page_index in range(len(doc)):
    for page_index in page_range:
        page = doc[page_index]
        layout = page.get_text("dict")
        caption_paragraphs = extract_captions_with_bbox(page)
        caption_count = len(caption_paragraphs)

        image_infos = []
        image_boxes = [
            block["bbox"] for block in layout["blocks"]
            if block.get("type") == 1 and "image" in block
        ]

        for img in page.get_images(full=True):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image = Image.open(io.BytesIO(base_image["image"]))
            area = image.width * image.height

            image_infos.append({
                "bytes": base_image["image"],
                "ext": base_image["ext"],
                "area": area,
                "xref": xref
            })

        image_count = len(image_infos)
        page_label = f"page{page_index + 1}"

        if caption_count == 0:
            print(f"🚫 No captions for {page_label}, skipping.")
            continue

        elif image_count == caption_count:
            print(f"🖼️ Matched images and captions on {page_label}, saving large images.")
            for i, info in enumerate(image_infos):
                if info["area"] >= size_threshold:
                    filename = f"{book_id}_page{page_index+1:03}_xref{info['xref']}.{info['ext']}"
                    # save_image(filename, info["bytes"], output_dir)
                    # upload_image_to_minio(info["bytes"], filename)
                    try:
                        upload_image_to_minio(
                                image_bytes=info["bytes"],
                                filename=filename,
                                content_type=f"image/{info['ext']}"
                            )
                    except Exception as e:
                        print(f"❌ Skipping image due to error: {e}")
                        continue

                    caption_text = caption_paragraphs[i]["text"] if i < caption_count else ""
                    metadata_list.append(ImageMetadata(
                        book_id, pdf_path, page_index + 1, info["xref"], filename, caption_text
                    ))
                    print(f"✅ Saved: {filename}")

        elif image_count > caption_count and image_boxes:
            print(f"📸 More images than captions on {page_label}, taking grouped screenshots.")
            groups = group_boxes_by_rows(image_boxes)
            all_boxes = list(chain.from_iterable(groups))

            if len(groups) > caption_count:
                new_groups = groups[:caption_count - 1]
                new_groups.append(list(chain.from_iterable(groups[caption_count - 1:])))
                groups = new_groups

            assert sorted(map(tuple, chain.from_iterable(groups))) == sorted(map(tuple, all_boxes)), f"❌ Box mismatch on {page_label}"

            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)

            for i, group in enumerate(groups):
                x0 = min(b[0] for b in group) - padding
                y0 = min(b[1] for b in group) - padding
                x1 = max(b[2] for b in group) + padding
                y1 = max(b[3] for b in group) + padding

                rect = fitz.Rect(
                    max(x0, page.rect.x0),
                    max(y0, page.rect.y0),
                    min(x1, page.rect.x1),
                    min(y1, page.rect.y1)
                )

                pix = page.get_pixmap(matrix=mat, clip=rect)
                # filename = f"{book_id}_page{page_index+1:03}_group{i+1}.png"
                # pix.save(os.path.join(output_dir, filename))
                img_bytes = pix.tobytes("png")
                filename = f"{book_id}_page{page_index+1:03}_group{i+1}.png"
                upload_image_to_minio(img_bytes, filename)

                closest_caption = find_closest_caption_to_group((x0, y0, x1, y1), caption_paragraphs)
                caption_text = closest_caption["text"] if closest_caption else ""
                metadata_list.append(ImageMetadata(
                    book_id, pdf_path, page_index + 1, -1, filename, caption_text
                ))
                print(f"📷 Saved screenshot: {filename}")

        else:
            print(f"⚠️ Unexpected case for {page_label}, skipping.")

    print("✅ All pages processed.")
    return metadata_list




# --- Example run ---
# if __name__ == "__main__":
#     file_path = 'pdfs/black_hole.pdf'
#     # file_path = 'pdfs/astronomy.pdf'
#     # file_path = 'pdfs/de_witte.pdf'
#     # result = process_page_smart(pdf_path=file_path, page_range=(38, 55, 56, 57, 58, 59, 48), book_id="astronomy")
#     # result = process_page_smart(pdf_path=file_path, page_range=(56,), book_id="astronomy")
#     result = process_page_smart(pdf_path=file_path, page_range=(38, 55, 56, 57), book_id="astronomy")
#     # result = process_page_smart(pdf_path=file_path, book_id="astronomy")
    
#     for entry in result:
#         print(asdict(entry))  # This shows the metadata per image/screenshot
