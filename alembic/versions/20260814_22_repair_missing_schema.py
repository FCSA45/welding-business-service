"""Create tables skipped by databases carrying an incorrect legacy stamp.

Revision ID: 20260814_22
Revises: 20260814_21
"""

from collections.abc import Sequence

from alembic import op

from app.db.base import Base
import app.db.models  # noqa: F401 - registers every mapped table


revision: str = "20260814_22"
down_revision: str | Sequence[str] | None = "20260814_21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # Repair-only migration: never remove pre-existing business tables.
    pass
