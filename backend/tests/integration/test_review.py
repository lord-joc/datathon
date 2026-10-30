"""Import review (FZ22): a version waiting for review is unused and blocks new imports
until someone approves or rejects it."""

from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from app.adapters.coordinates_csv import HEADER_LINE
from app.pipeline.geocode import latest_valid_version
from app.pipeline.importer import ImportBusyError, Importer
from app.pipeline.review import ReviewError, pending_reviews, review_import
from tests import fixtures as fx
from tests.integration.support import URL, write_file

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not URL, reason="MIGRATION_DATABASE_URL not set"),
]

ROWS = {
    "4763": "4763,15.97761,45.80455,entrance_confirmed,,Obilazak tima,2026-10-27",
    "4010": "4010,15.98500,45.82500,building_approximate,,OSM way 100,2026-10-27",
    "10422": "10422,15.87000,45.77000,building_approximate,,OSM node 2,2026-10-27",
    "5357": "5357,16.03000,45.82000,building_approximate,,OSM node 9,2026-10-27",
}


def _d11(tmp_path: Path, name: str, ids: list[str]) -> Path:
    body = "\n".join([HEADER_LINE, *(ROWS[i] for i in ids)]) + "\n"
    return write_file(tmp_path, name, body.encode())


def _version(engine: Engine, version_id: str) -> str:
    with engine.connect() as conn:
        return str(
            conn.execute(
                text(
                    "SELECT quality_status FROM prostoriq.source_version "
                    "WHERE source_version_id = CAST(:v AS uuid)"
                ),
                {"v": version_id},
            ).scalar_one()
        )


def _latest_d11(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return latest_valid_version(conn, "D11")


def test_count_drop_waits_for_review_then_reject_keeps_previous(
    imported: Engine, tmp_path: Path
) -> None:
    imp = Importer(imported, fx.registry(), tmp_path / "raw")
    first = imp.run("D11", idempotency_key="a", local_file=_d11(tmp_path, "a.csv", list(ROWS)))
    assert first.status == "succeeded"
    second = imp.run("D11", idempotency_key="b", local_file=_d11(tmp_path, "b.csv", ["4763"]))
    assert second.status == "awaiting_review"
    assert _latest_d11(imported) == first.source_version_id

    pending = pending_reviews(imported)
    assert [p.job_id for p in pending] == [second.job_id]
    assert any("20 %" in w for w in pending[0].warnings)

    with pytest.raises(ImportBusyError):
        imp.run("D11", idempotency_key="c", local_file=_d11(tmp_path, "c.csv", ["4010"]))

    with pytest.raises(ReviewError):
        review_import(imported, second.job_id, approve=False, reason=" ")
    outcome = review_import(imported, second.job_id, approve=False, reason="test: probni uvoz")
    assert outcome.decision == "rejected"
    assert second.source_version_id and _version(imported, second.source_version_id) == "rejected"
    assert _latest_d11(imported) == first.source_version_id
    assert pending_reviews(imported) == []

    with pytest.raises(ReviewError):
        review_import(imported, second.job_id, approve=True, reason="ponovno")

    third = imp.run("D11", idempotency_key="c", local_file=_d11(tmp_path, "c.csv", ["4010"]))
    assert third.status == "awaiting_review"
    review_import(imported, third.job_id, approve=True, reason="test: smanjen popis je ispravan")
    assert _latest_d11(imported) == third.source_version_id
    with imported.connect() as conn:
        audits = conn.execute(
            text(
                "SELECT count(*) FROM prostoriq.audit_event "
                "WHERE action = 'review_import' AND entity_id = ANY(:v)"
            ),
            {"v": [second.source_version_id, third.source_version_id]},
        ).scalar_one()
    assert audits == 2
