"""Full slice-3 flow on PostgreSQL + PostGIS as the restricted pipeline role.

import D01-D07 (+D14/D18) -> osm-import (D19 + D08 from one PBF) -> geocode -> D11 ->
bundle-build -> metrics -> activate. Distances are checked against independent haversine.
"""

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text

from app.adapters.coordinates_csv import HEADER_LINE
from app.gis.addresses import haversine_m
from app.pipeline.bundle import BundleError, activate_bundle, build_bundle
from app.pipeline.geocode import geocode_spaces, review_csv
from app.pipeline.importer import Importer
from tests import fixtures as fx
from tests.integration.support import (
    PARKING_NEAR_4010,
    STOP_NEAR_4763,
    URL,
    import_ok,
    write_file,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not URL, reason="MIGRATION_DATABASE_URL not set"),
]


def _metric(engine: Engine, bundle: str, space: str, criterion: str, radius: int = 500) -> Any:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT value, reason, evidence FROM prostoriq.spatial_metric "
                "WHERE dataset_bundle_id = CAST(:b AS uuid) AND space_id = :s "
                "AND criterion = :c AND radius_m = :r"
            ),
            {"b": bundle, "s": space, "c": criterion, "r": radius},
        ).one()


def _bundle_space(engine: Engine, bundle: str, space: str) -> Any:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT bs.district_assignment, d.name, g.precision_status "
                "FROM prostoriq.bundle_space bs "
                "LEFT JOIN prostoriq.district d ON d.district_id = bs.district_id "
                "LEFT JOIN prostoriq.geo_evidence g ON g.geo_evidence_id = bs.geo_evidence_id "
                "WHERE bs.dataset_bundle_id = CAST(:b AS uuid) AND bs.space_id = :s"
            ),
            {"b": bundle, "s": space},
        ).one()


def test_osm_import_fills_addresses_and_competitors(imported: Engine) -> None:
    with imported.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM prostoriq.osm_address")).scalar_one() == 4
        rows = {
            int(r[0]): str(r[1])
            for r in conn.execute(text("SELECT osm_id, lifecycle_status FROM prostoriq.competitor"))
        }
    assert rows == {20: "mapped_active", 21: "disused", 22: "mapped_active"}


def test_geocode_is_idempotent_and_review_lists_the_rest(imported: Engine) -> None:
    first = geocode_spaces(imported)
    assert first.processed == 4
    assert first.by_precision == {"building_approximate": 2, "needs_review": 1, "missing": 1}
    again = geocode_spaces(imported)
    assert (again.processed, again.skipped_existing) == (0, 4)

    review = review_csv(imported).splitlines()
    assert review[0] == HEADER_LINE.replace(",", ";") + ";auto_note"
    rows = [line.split(";") for line in review[1:]]
    assert [r[0] for r in rows] == ["5357", "10422"]
    # The automatic hint never pre-fills the evidence columns.
    assert all(r[4] == "" and r[5] == "" and r[7] for r in rows)


def test_bundle_metrics_districts_and_activation(imported: Engine, tmp_path: Path) -> None:
    geocode_spaces(imported)
    with pytest.raises(BundleError):
        activate_bundle(imported)

    result = build_bundle(imported, "test")
    assert result.status == "valid" and result.created
    bundle = result.bundle_id
    assert result.report["spaces"]["total"] == 4
    assert result.report["location"]["usable"] == 2

    assert tuple(_bundle_space(imported, bundle, "4763")) == (
        "confirmed",
        "Donji grad",
        "building_approximate",
    )
    # No usable location -> district from the list name, never from a guessed point.
    assignment, _, precision = _bundle_space(imported, bundle, "10422")
    assert precision == "needs_review" and assignment in {"source_name", "missing"}

    value, reason, evidence = _metric(imported, bundle, "4763", "transit")
    # Address node 1 and the bakery node 22 carry the same address -> their mean.
    expected = haversine_m(15.97725, 45.80425, *STOP_NEAR_4763)
    assert reason is None and abs(float(value) - expected) < 1.0
    assert evidence["distance"] == "air" and evidence["name"] == "Jurišićeva"

    value, reason, _ = _metric(imported, bundle, "10422", "transit")
    assert value is None and reason == "location_not_confirmed"

    value, _, _ = _metric(imported, bundle, "4010", "parking")
    assert abs(float(value) - haversine_m(*fx.VLASKA_96, *PARKING_NEAR_4010)) < 1.0

    value, _, _ = _metric(imported, bundle, "4763", "universities")
    assert int(value) == 1  # the far university is outside 600 m

    value, reason, evidence = _metric(imported, bundle, "4763", "competition")
    assert value is None and reason == "coverage_not_reviewed"
    assert evidence["counts"] == {"bakery": 1, "cafe": 1}  # disused bar is not counted

    value, reason, _ = _metric(imported, bundle, "4763", "cost")
    assert value is None and reason == "cost_unavailable"
    value, reason, _ = _metric(imported, bundle, "4763", "schools")
    assert value is None and reason == "source_missing"

    again = build_bundle(imported)
    assert (again.bundle_id, again.created) == (bundle, False)

    assert activate_bundle(imported) == bundle
    with imported.connect() as conn:
        active = conn.execute(
            text("SELECT dataset_bundle_id::text FROM prostoriq.active_dataset")
        ).scalar_one()
        audits = conn.execute(
            text("SELECT count(*) FROM prostoriq.audit_event WHERE action = 'activate_bundle'")
        ).scalar_one()
    assert active == bundle and audits >= 1


def test_d11_entrance_overrides_osm_and_creates_new_bundle(
    imported: Engine, tmp_path: Path
) -> None:
    geocode_spaces(imported)
    first = build_bundle(imported).bundle_id
    d11 = (
        HEADER_LINE + "\n"
        "10422,15.8700,45.7700,entrance_confirmed,,Obilazak tima,2026-10-27\n"
        "5357,,,missing,,MAKSIMIRSKA: nema,\n"
    ).encode()
    imp = Importer(imported, fx.registry(), tmp_path / "raw")
    import_ok(imp, "D11", write_file(tmp_path, "d11.csv", d11))

    second = build_bundle(imported)
    assert second.created and second.bundle_id != first
    assert _bundle_space(imported, second.bundle_id, "10422")[2] == "entrance_confirmed"
    assert second.report["location"]["usable"] == 3


def test_new_d19_evidence_creates_new_bundle(imported: Engine) -> None:
    geocode_spaces(imported)
    first = build_bundle(imported).bundle_id
    # An improved matcher appends better evidence for the same D19 version.
    with imported.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO prostoriq.geo_evidence (space_id, source_version_id, geom,
                    precision_status, evidence_note, checked_at, license_id)
                SELECT '10422', source_version_id, ST_SetSRID(ST_MakePoint(15.87, 45.77), 4326),
                    'building_approximate', 'test: improved match', now(), 'ODbL-1.0'
                FROM prostoriq.source_version WHERE source_code = 'D19'
                ORDER BY fetched_at DESC LIMIT 1
                """
            )
        )
    second = build_bundle(imported)
    assert second.created and second.bundle_id != first
    assert _bundle_space(imported, second.bundle_id, "10422")[2] == "building_approximate"
    again = build_bundle(imported)
    assert (again.bundle_id, again.created) == (second.bundle_id, False)


def test_newest_d19_answer_replaces_a_wrong_earlier_match(imported: Engine) -> None:
    geocode_spaces(imported)
    assert _bundle_space(imported, build_bundle(imported).bundle_id, "4763")[2] == (
        "building_approximate"
    )
    # A corrected matcher now sends 4763 to review: the old point must not survive.
    with imported.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO prostoriq.geo_evidence (space_id, source_version_id, geom,
                    precision_status, evidence_note, checked_at, license_id)
                SELECT '4763', source_version_id, NULL, 'needs_review', 'test: corrected',
                    now(), 'ODbL-1.0'
                FROM prostoriq.source_version WHERE source_code = 'D19'
                ORDER BY fetched_at DESC LIMIT 1
                """
            )
        )
    second = build_bundle(imported)
    assert second.created
    assert _bundle_space(imported, second.bundle_id, "4763")[2] == "needs_review"


def test_overlapping_d01_d02_is_rejected(pipeline: Engine, tmp_path: Path) -> None:
    imp = Importer(pipeline, fx.registry(), tmp_path / "raw")
    import_ok(imp, "D01", write_file(tmp_path, "d01.csv", fx.spaces_csv()))
    clash = fx.spaces_csv(fx.D02_HEADER, [fx.D01_ROWS[1]], preamble_rows=2)
    import_ok(imp, "D02", write_file(tmp_path, "d02.csv", clash))
    for code, name, content in (
        ("D03", "a.geojson", fx.geojson_points([fx.point(1, 15.97, 45.80)])),
        ("D04", "b.geojson", fx.geojson_points([fx.point(1, 15.97, 45.80)])),
        ("D05", "c.geojson", fx.geojson_points([fx.point(1, 15.97, 45.80)])),
        ("D06", "d.geojson", fx.geojson_points([fx.point(1, 15.97, 45.80)])),
        ("D07", "e.zip", fx.districts_zip()),
    ):
        import_ok(imp, code, write_file(tmp_path, name, content))
    result = build_bundle(pipeline)
    assert result.status == "rejected"
    assert result.report["space_ids"] == ["4763"]
