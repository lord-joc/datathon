"""OSM address points (D19) for geocoding, and an index cleanup.

- osm_address: one row per OSM object with addr:housenumber inside the Zagreb extract.
  Keys are normalised in Python (app/gis/addresses.py) and stored for indexed lookup.
- Drops spatial_feature_version_category_idx from 0004: schema v3 already has the same
  index as spatial_feature_category_idx (category, source_version_id).

Revision ID: 0006_osm_addresses
Revises: 0005_pipeline_version_checks
Create Date: 2026-10-28
"""

from alembic import op

revision = "0006_osm_addresses"
down_revision = "0005_pipeline_version_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS prostoriq.spatial_feature_version_category_idx")
    op.execute(
        """
        CREATE TABLE prostoriq.osm_address (
            source_version_id uuid NOT NULL REFERENCES prostoriq.source_version,
            osm_type text NOT NULL CHECK (osm_type IN ('node', 'way')),
            osm_id bigint NOT NULL CHECK (osm_id > 0),
            street text NOT NULL,
            housenumber text NOT NULL,
            street_key text NOT NULL,
            number integer NOT NULL CHECK (number > 0),
            letter text NOT NULL DEFAULT '',
            geom geometry(Point, 4326) NOT NULL,
            PRIMARY KEY (source_version_id, osm_type, osm_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX osm_address_lookup_idx "
        "ON prostoriq.osm_address (source_version_id, street_key, number)"
    )
    # Default privileges from 0002 already grant SELECT/INSERT; repeat explicitly for clarity.
    op.execute("GRANT SELECT ON prostoriq.osm_address TO app_read, pipeline")
    op.execute("GRANT INSERT ON prostoriq.osm_address TO pipeline")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS prostoriq.osm_address")
    op.execute(
        "CREATE INDEX IF NOT EXISTS spatial_feature_version_category_idx "
        "ON prostoriq.spatial_feature (source_version_id, category)"
    )
