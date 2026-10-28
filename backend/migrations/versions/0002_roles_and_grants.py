"""Least-privilege group roles and grants (NF02, NF03, doc. chapter 15).

Group roles (NOLOGIN) are created here. Login users are created once by
db/init/10-roles.sh from environment variables and made members of these roles.

- app_read          public API: SELECT on everything it serves
- app_ranking_write public API: INSERT on ranking snapshots only
- pipeline          import/GIS/AI scripts: SELECT/INSERT/UPDATE on working tables

No role used by the API can UPDATE or DELETE historical tables.

Revision ID: 0002_roles_and_grants
Revises: 0001_initial_v3
Create Date: 2026-10-28
"""

from alembic import op

revision = "0002_roles_and_grants"
down_revision = "0001_initial_v3"
branch_labels = None
depends_on = None

ROLES = ("app_read", "app_ranking_write", "pipeline")


def upgrade() -> None:
    for role in ROLES:
        op.execute(
            f"""
            DO $$
            BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN;
              END IF;
            END
            $$;
            """
        )

    op.execute("GRANT USAGE ON SCHEMA prostoriq TO app_read, app_ranking_write, pipeline")

    # Public API: read everything except admin secrets.
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA prostoriq TO app_read")
    op.execute("REVOKE ALL ON prostoriq.admin_user, prostoriq.admin_session FROM app_read")

    # Public API: write only immutable ranking snapshots.
    op.execute("GRANT INSERT ON prostoriq.ranking_run, prostoriq.ranking_item TO app_ranking_write")
    op.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA prostoriq TO app_ranking_write, pipeline")

    # Pipeline: working tables. Historical revisions are insert-only by convention and grant.
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA prostoriq TO pipeline")
    op.execute(
        """
        GRANT INSERT ON ALL TABLES IN SCHEMA prostoriq TO pipeline;
        REVOKE INSERT ON prostoriq.ranking_run, prostoriq.ranking_item,
                         prostoriq.admin_user, prostoriq.admin_session FROM pipeline;
        GRANT UPDATE ON prostoriq.import_job, prostoriq.source, prostoriq.dataset_bundle,
                        prostoriq.active_dataset, prostoriq.context_card,
                        prostoriq.coverage_review TO pipeline;
        """
    )

    # Tables created by later migrations (run by the same owner role) get read access.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA prostoriq GRANT SELECT ON TABLES TO app_read, pipeline"
    )
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA prostoriq GRANT INSERT ON TABLES TO pipeline")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA prostoriq GRANT USAGE ON SEQUENCES "
        "TO app_ranking_write, pipeline"
    )


def downgrade() -> None:
    for role in ROLES:
        op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA prostoriq FROM {role}")
        op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA prostoriq FROM {role}")
        op.execute(f"REVOKE USAGE ON SCHEMA prostoriq FROM {role}")
