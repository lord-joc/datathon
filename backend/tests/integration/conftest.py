"""Fixtures shared by integration tests (PostgreSQL + PostGIS via MIGRATION_DATABASE_URL).

Never point MIGRATION_DATABASE_URL at a database with real data: the fixtures TRUNCATE.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from app.cli import main as cli_main
from app.pipeline.importer import Importer, sync_sources
from tests import fixtures as fx
from tests.integration.support import (
    PARKING_NEAR_4010,
    PASSWORD,
    STOP_NEAR_4763,
    URL,
    import_ok,
    write_file,
)


@pytest.fixture(scope="module")
def owner() -> Engine:
    assert URL
    assert cli_main(["migrate"]) == 0
    engine = create_engine(URL)
    with engine.begin() as conn:
        conn.execute(
            text(
                "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='test_pipeline') "
                f"THEN CREATE ROLE test_pipeline LOGIN PASSWORD '{PASSWORD}'; END IF; END $$"
            )
        )
        conn.execute(text("GRANT pipeline TO test_pipeline"))
    return engine


@pytest.fixture
def pipeline(owner: Engine) -> Iterator[Engine]:
    with owner.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE prostoriq.active_dataset, prostoriq.spatial_metric, "
                "prostoriq.bundle_space, prostoriq.bundle_source, prostoriq.dataset_bundle, "
                "prostoriq.geo_evidence, prostoriq.competitor, prostoriq.osm_address, "
                "prostoriq.district, prostoriq.spatial_feature, prostoriq.space_revision, "
                "prostoriq.space, prostoriq.source_record, prostoriq.source_version, "
                "prostoriq.import_error, prostoriq.import_job CASCADE"
            )
        )
    assert URL
    engine = create_engine(make_url(URL).set(username="test_pipeline", password=PASSWORD))
    with engine.begin() as conn:
        sync_sources(conn, fx.registry())
    yield engine
    engine.dispose()


@pytest.fixture
def imported(pipeline: Engine, tmp_path: Path) -> Engine:
    imp = Importer(pipeline, fx.registry(), tmp_path / "raw")
    import_ok(imp, "D01", write_file(tmp_path, "d01.csv", fx.spaces_csv()))
    d02 = fx.spaces_csv(fx.D02_HEADER, fx.D02_ROWS, preamble_rows=2)
    import_ok(imp, "D02", write_file(tmp_path, "d02.csv", d02))
    stops = fx.geojson_points(
        [fx.point(1, STOP_NEAR_4763[0], STOP_NEAR_4763[1], **{"Naziv_stajališta": "Jurišićeva"})]
    )
    import_ok(imp, "D03", write_file(tmp_path, "d03.geojson", stops))
    unis = fx.geojson_points([fx.point(1, 15.9780, 45.8050), fx.point(2, 15.90, 45.78)])
    import_ok(imp, "D04", write_file(tmp_path, "d04.geojson", unis))
    import_ok(
        imp,
        "D05",
        write_file(tmp_path, "d05.geojson", fx.geojson_points([fx.point(1, 15.977, 45.806)])),
    )
    parking = fx.geojson_points([fx.point(1, *PARKING_NEAR_4010)])
    import_ok(imp, "D06", write_file(tmp_path, "d06.geojson", parking))
    import_ok(imp, "D07", write_file(tmp_path, "d07.zip", fx.districts_zip()))
    pbf = fx.osm_pbf(tmp_path / "croatia.osm.pbf")
    import_ok(imp, "D19", pbf)
    import_ok(imp, "D08", pbf)
    return pipeline
