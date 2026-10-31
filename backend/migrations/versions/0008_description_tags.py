"""Tags from the D01 "Opis strukture" field, with a human review (ADR21).

- description_tag: one proposed tag per space revision, with the words from the official text
  as evidence and the hash of the rules that produced it. Starts as pending_review.
- The pipeline role may change only the review columns (status, reviewed_at, reviewer,
  review_note); evidence and the tag itself are insert-only.
- Public reads show approved tags only (app/db/public.py), never the evidence text.

Revision ID: 0008_description_tags
Revises: 0007_review_and_ranking
Create Date: 2026-10-30
"""

from alembic import op

revision = "0008_description_tags"
down_revision = "0007_review_and_ranking"
branch_labels = None
depends_on = None

# Frozen copy of app.ai.tags.TAG_LABELS at this revision; a new tag needs a new migration.
_TAGS = (
    "'ground_floor', 'basement', 'upper_floor', 'attic', 'gallery', 'street_facing', "
    "'courtyard', 'standalone', 'underpass', 'barrack', 'toilet', 'storage', 'kitchen', "
    "'shop_window', 'terrace', 'unfinished', 'poor_condition', 'room_count'"
)


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE prostoriq.description_tag (
            description_tag_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            space_revision_id uuid NOT NULL REFERENCES prostoriq.space_revision,
            space_id text NOT NULL REFERENCES prostoriq.space,
            tag text NOT NULL CHECK (tag IN ({_TAGS})),
            value integer CHECK (value IS NULL OR value BETWEEN 1 AND 99),
            method text NOT NULL CHECK (method IN ('rule', 'model')),
            evidence text NOT NULL CHECK (length(evidence) BETWEEN 1 AND 500),
            rules_sha256 char(64) NOT NULL CHECK (rules_sha256 ~ '^[0-9a-f]{{64}}$'),
            status text NOT NULL DEFAULT 'pending_review'
                CHECK (status IN ('pending_review', 'approved', 'rejected')),
            created_at timestamptz NOT NULL DEFAULT now(),
            reviewed_at timestamptz,
            reviewer text CHECK (reviewer IS NULL OR length(reviewer) BETWEEN 2 AND 40),
            review_note text CHECK (review_note IS NULL OR length(review_note) <= 500),
            CHECK (status = 'pending_review' OR (reviewed_at IS NOT NULL AND reviewer IS NOT NULL)),
            CHECK ((tag = 'room_count') = (value IS NOT NULL)),
            UNIQUE (space_revision_id, tag, rules_sha256)
        )
        """
    )
    op.execute(
        "CREATE INDEX description_tag_space_idx ON prostoriq.description_tag (space_id, status)"
    )
    op.execute("GRANT SELECT ON prostoriq.description_tag TO app_read, pipeline")
    op.execute("GRANT INSERT ON prostoriq.description_tag TO pipeline")
    op.execute(
        "GRANT UPDATE (status, reviewed_at, reviewer, review_note) "
        "ON prostoriq.description_tag TO pipeline"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS prostoriq.description_tag")
