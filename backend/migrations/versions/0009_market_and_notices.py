"""City lease register and reviewed notices (ADR24).

- market_lease: rent signals from D20. Allowlisted fields only; no tenant names, by design.
- context_card.reviewed_by_name: a card is reviewed by a team member through CSV (like description
  tags), since no admin accounts exist yet. An approved card needs a reviewer name or an admin.

Revision ID: 0009_market_and_notices
Revises: 0008_description_tags
Create Date: 2026-11-04
"""

from alembic import op

revision = "0009_market_and_notices"
down_revision = "0008_description_tags"
branch_labels = None
depends_on = None


def _drop_approved_check() -> None:
    op.execute(
        """
        DO $$
        DECLARE c text;
        BEGIN
            SELECT conname INTO c FROM pg_constraint
            WHERE conrelid = 'prostoriq.context_card'::regclass AND contype = 'c'
              AND pg_get_constraintdef(oid) LIKE '%approved_at%';
            EXECUTE format('ALTER TABLE prostoriq.context_card DROP CONSTRAINT %I', c);
        END $$
        """
    )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE prostoriq.market_lease (
            source_version_id uuid NOT NULL REFERENCES prostoriq.source_version,
            contract_key text NOT NULL CHECK (contract_key ~ '^[0-9]{1,12}$'),
            space_id text CHECK (space_id IS NULL OR space_id ~ '^[0-9]{1,12}$'),
            street_key text,
            house_number integer,
            area_m2 numeric NOT NULL CHECK (area_m2 > 0),
            monthly_rent_eur numeric NOT NULL CHECK (monthly_rent_eur > 0),
            signed_date date,
            activity text NOT NULL CHECK (length(activity) BETWEEN 1 AND 300),
            PRIMARY KEY (source_version_id, contract_key)
        )
        """
    )
    op.execute(
        "ALTER TABLE prostoriq.context_card ADD COLUMN reviewed_by_name text "
        "CHECK (reviewed_by_name IS NULL OR length(reviewed_by_name) BETWEEN 2 AND 40)"
    )
    _drop_approved_check()
    op.execute(
        """
        ALTER TABLE prostoriq.context_card ADD CONSTRAINT context_card_approved_check CHECK (
            status <> 'approved' OR (
                approved_at IS NOT NULL
                AND (approved_by IS NOT NULL OR reviewed_by_name IS NOT NULL)
                AND location_kind IS NOT NULL AND location_label IS NOT NULL
                AND (valid_to IS NOT NULL OR review_due_at IS NOT NULL)))
        """
    )
    op.execute("GRANT INSERT, SELECT ON prostoriq.audit_event TO pipeline")


def downgrade() -> None:
    op.execute("ALTER TABLE prostoriq.context_card DROP CONSTRAINT context_card_approved_check")
    op.execute(
        """
        ALTER TABLE prostoriq.context_card ADD CHECK (
            status <> 'approved' OR (approved_at IS NOT NULL AND approved_by IS NOT NULL
                AND location_kind IS NOT NULL AND location_label IS NOT NULL
                AND (valid_to IS NOT NULL OR review_due_at IS NOT NULL)))
        """
    )
    op.execute("ALTER TABLE prostoriq.context_card DROP COLUMN reviewed_by_name")
    op.execute("DROP TABLE IF EXISTS prostoriq.market_lease")
