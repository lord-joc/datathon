"""Team decision (master prompt §2.3): seven business profiles and wider competitor categories.

Replaces the v3 CHECK constraints that allowed only cafe/office and cafe/bar/pub.

Revision ID: 0003_more_profiles
Revises: 0002_roles_and_grants
Create Date: 2026-10-28
"""

from alembic import op

revision = "0003_more_profiles"
down_revision = "0002_roles_and_grants"
branch_labels = None
depends_on = None

PROFILES = "'cafe','office','retail','food_takeaway','personal_care','education','workshop'"
CATEGORIES = "'cafe','bar','pub','fast_food','bakery','hairdresser','beauty'"
PROFILE_TABLES = ("status_assessment", "bundle_status", "criteria_profile")


def upgrade() -> None:
    for table in PROFILE_TABLES:
        op.execute(
            f"ALTER TABLE prostoriq.{table} DROP CONSTRAINT IF EXISTS {table}_profile_code_check"
        )
        op.execute(
            f"ALTER TABLE prostoriq.{table} ADD CONSTRAINT {table}_profile_code_check "
            f"CHECK (profile_code IN ({PROFILES}))"
        )
    op.execute(
        "ALTER TABLE prostoriq.competitor DROP CONSTRAINT IF EXISTS competitor_category_check"
    )
    op.execute(
        "ALTER TABLE prostoriq.competitor ADD CONSTRAINT competitor_category_check "
        f"CHECK (category IN ({CATEGORIES}))"
    )


def downgrade() -> None:
    for table in PROFILE_TABLES:
        op.execute(
            f"ALTER TABLE prostoriq.{table} DROP CONSTRAINT IF EXISTS {table}_profile_code_check"
        )
        op.execute(
            f"ALTER TABLE prostoriq.{table} ADD CONSTRAINT {table}_profile_code_check "
            "CHECK (profile_code IN ('cafe','office'))"
        )
    op.execute(
        "ALTER TABLE prostoriq.competitor DROP CONSTRAINT IF EXISTS competitor_category_check"
    )
    op.execute(
        "ALTER TABLE prostoriq.competitor ADD CONSTRAINT competitor_category_check "
        "CHECK (category IN ('cafe','bar','pub'))"
    )
