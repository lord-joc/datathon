"""Import review decisions and ranking reads.

- pipeline may change only source_version.quality_status (awaiting_review -> valid/rejected)
  through 'source-review'; every other column stays insert-only.
- ranking_item.reason: why a stored item has no score (no_common_criteria, partial_coverage,
  not_applicable), as the API contract returns it; v3 had only the reasons list.
- ranking_run(dataset_bundle_id, created_at) index for the public read path.

Revision ID: 0007_review_and_ranking
Revises: 0006_osm_addresses
Create Date: 2026-10-30
"""

from alembic import op

revision = "0007_review_and_ranking"
down_revision = "0006_osm_addresses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT UPDATE (quality_status) ON prostoriq.source_version TO pipeline")
    op.execute("ALTER TABLE prostoriq.ranking_item ADD COLUMN reason text")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ranking_run_bundle_idx "
        "ON prostoriq.ranking_run (dataset_bundle_id, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS prostoriq.ranking_run_bundle_idx")
    op.execute("ALTER TABLE prostoriq.ranking_item DROP COLUMN IF EXISTS reason")
    op.execute("REVOKE UPDATE (quality_status) ON prostoriq.source_version FROM pipeline")
