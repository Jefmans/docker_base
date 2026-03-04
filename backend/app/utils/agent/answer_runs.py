from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.db import Session as SessionModel, SessionLocal


def _iso_now() -> str:
    return datetime.utcnow().isoformat()


def create_answer_run(
    session_id: str,
    *,
    query: str,
    scope: dict[str, Any],
) -> None:
    with SessionLocal() as db:
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        payload = dict(session.tree or {}) if session else {}
        payload["scope"] = scope
        payload["answer_run"] = {
            "status": "pending",
            "stage": "Queued",
            "failed_stage": None,
            "requested_at": _iso_now(),
            "started_at": None,
            "finished_at": None,
            "updated_at": _iso_now(),
            "error": None,
            "result": None,
        }

        if session is None:
            db.add(SessionModel(id=session_id, query=query, tree=payload))
        else:
            session.query = query
            session.tree = payload
        db.commit()


def update_answer_run(
    session_id: str,
    *,
    status: str | None = None,
    stage: str | None = None,
    failed_stage: str | None = None,
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    with SessionLocal() as db:
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if session is None:
            return

        payload = dict(session.tree or {})
        run = dict(payload.get("answer_run") or {})
        if status is not None:
            run["status"] = status
        if stage is not None:
            run["stage"] = stage
        if failed_stage is not None:
            run["failed_stage"] = failed_stage
        if status == "running":
            run["started_at"] = run.get("started_at") or _iso_now()
            run["error"] = None
            run["failed_stage"] = None
        if status in {"completed", "failed"}:
            run["finished_at"] = _iso_now()
        if error is not None:
            run["error"] = error
        if result is not None:
            run["result"] = result
        run["updated_at"] = _iso_now()

        payload["answer_run"] = run
        session.tree = payload
        db.commit()


def get_answer_run(session_id: str) -> dict[str, Any] | None:
    with SessionLocal() as db:
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if session is None:
            return None

        payload = dict(session.tree or {})
        run = dict(payload.get("answer_run") or {})
        if not run:
            return None

        return {
            "session_id": str(session.id),
            "query": session.query,
            "scope": dict(payload.get("scope") or {}),
            **run,
        }
