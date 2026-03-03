import logging
import os
import threading
from typing import Any

import requests

from app.utils.metadata import get_doc_info
from app.utils.pdf_reader import download_from_minio
from app.utils.pdf_pipeline import process_pdf


logger = logging.getLogger(__name__)

BACKEND_INTERNAL_URL = os.getenv("BACKEND_INTERNAL_URL", "http://backend:8000")
WORKER_NAME = os.getenv("PDF_WORKER_NAME", "pdf_worker")
POLL_INTERVAL_SECONDS = float(os.getenv("PDF_WORKER_POLL_INTERVAL_SECONDS", "5"))
RUNNER_ENABLED = os.getenv("PDF_WORKER_RUNNER_ENABLED", "true").lower() in {"1", "true", "yes"}

_worker_started = False
_stop_event = threading.Event()


def _claim_job() -> dict[str, Any] | None:
    response = requests.post(
        f"{BACKEND_INTERNAL_URL}/internal/jobs/claim",
        json={"worker_name": WORKER_NAME},
        timeout=30,
    )
    if response.status_code == 204:
        return None
    response.raise_for_status()
    return response.json()


def _report_complete(job_id: str, *, metadata: dict[str, Any] | None, images: list[dict[str, Any]], stats: dict[str, Any]):
    response = requests.post(
        f"{BACKEND_INTERNAL_URL}/internal/jobs/{job_id}/complete",
        json={"metadata": metadata, "images": images, "stats": stats},
        timeout=120,
    )
    response.raise_for_status()


def _report_failure(job_id: str, error_message: str):
    response = requests.post(
        f"{BACKEND_INTERNAL_URL}/internal/jobs/{job_id}/fail",
        json={"error": error_message[:2000]},
        timeout=30,
    )
    response.raise_for_status()


def _process_job(job: dict[str, Any]) -> None:
    job_id = job["id"]
    filename = job["filename"]
    book_id = filename.split("_", 1)[0]

    local_path = download_from_minio(filename)
    metadata = get_doc_info(local_path)
    stats, image_records = process_pdf(
        local_path,
        book_id,
        filename,
        return_image_records=True,
    )

    _report_complete(
        job_id,
        metadata=metadata.model_dump(mode="json") if metadata else None,
        images=[record.model_dump(mode="json") for record in image_records],
        stats=stats,
    )


def worker_loop():
    while not _stop_event.is_set():
        try:
            job = _claim_job()
            if job is None:
                _stop_event.wait(POLL_INTERVAL_SECONDS)
                continue

            try:
                _process_job(job)
            except Exception as exc:
                logger.exception("Job %s failed", job.get("id"))
                try:
                    _report_failure(job["id"], str(exc))
                except Exception:
                    logger.exception("Failed to report job failure for %s", job.get("id"))
        except Exception:
            logger.exception("Worker loop failed while polling backend")
            _stop_event.wait(POLL_INTERVAL_SECONDS)


def start_worker_thread() -> None:
    global _worker_started
    if _worker_started or not RUNNER_ENABLED:
        return

    thread = threading.Thread(target=worker_loop, name="pdf-worker-loop", daemon=True)
    thread.start()
    _worker_started = True
    logger.info("Background worker loop started")
