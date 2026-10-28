"""Team decision (ADR16): schools/kindergartens layer and 'schools' criterion.

- spatial_feature.category gains 'school' (D17 vrtići, D18 osnovne škole).
- spatial_metric.criterion gains 'schools'.
- Transit stays one category; tram vs bus is kept in spatial_feature.properties.mode.
- B-tree index to filter features by version and category (geography GiST already exists).

Revision ID: 0004_schools_and_transit_mode
Revises: 0003_more_profiles
Create Date: 2026-10-28
"""

from alembic import op

revision = "0004_schools_and_transit_mode"
down_revision = "0003_more_profiles"
branch_labels = None
depends_on = None

CATEGORIES_NEW = "'transit','university','culture','parking','school'"
CATEGORIES_OLD = "'transit','university','culture','parking'"
CRITERIA_NEW = (
    "'transit','universities','culture','parking','schools','area','street','competition','cost'"
)
CRITERIA_OLD = "'transit','universities','culture','parking','area','street','competition','cost'"


def _replace_checks(categories: str, criteria: str) -> None:
    op.execute(
        "ALTER TABLE prostoriq.spatial_feature DROP CONSTRAINT IF EXISTS spatial_feature_category_check"
    )
    op.execute(
        "ALTER TABLE prostoriq.spatial_feature ADD CONSTRAINT spatial_feature_category_check "
        f"CHECK (category IN ({categories}))"
    )
    op.execute(
        "ALTER TABLE prostoriq.spatial_metric DROP CONSTRAINT IF EXISTS spatial_metric_criterion_check"
    )
    op.execute(
        "ALTER TABLE prostoriq.spatial_metric ADD CONSTRAINT spatial_metric_criterion_check "
        f"CHECK (criterion IN ({criteria}))"
    )


def upgrade() -> None:
    _replace_checks(CATEGORIES_NEW, CRITERIA_NEW)
    op.execute(
        "CREATE INDEX IF NOT EXISTS spatial_feature_version_category_idx "
        "ON prostoriq.spatial_feature (source_version_id, category)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS prostoriq.spatial_feature_version_category_idx")
    _replace_checks(CATEGORIES_OLD, CRITERIA_OLD)
