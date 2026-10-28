"""Read-only queries for the system status endpoint."""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("app.db")


@dataclass(frozen=True)
class DatabaseStatus:
    reachable: bool
    postgis_version: str | None
    active_bundle_id: str | None
    activated_at: datetime | None


def read_database_status(engine: Engine) -> DatabaseStatus:
    try:
        with engine.connect() as conn:
            postgis = conn.execute(text("SELECT postgis_lib_version()")).scalar_one_or_none()
            row = (
                conn.execute(
                    text(
                        "SELECT dataset_bundle_id::text AS bundle_id, activated_at "
                        "FROM prostoriq.active_dataset LIMIT 1"
                    )
                )
                .mappings()
                .first()
            )
    except SQLAlchemyError as exc:
        # Log only the error class: driver messages can contain host names or user names.
        logger.warning(
            "database_unreachable", extra={"extra_fields": {"error": type(exc).__name__}}
        )
        return DatabaseStatus(False, None, None, None)
    return DatabaseStatus(
        reachable=True,
        postgis_version=str(postgis) if postgis else None,
        active_bundle_id=row["bundle_id"] if row else None,
        activated_at=row["activated_at"] if row else None,
    )
