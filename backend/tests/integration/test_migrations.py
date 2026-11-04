"""Runs real migrations against PostgreSQL + PostGIS.

Requires MIGRATION_DATABASE_URL pointing at an EMPTY database (owner role).
Skipped when the variable is not set.
"""

import os

import pytest
from sqlalchemy import create_engine, text

from app.cli import main as cli_main

URL = os.environ.get("MIGRATION_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not URL, reason="MIGRATION_DATABASE_URL not set"),
]


def test_migrate_creates_schema_roles_and_profiles() -> None:
    assert cli_main(["migrate"]) == 0
    assert URL
    engine = create_engine(URL)
    with engine.connect() as conn:
        tables = conn.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema='prostoriq'")
        ).scalar_one()
        roles = set(
            conn.execute(
                text(
                    "SELECT rolname FROM pg_roles "
                    "WHERE rolname IN ('app_read','app_ranking_write','pipeline')"
                )
            ).scalars()
        )
        api_can_update_history = conn.execute(
            text("SELECT has_table_privilege('app_read', 'prostoriq.space_revision', 'UPDATE')")
        ).scalar_one()
        api_reads_admin = conn.execute(
            text("SELECT has_table_privilege('app_read', 'prostoriq.admin_user', 'SELECT')")
        ).scalar_one()
        profile_check = conn.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'criteria_profile_profile_code_check'"
            )
        ).scalar_one()
    assert (
        tables == 34
    )  # 31 in 0001 + osm_address (0006), description_tag (0008), market_lease (0009)
    assert roles == {"app_read", "app_ranking_write", "pipeline"}
    assert api_can_update_history is False
    assert api_reads_admin is False
    assert "food_takeaway" in profile_check


def test_migrate_is_idempotent() -> None:
    assert cli_main(["migrate"]) == 0
