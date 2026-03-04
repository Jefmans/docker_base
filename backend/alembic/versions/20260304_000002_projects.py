"""add projects and document project assignment

Revision ID: 20260304_000002
Revises: 20260303_000001
Create Date: 2026-03-04 00:00:02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260304_000002"
down_revision: Union[str, Sequence[str], None] = "20260303_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    columns = sa.inspect(bind).get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def _has_index(bind, table_name: str, index_name: str) -> bool:
    indexes = sa.inspect(bind).get_indexes(table_name)
    return any(index["name"] == index_name for index in indexes)


def _has_foreign_key(bind, table_name: str, fk_name: str) -> bool:
    foreign_keys = sa.inspect(bind).get_foreign_keys(table_name)
    return any(foreign_key["name"] == fk_name for foreign_key in foreign_keys)


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "projects"):
        op.create_table(
            "projects",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_index(bind, "projects", "ix_projects_name"):
        op.create_index("ix_projects_name", "projects", ["name"], unique=True)

    if _has_table(bind, "documents") and not _has_column(bind, "documents", "project_id"):
        op.add_column("documents", sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True))

    if _has_table(bind, "documents") and not _has_index(bind, "documents", "ix_documents_project_id"):
        op.create_index("ix_documents_project_id", "documents", ["project_id"], unique=False)

    if (
        _has_table(bind, "documents")
        and _has_table(bind, "projects")
        and not _has_foreign_key(bind, "documents", "fk_documents_project_id_projects")
    ):
        op.create_foreign_key(
            "fk_documents_project_id_projects",
            "documents",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "documents") and _has_foreign_key(bind, "documents", "fk_documents_project_id_projects"):
        op.drop_constraint("fk_documents_project_id_projects", "documents", type_="foreignkey")

    if _has_table(bind, "documents") and _has_index(bind, "documents", "ix_documents_project_id"):
        op.drop_index("ix_documents_project_id", table_name="documents")

    if _has_table(bind, "documents") and _has_column(bind, "documents", "project_id"):
        op.drop_column("documents", "project_id")

    if _has_table(bind, "projects") and _has_index(bind, "projects", "ix_projects_name"):
        op.drop_index("ix_projects_name", table_name="projects")

    if _has_table(bind, "projects"):
        op.drop_table("projects")
