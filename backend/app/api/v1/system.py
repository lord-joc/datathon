"""Health and status endpoints."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from app import __version__
from app.db.engine import get_engine
from app.db.status import read_database_status

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]
    version: str


class SystemStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok", "degraded"]
    version: str
    database: Literal["up", "down"]
    postgis_version: str | None
    dataset_ready: bool
    active_bundle_id: str | None
    activated_at: datetime | None
    message: str


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
def health() -> HealthResponse:
    """Process is alive. Does not touch the database (used by container healthchecks)."""
    return HealthResponse(status="ok", version=__version__)


@router.get("/status", response_model=SystemStatusResponse, summary="System and data status")
def system_status(response: Response) -> SystemStatusResponse:
    db = read_database_status(get_engine())
    if not db.reachable:
        response.status_code = 503
        return SystemStatusResponse(
            status="degraded",
            version=__version__,
            database="down",
            postgis_version=None,
            dataset_ready=False,
            active_bundle_id=None,
            activated_at=None,
            message="Baza podataka trenutačno nije dostupna.",
        )
    ready = db.active_bundle_id is not None
    return SystemStatusResponse(
        status="ok",
        version=__version__,
        database="up",
        postgis_version=db.postgis_version,
        dataset_ready=ready,
        active_bundle_id=db.active_bundle_id,
        activated_at=db.activated_at,
        message="Podaci su spremni." if ready else "Podaci još nisu uvezeni ni aktivirani.",
    )
