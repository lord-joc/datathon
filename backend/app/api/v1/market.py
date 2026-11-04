"""Presenting market context and notice cards (ADR24). Context only, never part of a score."""

import statistics
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Connection

from app.ai.brief import activity_matches
from app.ai.model import load_ai_config
from app.api.v1.schemas import (
    ContextCard,
    ContextLocation,
    MarketDistrict,
    MarketSummary,
    RentStats,
)
from app.db import public as q
from app.db.public import ActiveBundle

_OSM_WARNING = "Evidentirani objekti u OSM-u; popis možda nije potpun."
_LEASE_WARNING = (
    "Zakupnine su iz ugovora Grada Zagreba potpisanih u navedenom razdoblju. "
    "Nisu tržišne cijene privatnih prostora ni ponuda za pojedini prostor."
)


def card(row: dict[str, Any]) -> ContextCard:
    now = datetime.now(UTC)
    start = row["valid_from"]
    label = "date_not_confirmed" if start is None else "announced" if start > now else "current"
    return ContextCard(
        card_id=UUID(row["card_id"]),
        version=row["version"],
        topic=row["topic"],
        summary=row["summary"],
        location=ContextLocation(
            kind=row["location_kind"],
            label=row["location_label"],
            district_ids=list(row["district_ids"] or []),
        ),
        source_url=row["canonical_url"],
        publisher=row["publisher"],
        published_date=row["published_date"],
        valid_from=start,
        valid_to=row["valid_to"],
        review_due_at=row["review_due_at"],
        temporal_label=label,
        approved_at=row["approved_at"],
    )


def rent_stats(rents_per_m2: list[float], min_contracts: int) -> RentStats:
    """Below `min_contracts` only the count is given: a median of two contracts says nothing."""
    if len(rents_per_m2) < min_contracts:
        return RentStats(
            contracts=len(rents_per_m2),
            median_eur_per_m2=None,
            p25_eur_per_m2=None,
            p75_eur_per_m2=None,
        )
    q1, median, q3 = statistics.quantiles(rents_per_m2, n=4, method="inclusive")
    return RentStats(
        contracts=len(rents_per_m2),
        median_eur_per_m2=round(median, 2),
        p25_eur_per_m2=round(q1, 2),
        p75_eur_per_m2=round(q3, 2),
    )


def summary(
    conn: Connection, bundle: ActiveBundle, d07: str, profile: str, categories: list[str]
) -> MarketSummary:
    min_contracts = int(load_ai_config()["business_brief"]["min_contracts_for_median"])
    competitors = q.market_competitors(conn, d07, bundle.versions.get("D08"), categories)
    leases, version, period = q.market_leases(conn, d07, bundle.versions.get("D19"))
    matching = [row for row in leases if activity_matches(profile, str(row["activity"]))]
    per_m2 = [(row, float(row["monthly_rent_eur"]) / float(row["area_m2"])) for row in matching]
    known_competition = bool(categories) and "D08" in bundle.versions
    districts = [
        MarketDistrict(
            district_id=row["district_id"],
            name=row["name"],
            competitors=int(row["competitors"]) if known_competition else None,
            competitors_per_km2=(
                round(int(row["competitors"]) / float(row["area_km2"]), 2)
                if known_competition and row["area_km2"]
                else None
            ),
            rent=rent_stats(
                [v for lease, v in per_m2 if lease["district_id"] == row["district_id"]],
                min_contracts,
            ),
        )
        for row in competitors
    ]
    warnings = [_LEASE_WARNING]
    if known_competition:
        warnings.insert(0, _OSM_WARNING)
    return MarketSummary(
        dataset_bundle_id=UUID(bundle.bundle_id),
        profile=profile,
        competitor_categories=categories,
        city_rent=rent_stats([v for _, v in per_m2], min_contracts),
        districts=districts,
        lease_source_version_id=UUID(version) if version else None,
        lease_reference_period=period,
        pending_notices=q.pending_cards(conn),
        warnings=warnings,
    )
