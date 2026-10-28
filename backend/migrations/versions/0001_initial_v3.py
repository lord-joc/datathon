"""Initial schema from documentation v3 (schema.sql, 31 tables).

Revision ID: 0001_initial_v3
Revises:
Create Date: 2026-10-28
"""

from pathlib import Path

from alembic import op

revision = "0001_initial_v3"
down_revision = None
branch_labels = None
depends_on = None

SQL_FILE = Path(__file__).resolve().parent.parent / "sql" / "0001_initial_v3.sql"


def upgrade() -> None:
    # The SQL file is schema.sql from the technical appendix without BEGIN/COMMIT;
    # Alembic wraps it in its own transaction. exec_driver_sql avoids SQLAlchemy
    # interpreting ":name" sequences inside the DDL as bind parameters.
    op.get_bind().exec_driver_sql(SQL_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS prostoriq CASCADE")
