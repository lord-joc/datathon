"""End-to-end import on a real PostgreSQL + PostGIS, executed as the restricted pipeline role.

Requires MIGRATION_DATABASE_URL (owner). The test creates a temporary login role that is a
member of the 'pipeline' group role, so missing grants show up here, not in production.
"""

import json
import os
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from app.adapters.http import SafeFetcher
from app.cli import main as cli_main
from app.pipeline.importer import ImportBusyError, Importer, sync_sources
from tests import fixtures as fx

URL = os.environ.get("MIGRATION_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not URL, reason="MIGRATION_DATABASE_URL not set"),
]
PIPELINE_TEST_PASSWORD = "pipeline_test_only"


@pytest.fixture(scope="module")
def owner() -> Engine:
    assert URL
    assert cli_main(["migrate"]) == 0
    engine = create_engine(URL)
    with engine.begin() as conn:
        conn.execute(
            text(
                "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='test_pipeline') "
                f"THEN CREATE ROLE test_pipeline LOGIN PASSWORD '{PIPELINE_TEST_PASSWORD}'; END IF; END $$"
            )
        )
        conn.execute(text("GRANT pipeline TO test_pipeline"))
    return engine


@pytest.fixture
def pipeline(owner: Engine) -> Iterator[Engine]:
    with owner.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE prostoriq.district, prostoriq.spatial_feature, prostoriq.space_revision, "
                "prostoriq.space, prostoriq.source_record, prostoriq.source_version, "
                "prostoriq.import_error, prostoriq.import_job CASCADE"
            )
        )
    assert URL
    url = make_url(URL).set(username="test_pipeline", password=PIPELINE_TEST_PASSWORD)
    engine = create_engine(url)
    reg = fx.registry()
    with engine.begin() as conn:
        sync_sources(conn, reg)
    yield engine
    engine.dispose()


@pytest.fixture
def importer(pipeline: Engine, tmp_path: Path) -> Importer:
    return Importer(pipeline, fx.registry(), tmp_path / "raw")


def write(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def scalar(engine: Engine, sql: str, **params: object) -> object:
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def test_d01_import_creates_spaces_and_raw_file(
    importer: Importer, pipeline: Engine, tmp_path: Path
) -> None:
    file = write(tmp_path, "d01.csv", fx.spaces_csv())
    outcome = importer.run("D01", idempotency_key="k1", local_file=file)
    assert outcome.status == "succeeded", outcome
    assert outcome.record_count == 3
    assert scalar(pipeline, "SELECT count(*) FROM prostoriq.space") == 3
    assert scalar(
        pipeline, "SELECT area_m2 FROM prostoriq.space_revision WHERE space_id='10422'"
    ) == Decimal("87.96")
    assert (
        scalar(pipeline, "SELECT address FROM prostoriq.space_revision WHERE space_id='4763'")
        == "TRG ANTE STARČEVIĆA 0007"
    )
    raw_key = scalar(pipeline, "SELECT raw_storage_key FROM prostoriq.source_version")
    assert (tmp_path / "raw" / str(raw_key)).read_bytes() == file.read_bytes()


def test_same_key_returns_same_job(importer: Importer, tmp_path: Path) -> None:
    file = write(tmp_path, "d01.csv", fx.spaces_csv())
    first = importer.run("D01", idempotency_key="same", local_file=file)
    second = importer.run("D01", idempotency_key="same", local_file=file)
    assert second.job_id == first.job_id
    assert second.reused_job


def test_same_content_new_key_is_unchanged_no_duplicates(
    importer: Importer, pipeline: Engine, tmp_path: Path
) -> None:
    file = write(tmp_path, "d01.csv", fx.spaces_csv())
    importer.run("D01", idempotency_key="a", local_file=file)
    again = importer.run("D01", idempotency_key="b", local_file=file)
    assert again.unchanged
    assert scalar(pipeline, "SELECT count(*) FROM prostoriq.source_version") == 1
    assert scalar(pipeline, "SELECT count(*) FROM prostoriq.space_revision") == 3


def test_large_count_change_waits_for_review(importer: Importer, tmp_path: Path) -> None:
    importer.run("D01", idempotency_key="a", local_file=write(tmp_path, "a.csv", fx.spaces_csv()))
    smaller = fx.spaces_csv(rows=fx.D01_ROWS[:1])
    outcome = importer.run("D01", idempotency_key="b", local_file=write(tmp_path, "b.csv", smaller))
    assert outcome.status == "awaiting_review"
    assert any("20 %" in w for w in outcome.warnings)


def test_bad_header_fails_and_keeps_previous_version(
    importer: Importer, pipeline: Engine, tmp_path: Path
) -> None:
    importer.run(
        "D01", idempotency_key="good", local_file=write(tmp_path, "g.csv", fx.spaces_csv())
    )
    bad = fx.spaces_csv(["NEPOZNATO", "POLJE"], [["1", "x"]])
    outcome = importer.run("D01", idempotency_key="bad", local_file=write(tmp_path, "b.csv", bad))
    assert outcome.status == "failed"
    assert outcome.error_code == "schema_changed"
    assert scalar(pipeline, "SELECT count(*) FROM prostoriq.source_version") == 1
    assert scalar(pipeline, "SELECT count(*) FROM prostoriq.space_revision") == 3
    assert (
        scalar(
            pipeline,
            "SELECT count(*) FROM prostoriq.import_error e JOIN prostoriq.import_job j USING (job_id) "
            "WHERE j.idempotency_key = 'bad' AND e.severity = 'blocking'",
        )
        == 1
    )


def test_spatial_layers_and_districts(importer: Importer, pipeline: Engine, tmp_path: Path) -> None:
    stops = fx.geojson_points(
        [
            fx.point(1, 15.9775, 45.8131, **{"Naziv_stajališta": "Trg bana Jelačića"}),
            fx.point(2, 15.9750, 45.8050),
        ]
    )
    assert (
        importer.run(
            "D03", idempotency_key="s", local_file=write(tmp_path, "s.geojson", stops)
        ).status
        == "succeeded"
    )
    assert (
        importer.run(
            "D07", idempotency_key="d", local_file=write(tmp_path, "d.zip", fx.districts_zip())
        ).status
        == "succeeded"
    )
    assert (
        scalar(pipeline, "SELECT count(*) FROM prostoriq.spatial_feature WHERE category='transit'")
        == 2
    )
    assert (
        scalar(pipeline, "SELECT properties->>'mode' FROM prostoriq.spatial_feature LIMIT 1")
        == "tram"
    )
    # Geography distance in metres between the two stops (~900 m), never on raw degrees (NF11).
    distance = scalar(
        pipeline,
        "SELECT ST_Distance(a.geom::geography, b.geom::geography) FROM prostoriq.spatial_feature a, "
        "prostoriq.spatial_feature b WHERE a.feature_key='1' AND b.feature_key='2'",
    )
    assert 850 < float(distance) < 950  # type: ignore[arg-type]
    district = scalar(
        pipeline,
        "SELECT d.name FROM prostoriq.district d WHERE ST_Covers(d.geom, ST_SetSRID(ST_MakePoint(15.97, 45.81), 4326))",
    )
    assert district == "Donji grad"


def test_network_import_through_ckan_metadata(importer: Importer, pipeline: Engine) -> None:
    spec = fx.registry().get("D01")
    package = {
        "success": True,
        "result": {
            "name": "prazni-poslovni-prostori",
            "license_id": "otvorena-dozvola",
            "license_title": "Otvorena dozvola",
            "resources": [
                {
                    "id": spec.resource_id,
                    "url": spec.resource_urls[0],
                    "format": "CSV",
                    "last_modified": "2025-12-30T13:01:18",
                },
                {"id": "other", "url": "https://data.zagreb.hr/other.csv", "format": "CSV"},
            ],
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "data.gov.hr":
            return httpx.Response(200, content=json.dumps(package).encode())
        assert str(request.url) == spec.resource_urls[0]
        return httpx.Response(200, content=fx.spaces_csv(), headers={"etag": '"abc"'})

    fetcher = SafeFetcher(
        ("data.gov.hr", "data.zagreb.hr"),
        resolver=lambda _h: ["93.184.216.34"],
        transport=httpx.MockTransport(handler),
    )
    outcome = importer.run("D01", idempotency_key="net", fetcher=fetcher)
    assert outcome.status == "succeeded", outcome
    with pipeline.connect() as conn:
        row = conn.execute(
            text("SELECT resource_id, download_url, manifest FROM prostoriq.source_version")
        ).one()
    assert row.resource_id == spec.resource_id
    assert row.download_url == spec.resource_urls[0]
    assert row.manifest["package_id"] == "prazni-poslovni-prostori"
    assert row.manifest["http"]["etag"] == '"abc"'


def test_unrecognised_licence_waits_for_review(importer: Importer) -> None:
    spec = fx.registry().get("D01")
    package = {
        "success": True,
        "result": {
            "name": "x",
            "license_id": "proprietary",
            "resources": [{"id": spec.resource_id, "url": spec.resource_urls[0], "format": "CSV"}],
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "data.gov.hr":
            return httpx.Response(200, content=json.dumps(package).encode())
        return httpx.Response(200, content=fx.spaces_csv())

    fetcher = SafeFetcher(
        ("data.gov.hr", "data.zagreb.hr"),
        resolver=lambda _h: ["93.184.216.34"],
        transport=httpx.MockTransport(handler),
    )
    assert importer.run("D01", idempotency_key="lic", fetcher=fetcher).status == "awaiting_review"


def test_network_failure_is_recorded(importer: Importer, pipeline: Engine) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    fetcher = SafeFetcher(
        ("data.gov.hr", "data.zagreb.hr"),
        resolver=lambda _h: ["93.184.216.34"],
        transport=httpx.MockTransport(handler),
    )
    outcome = importer.run("D01", idempotency_key="down", fetcher=fetcher)
    assert outcome.status == "failed"
    assert outcome.error_code == "http_error"
    assert scalar(pipeline, "SELECT count(*) FROM prostoriq.source_version") == 0


def test_second_running_job_is_source_busy(
    importer: Importer, pipeline: Engine, tmp_path: Path
) -> None:
    with pipeline.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO prostoriq.import_job (source_code, kind, status, idempotency_key, "
                "request_sha256, request_json) VALUES ('D01', 'source_import', 'running', 'x', "
                "repeat('0', 64), '{}')"
            )
        )
    with pytest.raises(ImportBusyError):
        importer.run(
            "D01", idempotency_key="y", local_file=write(tmp_path, "f.csv", fx.spaces_csv())
        )
