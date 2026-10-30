"""Shared setup for integration tests: restricted roles, clean tables, slice-3 import."""

import os
from pathlib import Path

from app.pipeline.importer import Importer

URL = os.environ.get("MIGRATION_DATABASE_URL")
PASSWORD = "pipeline_test_only"
STOP_NEAR_4763 = (15.9775, 45.8063)  # ~200 m north of Trg Ante Starčevića 7
PARKING_NEAR_4010 = (15.9860, 45.8250)


def write_file(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def import_ok(importer: Importer, code: str, path: Path) -> None:
    outcome = importer.run(code, idempotency_key=f"t-{code}-{path.name}", local_file=path)
    assert outcome.status == "succeeded", (code, outcome)
