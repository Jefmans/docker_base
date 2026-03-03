"""initial baseline

Revision ID: 20260303_000001
Revises:
Create Date: 2026-03-03 00:00:01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260303_000001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _has_index(bind, table_name: str, index_name: str) -> bool:
    indexes = sa.inspect(bind).get_indexes(table_name)
    return any(index["name"] == index_name for index in indexes)


def _has_unique_constraint(bind, table_name: str, constraint_name: str) -> bool:
    constraints = sa.inspect(bind).get_unique_constraints(table_name)
    return any(constraint["name"] == constraint_name for constraint in constraints)


def upgrade() -> None:
    bind = op.get_bind()

    question_status_enum = postgresql.ENUM(
        "proposed",
        "assigned",
        "consumed",
        name="questionstatus",
        create_type=False,
    )
    processing_job_status_enum = postgresql.ENUM(
        "pending",
        "running",
        "completed",
        "failed",
        name="processingjobstatus",
        create_type=False,
    )

    question_status_enum.create(bind, checkfirst=True)
    processing_job_status_enum.create(bind, checkfirst=True)

    if not _has_table(bind, "sessions"):
        op.create_table(
            "sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("query", sa.String(), nullable=False),
            sa.Column("tree", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_table(bind, "documents"):
        op.create_table(
            "documents",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("filename", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("year", sa.Integer(), nullable=True),
            sa.Column("type", sa.String(), nullable=True),
            sa.Column("topic", sa.String(), nullable=True),
            sa.Column("authors", postgresql.ARRAY(sa.String()), nullable=True),
            sa.Column("isbn", sa.String(), nullable=True),
            sa.Column("doi", sa.String(), nullable=True),
            sa.Column("publisher", sa.String(), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_index(bind, "documents", "ix_documents_filename"):
        op.create_index("ix_documents_filename", "documents", ["filename"], unique=True)

    if not _has_table(bind, "images"):
        op.create_table(
            "images",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("book_id", sa.String(), nullable=True),
            sa.Column("source_pdf", sa.String(), nullable=True),
            sa.Column("page_number", sa.Integer(), nullable=True),
            sa.Column("xref", sa.Integer(), nullable=True),
            sa.Column("filename", sa.String(), nullable=True),
            sa.Column("caption", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_index(bind, "images", "ix_images_id"):
        op.create_index("ix_images_id", "images", ["id"], unique=False)
    if not _has_index(bind, "images", "ix_images_book_id"):
        op.create_index("ix_images_book_id", "images", ["book_id"], unique=False)
    if not _has_index(bind, "images", "ix_images_filename"):
        op.create_index("ix_images_filename", "images", ["filename"], unique=True)

    if not _has_table(bind, "research_nodes"):
        op.create_table(
            "research_nodes",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("goals", sa.Text(), nullable=True),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("conclusion", sa.Text(), nullable=True),
            sa.Column("rank", sa.Integer(), nullable=False),
            sa.Column("level", sa.Integer(), nullable=False),
            sa.Column("is_final", sa.Boolean(), nullable=True),
            sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.ForeignKeyConstraint(["parent_id"], ["research_nodes.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_index(bind, "research_nodes", "ix_research_nodes_session_id"):
        op.create_index("ix_research_nodes_session_id", "research_nodes", ["session_id"], unique=False)

    if not _has_table(bind, "questions"):
        op.create_table(
            "questions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("text", sa.String(), nullable=False),
            sa.Column("source", sa.String(), nullable=False),
            sa.Column("status", question_status_enum, nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_index(bind, "questions", "ix_questions_text"):
        op.create_index("ix_questions_text", "questions", ["text"], unique=True)

    if not _has_table(bind, "chunks"):
        op.create_table(
            "chunks",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("page", sa.Integer(), nullable=True),
            sa.Column("source", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_table(bind, "node_questions"):
        op.create_table(
            "node_questions",
            sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.ForeignKeyConstraint(["node_id"], ["research_nodes.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("node_id", "question_id"),
            sa.UniqueConstraint("node_id", "question_id", name="uq_node_question"),
        )

    if not _has_table(bind, "node_chunks"):
        op.create_table(
            "node_chunks",
            sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("chunk_id", sa.String(), nullable=False),
            sa.ForeignKeyConstraint(["node_id"], ["research_nodes.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("node_id", "chunk_id"),
            sa.UniqueConstraint("node_id", "chunk_id", name="uq_node_chunk"),
        )

    if not _has_table(bind, "processing_jobs"):
        op.create_table(
            "processing_jobs",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("job_type", sa.String(), nullable=False),
            sa.Column("status", processing_job_status_enum, nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False),
            sa.Column("worker_name", sa.String(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
            sa.Column("started_at", sa.TIMESTAMP(), nullable=True),
            sa.Column("finished_at", sa.TIMESTAMP(), nullable=True),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_index(bind, "processing_jobs", "ix_processing_jobs_document_id"):
        op.create_index("ix_processing_jobs_document_id", "processing_jobs", ["document_id"], unique=False)
    if not _has_index(bind, "processing_jobs", "ix_processing_jobs_status"):
        op.create_index("ix_processing_jobs_status", "processing_jobs", ["status"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "processing_jobs"):
        op.drop_index("ix_processing_jobs_status", table_name="processing_jobs")
        op.drop_index("ix_processing_jobs_document_id", table_name="processing_jobs")
        op.drop_table("processing_jobs")

    if _has_table(bind, "node_chunks"):
        op.drop_table("node_chunks")

    if _has_table(bind, "node_questions"):
        op.drop_table("node_questions")

    if _has_table(bind, "chunks"):
        op.drop_table("chunks")

    if _has_table(bind, "questions"):
        op.drop_index("ix_questions_text", table_name="questions")
        op.drop_table("questions")

    if _has_table(bind, "research_nodes"):
        op.drop_index("ix_research_nodes_session_id", table_name="research_nodes")
        op.drop_table("research_nodes")

    if _has_table(bind, "images"):
        op.drop_index("ix_images_filename", table_name="images")
        op.drop_index("ix_images_book_id", table_name="images")
        op.drop_index("ix_images_id", table_name="images")
        op.drop_table("images")

    if _has_table(bind, "documents"):
        op.drop_index("ix_documents_filename", table_name="documents")
        op.drop_table("documents")

    if _has_table(bind, "sessions"):
        op.drop_table("sessions")

    processing_job_status_enum = postgresql.ENUM(name="processingjobstatus")
    question_status_enum = postgresql.ENUM(name="questionstatus")
    processing_job_status_enum.drop(bind, checkfirst=True)
    question_status_enum.drop(bind, checkfirst=True)
