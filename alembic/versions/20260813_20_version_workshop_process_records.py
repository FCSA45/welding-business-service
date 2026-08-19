"""Keep immutable versions of workshop process records."""

from collections.abc import Sequence
import hashlib
import json
import sqlalchemy as sa
from alembic import op

revision: str = "20260813_20"
down_revision: str | Sequence[str] | None = "20260813_19"
branch_labels = None
depends_on = None


def _hash_existing(row) -> str:
    payload = {key: value for key, value in row.items() if key not in {"id", "created_at", "updated_at"}}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.add_column("workshop_process_records", sa.Column("version", sa.Integer(), nullable=True))
    op.add_column("workshop_process_records", sa.Column("content_hash", sa.String(64), nullable=True))
    op.add_column("workshop_process_records", sa.Column("is_current", sa.Boolean(), nullable=True))
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT * FROM workshop_process_records")).mappings()
    for row in rows:
        connection.execute(
            sa.text("UPDATE workshop_process_records SET version=1, content_hash=:hash, is_current=true WHERE id=:id"),
            {"hash": _hash_existing(row), "id": row["id"]},
        )
    op.alter_column("workshop_process_records", "version", nullable=False, server_default="1")
    op.alter_column("workshop_process_records", "content_hash", nullable=False)
    op.alter_column("workshop_process_records", "is_current", nullable=False, server_default=sa.true())
    op.drop_constraint("uq_workshop_process_source_record", "workshop_process_records", type_="unique")
    op.create_unique_constraint("uq_workshop_process_source_version", "workshop_process_records", ["source_type", "source_record_id", "version"])
    op.create_unique_constraint("uq_workshop_process_content_hash", "workshop_process_records", ["content_hash"])
    op.create_check_constraint("ck_workshop_process_version_positive", "workshop_process_records", "version >= 1")
    op.create_index("ix_workshop_process_current", "workshop_process_records", ["source_type", "source_record_id", "is_current"])


def downgrade() -> None:
    connection = op.get_bind()
    stale = connection.execute(sa.text("SELECT COUNT(*) FROM workshop_process_records WHERE is_current = false")).scalar_one()
    if stale:
        raise RuntimeError("Rollback blocked: historical workshop process versions would be lost")
    op.drop_index("ix_workshop_process_current", table_name="workshop_process_records")
    op.drop_constraint("ck_workshop_process_version_positive", "workshop_process_records", type_="check")
    op.drop_constraint("uq_workshop_process_content_hash", "workshop_process_records", type_="unique")
    op.drop_constraint("uq_workshop_process_source_version", "workshop_process_records", type_="unique")
    op.create_unique_constraint("uq_workshop_process_source_record", "workshop_process_records", ["source_type", "source_record_id"])
    op.drop_column("workshop_process_records", "is_current")
    op.drop_column("workshop_process_records", "content_hash")
    op.drop_column("workshop_process_records", "version")
