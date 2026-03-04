from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.project_orm import Project


def normalize_project_name(name: str | None) -> str:
    return (name or "").strip()


def get_project_by_name(db: Session, name: str) -> Project | None:
    normalized = normalize_project_name(name)
    if not normalized:
        return None
    return (
        db.query(Project)
        .filter(func.lower(Project.name) == normalized.lower())
        .one_or_none()
    )


def get_or_create_project(db: Session, name: str) -> tuple[Project, bool]:
    normalized = normalize_project_name(name)
    if not normalized:
        raise ValueError("Project name cannot be empty")

    existing = get_project_by_name(db, normalized)
    if existing is not None:
        return existing, False

    project = Project(name=normalized)
    db.add(project)
    db.flush()
    return project, True
