"""Pipeline may record a new check on an existing source version, nothing else.

Column-level grant: last_checked_at (unchanged re-download, FZ02) and quality_status
(review decision, FZ18). Content columns of source_version stay immutable.

Revision ID: 0005_pipeline_version_checks
Revises: 0004_schools_and_transit_mode
Create Date: 2026-10-28
"""

from alembic import op

revision = "0005_pipeline_version_checks"
down_revision = "0004_schools_and_transit_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "GRANT UPDATE (last_checked_at, quality_status) ON prostoriq.source_version TO pipeline"
    )


def downgrade() -> None:
    op.execute(
        "REVOKE UPDATE (last_checked_at, quality_status) ON prostoriq.source_version FROM pipeline"
    )
