"""Move operation daily reports into the canonical daily_reports table."""
from collections.abc import Sequence

from alembic import op


revision: str = "20260810_08"
down_revision: str | Sequence[str] | None = "20260810_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO daily_reports (
            report_date,
            employee_open_id,
            employee_name,
            completed_work,
            completed_count,
            next_plan,
            issues,
            submitted_at,
            updated_at,
            version,
            status,
            source,
            source_message_id
        )
        SELECT
            report_date,
            'operator:' || operator_name,
            operator_name,
            COALESCE(NULLIF(completed_work, ''), NULLIF(project_name, ''), '运营日报'),
            published_count,
            next_plan,
            issues,
            created_at,
            updated_at,
            1,
            'submitted',
            source,
            'operation-daily-' || id::text
        FROM operation_daily_reports
        ON CONFLICT (employee_open_id, report_date) DO UPDATE SET
            employee_name = EXCLUDED.employee_name,
            completed_work = EXCLUDED.completed_work,
            completed_count = EXCLUDED.completed_count,
            next_plan = EXCLUDED.next_plan,
            issues = EXCLUDED.issues,
            updated_at = EXCLUDED.updated_at,
            source = EXCLUDED.source
        """
    )
    op.drop_index("ix_operation_daily_reports_operator_name", table_name="operation_daily_reports")
    op.drop_index("ix_operation_daily_reports_report_date", table_name="operation_daily_reports")
    op.drop_table("operation_daily_reports")


def downgrade() -> None:
    raise RuntimeError("The operation_daily_reports table was intentionally removed; restore from backup to downgrade.")
