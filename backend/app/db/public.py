"""Read and snapshot queries for the public API. Parameterised SQL only (NF03).

Everything public reads the active bundle. Ranking runs are insert-only snapshots.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, text

from app.ranking.config import canonical
from app.ranking.status import Assessment


@dataclass(frozen=True)
class ActiveBundle:
    bundle_id: str
    activated_at: datetime
    versions: dict[str, str]


@dataclass(frozen=True)
class SpaceRow:
    space_id: str
    address: str
    inventory_kind: str
    area_m2: Decimal | None
    position_code: str | None
    revision_version_id: str
    reference_period: str | None
    district_id: str | None
    district_name: str | None
    district_assignment: str
    geo_evidence_id: str | None
    precision_status: str
    lon: float | None
    lat: float | None
    geo_checked_at: datetime | None
    assessment: Assessment | None


@dataclass(frozen=True)
class MetricRow:
    value: Decimal | None
    unit: str
    reason: str | None
    evidence: dict[str, Any]


def active_bundle(conn: Connection) -> ActiveBundle | None:
    row = conn.execute(
        text("SELECT dataset_bundle_id::text, activated_at FROM prostoriq.active_dataset")
    ).first()
    if row is None:
        return None
    return ActiveBundle(str(row[0]), row[1], bundle_versions(conn, str(row[0])))


def bundle_versions(conn: Connection, bundle_id: str) -> dict[str, str]:
    rows = conn.execute(
        text(
            "SELECT source_code, source_version_id::text FROM prostoriq.bundle_source "
            "WHERE dataset_bundle_id = CAST(:b AS uuid) ORDER BY source_code"
        ),
        {"b": bundle_id},
    ).all()
    return {str(r[0]): str(r[1]) for r in rows}


_SPACES = """
    SELECT bs.space_id, r.address, r.inventory_kind, r.area_m2, r.position_code,
           r.source_version_id::text AS revision_version_id, sv.reference_period,
           bs.district_id, d.name AS district_name, bs.district_assignment,
           g.geo_evidence_id::text AS geo_evidence_id,
           COALESCE(g.precision_status, 'missing') AS precision_status,
           CASE WHEN g.geom IS NOT NULL THEN ST_X(g.geom) END AS lon,
           CASE WHEN g.geom IS NOT NULL THEN ST_Y(g.geom) END AS lat,
           g.checked_at AS geo_checked_at,
           a.assessment_id IS NOT NULL AS assessed, a.physical_vacancy, a.tender_active,
           a.activity_allowed, a.technical_suitable, a.checked_at, a.valid_until,
           a.evidence_url, a.tender_url, a.monthly_total_eur,
           a.source_version_id::text AS assessment_version_id,
           a.cost_evidence->>'note' AS cost_note
    FROM prostoriq.bundle_space bs
    JOIN prostoriq.space_revision r ON r.space_revision_id = bs.space_revision_id
    JOIN prostoriq.source_version sv ON sv.source_version_id = r.source_version_id
    LEFT JOIN prostoriq.geo_evidence g ON g.geo_evidence_id = bs.geo_evidence_id
    LEFT JOIN prostoriq.bundle_source d7
        ON d7.dataset_bundle_id = bs.dataset_bundle_id AND d7.source_code = 'D07'
    LEFT JOIN prostoriq.district d
        ON d.source_version_id = d7.source_version_id AND d.district_id = bs.district_id
    LEFT JOIN prostoriq.bundle_status st
        ON st.dataset_bundle_id = bs.dataset_bundle_id AND st.space_id = bs.space_id
       AND st.profile_code = :p
    LEFT JOIN prostoriq.status_assessment a ON a.assessment_id = st.assessment_id
    WHERE bs.dataset_bundle_id = CAST(:b AS uuid)
"""


def load_spaces(
    conn: Connection, bundle_id: str, profile: str, space_ids: list[str] | None = None
) -> list[SpaceRow]:
    sql = _SPACES
    params: dict[str, Any] = {"b": bundle_id, "p": profile}
    if space_ids is not None:
        sql += " AND bs.space_id = ANY(:ids)"
        params["ids"] = space_ids
    rows = conn.execute(text(sql + " ORDER BY bs.space_id::bigint"), params).mappings().all()
    return [
        SpaceRow(
            space_id=str(r["space_id"]),
            address=str(r["address"]),
            inventory_kind=str(r["inventory_kind"]),
            area_m2=r["area_m2"],
            position_code=r["position_code"],
            revision_version_id=str(r["revision_version_id"]),
            reference_period=r["reference_period"],
            district_id=r["district_id"],
            district_name=r["district_name"],
            district_assignment=str(r["district_assignment"]),
            geo_evidence_id=r["geo_evidence_id"],
            precision_status=str(r["precision_status"]),
            lon=float(r["lon"]) if r["lon"] is not None else None,
            lat=float(r["lat"]) if r["lat"] is not None else None,
            geo_checked_at=r["geo_checked_at"],
            assessment=(
                Assessment(
                    r["physical_vacancy"],
                    r["tender_active"],
                    r["activity_allowed"],
                    r["technical_suitable"],
                    r["checked_at"],
                    r["valid_until"],
                    r["evidence_url"],
                    r["tender_url"],
                    r["monthly_total_eur"],
                    r["assessment_version_id"],
                    r["cost_note"],
                )
                if r["assessed"]
                else None
            ),
        )
        for r in rows
    ]


def load_metrics(
    conn: Connection, bundle_id: str, radius_m: int, space_ids: list[str]
) -> dict[str, dict[str, MetricRow]]:
    rows = conn.execute(
        text(
            "SELECT space_id, criterion, value, unit, reason, evidence "
            "FROM prostoriq.spatial_metric WHERE dataset_bundle_id = CAST(:b AS uuid) "
            "AND radius_m = :r AND space_id = ANY(:ids)"
        ),
        {"b": bundle_id, "r": radius_m, "ids": space_ids},
    ).all()
    out: dict[str, dict[str, MetricRow]] = {}
    for space_id, criterion, value, unit, reason, evidence in rows:
        out.setdefault(str(space_id), {})[str(criterion)] = MetricRow(
            value, str(unit), reason, dict(evidence or {})
        )
    return out


def districts(conn: Connection, bundle: ActiveBundle) -> list[tuple[str, str]]:
    rows = conn.execute(
        text(
            "SELECT district_id, name FROM prostoriq.district "
            "WHERE source_version_id = CAST(:v AS uuid) ORDER BY name"
        ),
        {"v": bundle.versions.get("D07")},
    ).all()
    return [(str(r[0]), str(r[1])) for r in rows]


def sources(conn: Connection, bundle: ActiveBundle) -> list[dict[str, Any]]:
    rows = (
        conn.execute(
            text(
                """
                SELECT s.source_code, s.name, s.publisher, s.catalog_url, s.license_id,
                       s.attribution, s.enabled, v.source_version_id::text AS version_id,
                       v.reference_period, v.fetched_at, v.last_checked_at, v.sha256,
                       v.download_url, v.source_modified_at
                FROM prostoriq.source s
                LEFT JOIN prostoriq.bundle_source b
                    ON b.source_code = s.source_code AND b.dataset_bundle_id = CAST(:b AS uuid)
                LEFT JOIN prostoriq.source_version v ON v.source_version_id = b.source_version_id
                ORDER BY s.source_code
                """
            ),
            {"b": bundle.bundle_id},
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


def profile_versions(conn: Connection, shas: list[str]) -> dict[str, str]:
    rows = conn.execute(
        text(
            "SELECT config_sha256, profile_version::text FROM prostoriq.criteria_profile "
            "WHERE config_sha256 = ANY(:s)"
        ),
        {"s": shas},
    ).all()
    return {str(r[0]): str(r[1]) for r in rows}


def insert_ranking(conn: Connection, run: dict[str, Any], items: list[dict[str, Any]]) -> None:
    conn.execute(
        text(
            """
            INSERT INTO prostoriq.ranking_run (ranking_run_id, dataset_bundle_id,
                profile_version, request_sha256, request_json, comparison_basis_id,
                criteria_used, excluded_criteria, coverage_active, coverage_default_profile,
                config_snapshot, source_versions, access_token_hash, created_at, expires_at)
            VALUES (CAST(:id AS uuid), CAST(:bundle AS uuid), CAST(:profile_version AS uuid),
                :request_sha256, CAST(:request_json AS jsonb), :basis,
                CAST(:criteria_used AS jsonb), CAST(:excluded AS jsonb), :coverage_active,
                :coverage_default, CAST(:config AS jsonb), CAST(:source_versions AS jsonb),
                :token_hash, :created_at, :expires_at)
            """
        ),
        {
            **run,
            "request_json": canonical(run["request_json"]),
            "criteria_used": canonical(run["criteria_used"]),
            "excluded": canonical(run["excluded"]),
            "config": canonical(run["config"]),
            "source_versions": canonical(run["source_versions"]),
        },
    )
    json_fields = (
        "reasons",
        "raw_metrics",
        "utilities",
        "contributions",
        "status_snapshot",
        "coordinate_snapshot",
    )
    # One executemany round trip for all items (up to 500).
    conn.execute(
        text(
            """
            INSERT INTO prostoriq.ranking_item (ranking_run_id, space_id, candidate_status,
                rank, score, reason, reasons, raw_metrics, utilities, contributions,
                status_snapshot, coordinate_snapshot)
            VALUES (CAST(:run AS uuid), :space_id, :candidate_status, :rank, :score, :reason,
                CAST(:reasons AS jsonb), CAST(:raw_metrics AS jsonb),
                CAST(:utilities AS jsonb), CAST(:contributions AS jsonb),
                CAST(:status_snapshot AS jsonb), CAST(:coordinate_snapshot AS jsonb))
            """
        ),
        [
            {
                "run": run["id"],
                "space_id": item["space_id"],
                "candidate_status": item["candidate_status"],
                "rank": item["rank"],
                "score": item["score"],
                "reason": item["reason"],
                **{k: canonical(item[k]) for k in json_fields},
            }
            for item in items
        ],
    )


def get_ranking(
    conn: Connection, run_id: str
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    run = (
        conn.execute(
            text(
                """
                SELECT r.ranking_run_id::text AS id, r.dataset_bundle_id::text AS bundle,
                       r.profile_version::text AS profile_version, p.profile_code,
                       r.comparison_basis_id, r.criteria_used, r.excluded_criteria,
                       r.coverage_active, r.coverage_default_profile, r.config_snapshot,
                       r.source_versions, r.access_token_hash, r.created_at, r.expires_at,
                       r.request_json
                FROM prostoriq.ranking_run r
                JOIN prostoriq.criteria_profile p ON p.profile_version = r.profile_version
                WHERE r.ranking_run_id = CAST(:id AS uuid)
                """
            ),
            {"id": run_id},
        )
        .mappings()
        .first()
    )
    if run is None:
        return None
    items = (
        conn.execute(
            text(
                """
                SELECT space_id, candidate_status, rank, score, reason, reasons, raw_metrics, utilities,
                       contributions, status_snapshot, coordinate_snapshot
                FROM prostoriq.ranking_item WHERE ranking_run_id = CAST(:id AS uuid)
                ORDER BY rank NULLS LAST, space_id::bigint
                """
            ),
            {"id": run_id},
        )
        .mappings()
        .all()
    )
    return dict(run), [dict(i) for i in items]


# Point layers for the map: layer name -> spatial_feature category.
LAYER_CATEGORIES = {
    "transit": "transit",
    "parking": "parking",
    "universities": "university",
    "culture": "culture",
    "schools": "school",
}
# Display kind per source, so the map can draw tram and bus stops differently.
_KIND = {"D03": "tram", "D14": "bus", "D17": "kindergarten", "D18": "school"}


def district_layer(conn: Connection, bundle: ActiveBundle) -> dict[str, Any]:
    """D07 outlines simplified to ~10 m, plus a point inside each (label, district-only spaces)."""
    row = conn.execute(
        text(
            """
            SELECT json_build_object('type', 'FeatureCollection', 'features',
                   COALESCE(json_agg(json_build_object(
                       'type', 'Feature', 'id', district_id,
                       'geometry', ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.0001), 5)::json,
                       'properties', json_build_object(
                           'district_id', district_id, 'name', name,
                           'label_point', json_build_array(
                               round(ST_X(ST_PointOnSurface(geom))::numeric, 5),
                               round(ST_Y(ST_PointOnSurface(geom))::numeric, 5)))
                   ) ORDER BY name), '[]'::json))
            FROM prostoriq.district WHERE source_version_id = CAST(:v AS uuid)
            """
        ),
        {"v": bundle.versions.get("D07")},
    ).scalar_one()
    return dict(row)


def point_layer(conn: Connection, bundle: ActiveBundle, layer: str) -> dict[str, Any]:
    kinds = canonical(_KIND)
    row = conn.execute(
        text(
            """
            SELECT json_build_object('type', 'FeatureCollection', 'features',
                   COALESCE(json_agg(json_build_object(
                       'type', 'Feature',
                       'geometry', ST_AsGeoJSON(f.geom, 5)::json,
                       'properties', json_build_object(
                           'name', f.name,
                           'kind', COALESCE(f.properties->>'mode',
                                            CAST(:kinds AS jsonb)->>b.source_code, f.category),
                           'source_code', b.source_code)
                   ) ORDER BY f.feature_key), '[]'::json))
            FROM prostoriq.spatial_feature f
            JOIN prostoriq.bundle_source b ON b.source_version_id = f.source_version_id
            WHERE b.dataset_bundle_id = CAST(:b AS uuid) AND f.category = :c
            """
        ),
        {"b": bundle.bundle_id, "c": LAYER_CATEGORIES[layer], "kinds": kinds},
    ).scalar_one()
    return dict(row)
