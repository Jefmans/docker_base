from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.document_orm import Document
from app.db.models.project_orm import Project
from app.models.research_tree import ResearchScope


def _display_filename(filename: str) -> str:
    if "_" not in filename:
        return filename
    return filename.split("_", 1)[1]


def resolve_research_scope(
    db: Session,
    *,
    document_id: UUID | str | None = None,
    project_id: UUID | str | None = None,
) -> ResearchScope:
    if document_id and project_id:
        raise ValueError("Choose document_id or project_id, not both")

    if document_id:
        document = db.get(Document, document_id)
        if document is None:
            raise LookupError("Document not found")
        return ResearchScope(
            mode="document",
            document_id=str(document.id),
            project_id=str(document.project_id) if document.project_id else None,
            filenames=[document.filename],
            label=document.title or _display_filename(document.filename),
        )

    if project_id:
        project = db.get(Project, project_id)
        if project is None:
            raise LookupError("Project not found")

        documents = (
            db.query(Document)
            .filter(Document.project_id == project.id)
            .order_by(Document.created_at.asc())
            .all()
        )
        return ResearchScope(
            mode="project",
            project_id=str(project.id),
            filenames=[document.filename for document in documents],
            label=project.name,
        )

    return ResearchScope(mode="all", label="All indexed documents")
