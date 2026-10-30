"""Shared helpers for public routes: active bundle, profiles, and row -> response shapes."""

from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from typing import Any

from sqlalchemy import Connection

from app.core.config import get_settings
from app.core.errors import ProblemError
from app.db.public import ActiveBundle, MetricRow, SpaceRow, active_bundle
from app.ranking.config import ProfileSet, load_profiles
from app.ranking.scoring import METRIC_REASONS
from app.ranking.status import evaluate

TRUTH_BANNER = (
    "Popis Grada iz 2024. Nijedan natječaj nije potvrđen. Prije odluke provjerite službenu objavu."
)
AIR_DISTANCE = "Udaljenosti su zračne, a ne vrijeme hoda."
OSM_ATTRIBUTION = "© OpenStreetMap contributors, ODbL"

_CRITERION_SOURCES: dict[str, tuple[str, ...]] = {
    "transit": ("D03", "D14"),
    "parking": ("D06",),
    "universities": ("D04",),
    "culture": ("D05",),
    "schools": ("D17", "D18"),
    "competition": ("D08",),
    "cost": (),
}
_UNITS = {"m": "m", "count": "count", "m2": "m2", "flag": "utility", "EUR/month": "eur_month"}
_DETAIL_KEYS = ("name", "mode", "distance", "nearest_names", "radius_m", "counts", "total")
USABLE = ("entrance_confirmed", "building_approximate")


@lru_cache
def profiles() -> ProfileSet:
    return load_profiles(get_settings().config_dir)


def require_active(conn: Connection) -> ActiveBundle:
    bundle = active_bundle(conn)
    if bundle is None:
        raise ProblemError(503, "DATASET_NOT_READY", "Podaci još nisu uvezeni ni aktivirani.")
    return bundle


def check_bundle(requested: str | None, bundle: ActiveBundle) -> None:
    if requested is not None and requested != bundle.bundle_id:
        raise ProblemError(
            409,
            "DATASET_CHANGED",
            "Podaci su u međuvremenu osvježeni. Učitajte ponovno da biste vidjeli novi paket.",
            extra={"active_dataset_bundle_id": bundle.bundle_id},
        )


def public_reason(reason: str | None) -> str | None:
    return None if reason is None else METRIC_REASONS.get(reason, reason)


def metric_out(
    criterion: str,
    row: MetricRow | None,
    space: SpaceRow,
    bundle: ActiveBundle,
    other_position_utility: Decimal,
) -> dict[str, Any]:
    rent = space.assessment.monthly_rent_eur if space.assessment else None
    if criterion == "cost" and rent is not None and space.assessment is not None:
        # The tender's own figure (D12). Displayed and compared with a budget, never scored.
        a = space.assessment
        return {
            "value": float(rent),
            "unit": "eur_month",
            "reason": None,
            "source_version_ids": [a.source_version_id] if a.source_version_id else [],
            "detail": {
                "basis": "tender_start_monthly",
                "tender_url": a.tender_url,
                "checked_at": a.checked_at.isoformat() if a.checked_at else None,
                "note": a.cost_note,
            },
        }
    if row is None:
        return {
            "value": None,
            "unit": "count",
            "reason": "data_not_available",
            "source_version_ids": [],
            "detail": {},
        }
    value: Decimal | None = row.value
    if criterion == "street" and value is not None:
        value = Decimal(1) if value == 1 else other_position_utility
    if criterion in ("area", "street"):
        versions = [space.revision_version_id]
    elif row.evidence.get("source_version_id"):
        versions = [str(row.evidence["source_version_id"])]
    else:
        versions = [
            bundle.versions[c] for c in _CRITERION_SOURCES[criterion] if c in bundle.versions
        ]
    detail = {k: row.evidence[k] for k in _DETAIL_KEYS if row.evidence.get(k) not in (None, [], {})}
    return {
        "value": float(value) if value is not None else None,
        "unit": _UNITS.get(row.unit, "count"),
        "reason": public_reason(row.reason) if value is None else None,
        "source_version_ids": versions,
        "detail": detail,
    }


def area_out(space: SpaceRow) -> dict[str, Any]:
    return {
        "value": float(space.area_m2) if space.area_m2 is not None else None,
        "unit": "m2",
        "reason": None if space.area_m2 is not None else "data_not_available",
        "source_version_ids": [space.revision_version_id],
        "detail": {},
    }


def coordinate_out(space: SpaceRow) -> dict[str, Any]:
    usable = space.precision_status in USABLE and space.lon is not None and space.lat is not None
    return {
        "geometry": ({"type": "Point", "coordinates": [space.lon, space.lat]} if usable else None),
        "precision_status": space.precision_status,
        "reason": None if usable else "missing_coordinate",
        "geo_evidence_id": space.geo_evidence_id,
        "checked_at": space.geo_checked_at,
    }


def status_out(space: SpaceRow, now: datetime) -> dict[str, Any]:
    return evaluate(
        space.inventory_kind,
        space.assessment,
        now=now,
        validity_hours=profiles().constants.status_validity_hours,
    )


def summary_out(space: SpaceRow, status: dict[str, Any]) -> dict[str, Any]:
    return {
        "space_id": space.space_id,
        "address": space.address,
        "area": area_out(space),
        "position_code": space.position_code,
        "position_reason": None if space.position_code else "unknown_position",
        "district_id": space.district_id,
        "district_name": space.district_name,
        "district_assignment": space.district_assignment,
        "coordinate": coordinate_out(space),
        "status": status,
        "reference_period": space.reference_period,
        "historical_inventory": True,
    }
