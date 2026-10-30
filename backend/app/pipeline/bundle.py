"""Dataset bundle: a consistent set of source versions, precomputed metrics, activation (ADR02).

build_bundle()
  1. latest valid version of every source (D01-D07 required)
  2. bundle_space: each D01/D02 space with its best location evidence
     (newest row per source version, then D11 entrance_confirmed > building_approximate
     > needs_review > missing, D11 first on ties)
     and its district (point in polygon, else the name from the list, else missing)
  3. spatial_metric for radius 500 and 1000 m: raw values, never utilities.
     Distances and counts use geography (metres on the ellipsoid), never raw degrees (NF11).
  4. validation report; status valid / rejected
activate_bundle()
  atomic switch of the single active pointer, with an advisory lock and an audit event.

Only 'entrance_confirmed' and 'building_approximate' locations enter spatial metrics (FZ03).
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, Engine, text

from app.pipeline.geocode import latest_valid_version

REQUIRED = ("D01", "D02", "D03", "D04", "D05", "D06", "D07")
OPTIONAL = ("D08", "D11", "D14", "D17", "D18", "D19")
RADII = (500, 1000)
COUNT_RADIUS_M = 600
USABLE = ("entrance_confirmed", "building_approximate")


class BundleError(Exception):
    pass


@dataclass
class BundleReport:
    bundle_id: str
    status: str
    created: bool
    report: dict[str, Any]


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _versions(conn: Connection) -> dict[str, str]:
    versions: dict[str, str] = {}
    for code in (*REQUIRED, *OPTIONAL):
        vid = latest_valid_version(conn, code)
        if vid:
            versions[code] = vid
    missing = [c for c in REQUIRED if c not in versions]
    if missing:
        raise BundleError(f"Nedostaju valjane verzije izvora: {', '.join(missing)}.")
    return versions


# Location evidence per space. geo_evidence is append-only: within one source version the
# newest row is that version's current answer (a corrected geocoding replaces a wrong one).
# Across D11 and D19: entrance > building-level > review > missing, D11 first on ties.
# This pick is what the bundle uses and what its identity covers.
_BEST_EVIDENCE = """
    SELECT DISTINCT ON (g.space_id) g.space_id, g.geo_evidence_id, g.geom, g.precision_status
    FROM (
        SELECT DISTINCT ON (e.space_id, e.source_version_id) e.*
        FROM prostoriq.geo_evidence e
        WHERE e.source_version_id IN (CAST(:d11 AS uuid), CAST(:d19 AS uuid))
        ORDER BY e.space_id, e.source_version_id, e.checked_at DESC
    ) g
    ORDER BY g.space_id,
        CASE g.precision_status WHEN 'entrance_confirmed' THEN 0
            WHEN 'building_approximate' THEN 1 WHEN 'needs_review' THEN 2 ELSE 3 END,
        (g.source_version_id = CAST(:d11 AS uuid)) DESC NULLS LAST,
        g.checked_at DESC
"""


def _evidence_digest(conn: Connection, versions: dict[str, str]) -> str:
    """Hash of the chosen evidence ids: new geocoding or D11 rows change the bundle."""
    ids = conn.execute(
        text(
            f"SELECT array_agg(ev.geo_evidence_id::text ORDER BY ev.space_id) FROM ({_BEST_EVIDENCE}) ev"
        ),
        {"d11": versions.get("D11"), "d19": versions.get("D19")},
    ).scalar_one()
    return hashlib.sha256(_canonical(ids or []).encode()).hexdigest()


def build_bundle(engine: Engine, label: str | None = None) -> BundleReport:
    with engine.begin() as conn:
        versions = _versions(conn)
        manifest = {"sources": versions, "location_evidence": _evidence_digest(conn, versions)}
        manifest_sha = hashlib.sha256(_canonical(manifest).encode()).hexdigest()
        existing = conn.execute(
            text(
                "SELECT dataset_bundle_id::text, status, validation_report "
                "FROM prostoriq.dataset_bundle WHERE manifest_sha256 = :m"
            ),
            {"m": manifest_sha},
        ).first()
        if existing:
            return BundleReport(str(existing[0]), str(existing[1]), False, dict(existing[2] or {}))

        bundle_id = str(
            conn.execute(
                text(
                    "INSERT INTO prostoriq.dataset_bundle (label, manifest_sha256, status) "
                    "VALUES (:l, :m, 'validating') RETURNING dataset_bundle_id::text"
                ),
                {"l": label or f"bundle {manifest_sha[:8]}", "m": manifest_sha},
            ).scalar_one()
        )
        for code, vid in versions.items():
            conn.execute(
                text(
                    "INSERT INTO prostoriq.bundle_source (dataset_bundle_id, source_code, "
                    "source_version_id) VALUES (CAST(:b AS uuid), :c, CAST(:v AS uuid))"
                ),
                {"b": bundle_id, "c": code, "v": vid},
            )

        params = {
            "b": bundle_id,
            "d01": versions["D01"],
            "d02": versions["D02"],
            "d03": versions["D03"],
            "d04": versions["D04"],
            "d05": versions["D05"],
            "d06": versions["D06"],
            "d07": versions["D07"],
            "d08": versions.get("D08"),
            "d11": versions.get("D11"),
            "d14": versions.get("D14"),
            "d17": versions.get("D17"),
            "d18": versions.get("D18"),
            "d19": versions.get("D19"),
            "count_r": COUNT_RADIUS_M,
        }

        overlap = conn.execute(
            text(
                """
                SELECT array_agg(a.space_id ORDER BY a.space_id::bigint)
                FROM prostoriq.space_revision a
                JOIN prostoriq.space_revision b ON a.space_id = b.space_id
                WHERE a.source_version_id = CAST(:d01 AS uuid)
                  AND b.source_version_id = CAST(:d02 AS uuid)
                """
            ),
            params,
        ).scalar_one()
        if overlap:
            report = {"error": "d01_d02_overlap", "space_ids": overlap, "versions": versions}
            _finish(conn, bundle_id, "rejected", report)
            return BundleReport(bundle_id, "rejected", True, report)

        _insert_bundle_spaces(conn, params)
        _insert_metrics(conn, params)
        report = _validation_report(conn, params, versions)
        _finish(conn, bundle_id, "valid", report)
        return BundleReport(bundle_id, "valid", True, report)


def _finish(conn: Connection, bundle_id: str, status: str, report: dict[str, Any]) -> None:
    body = _canonical(report)
    conn.execute(
        text(
            "UPDATE prostoriq.dataset_bundle SET status = :s, validation_report = CAST(:r AS jsonb), "
            "validation_sha256 = :h WHERE dataset_bundle_id = CAST(:b AS uuid)"
        ),
        {"s": status, "r": body, "h": hashlib.sha256(body.encode()).hexdigest(), "b": bundle_id},
    )


def _insert_bundle_spaces(conn: Connection, p: dict[str, Any]) -> None:
    conn.execute(
        text(
            f"""
            WITH revs AS (
                SELECT r.space_id, r.space_revision_id, r.district_name_source
                FROM prostoriq.space_revision r
                WHERE r.source_version_id IN (CAST(:d01 AS uuid), CAST(:d02 AS uuid))
            ),
            ev AS ({_BEST_EVIDENCE})
            INSERT INTO prostoriq.bundle_space (dataset_bundle_id, space_id, space_revision_id,
                geo_evidence_id, district_id, district_assignment)
            SELECT CAST(:b AS uuid), revs.space_id, revs.space_revision_id, ev.geo_evidence_id,
                CASE WHEN pip.n = 1 THEN pip.district_id
                     WHEN COALESCE(pip.n, 0) = 0 THEN byname.district_id END,
                CASE WHEN pip.n = 1 THEN 'confirmed'
                     WHEN pip.n > 1 THEN 'boundary_review'
                     WHEN byname.district_id IS NOT NULL THEN 'source_name'
                     ELSE 'missing' END
            FROM revs
            LEFT JOIN ev ON ev.space_id = revs.space_id
            LEFT JOIN LATERAL (
                SELECT count(*) AS n, min(d.district_id) AS district_id
                FROM prostoriq.district d
                WHERE ev.precision_status IN ('entrance_confirmed', 'building_approximate')
                  AND d.source_version_id = CAST(:d07 AS uuid)
                  AND ST_Covers(d.geom, ev.geom)
            ) pip ON true
            LEFT JOIN LATERAL (
                SELECT d.district_id FROM prostoriq.district d
                WHERE d.source_version_id = CAST(:d07 AS uuid)
                  AND regexp_replace(upper(d.name), '[\\s-]+', ' ', 'g')
                    = regexp_replace(upper(revs.district_name_source), '[\\s-]+', ' ', 'g')
                LIMIT 1
            ) byname ON true
            """
        ),
        p,
    )


# Each metric: SQL producing (space_id, radius_m, value, unit, reason, evidence) per row of
# the bundle_space x radius grid. `loc` is the usable location or NULL.
_GRID = """
    WITH grid AS (
        SELECT bs.space_id, rad.radius_m, r.area_m2, r.position_code, r.position_source,
               CASE WHEN g.precision_status IN ('entrance_confirmed', 'building_approximate')
                    THEN g.geom END AS loc,
               COALESCE(g.precision_status, 'missing') AS precision
        FROM prostoriq.bundle_space bs
        JOIN prostoriq.space_revision r ON r.space_revision_id = bs.space_revision_id
        LEFT JOIN prostoriq.geo_evidence g ON g.geo_evidence_id = bs.geo_evidence_id
        CROSS JOIN (VALUES (500), (1000)) AS rad(radius_m)
        WHERE bs.dataset_bundle_id = CAST(:b AS uuid)
    )
"""
_INSERT = """
    INSERT INTO prostoriq.spatial_metric (dataset_bundle_id, space_id, radius_m, criterion,
        value, unit, reason, evidence)
"""


def _nearest(criterion: str, category: str, version_params: str) -> str:
    return (
        _GRID
        + _INSERT
        + f"""
        SELECT CAST(:b AS uuid), grid.space_id, grid.radius_m, '{criterion}',
            CASE WHEN grid.loc IS NULL OR n.feature_key IS NULL THEN NULL
                 ELSE round(n.distance_m::numeric, 1) END,
            'm',
            CASE WHEN grid.loc IS NULL THEN 'location_not_confirmed'
                 WHEN n.feature_key IS NULL THEN 'no_feature_in_source' END,
            jsonb_build_object('precision', grid.precision, 'distance', 'air',
                'feature_key', n.feature_key, 'name', n.name, 'mode', n.mode,
                'source_version_id', n.source_version_id)
        FROM grid
        LEFT JOIN LATERAL (
            SELECT f.feature_key, f.name, f.properties->>'mode' AS mode,
                   f.source_version_id::text AS source_version_id,
                   ST_Distance(f.geom::geography, grid.loc::geography) AS distance_m
            FROM prostoriq.spatial_feature f
            WHERE grid.loc IS NOT NULL AND f.category = '{category}'
              AND f.source_version_id IN ({version_params})
              AND COALESCE(f.properties->>'review', '') <> 'outside_zagreb'
            ORDER BY f.geom::geography <-> grid.loc::geography
            LIMIT 1
        ) n ON true
        """
    )


def _count(criterion: str, category: str, version_params: str) -> str:
    return (
        _GRID
        + _INSERT
        + f"""
        SELECT CAST(:b AS uuid), grid.space_id, grid.radius_m, '{criterion}',
            CASE WHEN grid.loc IS NULL OR c.versions = 0 THEN NULL ELSE c.n END,
            'count',
            CASE WHEN grid.loc IS NULL THEN 'location_not_confirmed'
                 WHEN c.versions = 0 THEN 'source_missing' END,
            jsonb_build_object('precision', grid.precision, 'radius_m', CAST(:count_r AS int),
                'distance', 'air', 'nearest_names', c.names)
        FROM grid
        LEFT JOIN LATERAL (
            SELECT count(*) AS n,
                   (SELECT count(*) FROM unnest(ARRAY[{version_params}]) v WHERE v IS NOT NULL)
                       AS versions,
                   COALESCE((array_agg(f.name ORDER BY ST_Distance(f.geom::geography,
                       grid.loc::geography)) FILTER (WHERE f.name IS NOT NULL))[1:5],
                       ARRAY[]::text[]) AS names
            FROM prostoriq.spatial_feature f
            WHERE grid.loc IS NOT NULL AND f.category = '{category}'
              AND f.source_version_id IN ({version_params})
              AND ST_DWithin(f.geom::geography, grid.loc::geography, CAST(:count_r AS int))
        ) c ON true
        """
    )


_AREA = (
    _GRID
    + _INSERT
    + """
    SELECT CAST(:b AS uuid), space_id, radius_m, 'area', area_m2, 'm2',
        CASE WHEN area_m2 IS NULL THEN 'area_missing' END,
        jsonb_build_object('source', 'D01/D02')
    FROM grid
"""
)
_STREET = (
    _GRID
    + _INSERT
    + """
    SELECT CAST(:b AS uuid), space_id, radius_m, 'street',
        CASE position_code WHEN 'street' THEN 1 WHEN 'other' THEN 0 END, 'flag',
        CASE WHEN position_code IS NULL THEN 'position_unknown' END,
        jsonb_build_object('position_source', position_source)
    FROM grid
"""
)
_COST = (
    _GRID
    + _INSERT
    + """
    SELECT CAST(:b AS uuid), space_id, radius_m, 'cost', NULL, 'EUR/month', 'cost_unavailable',
        jsonb_build_object('note', 'Usporediv trošak nije objavljen; nije 0 EUR.')
    FROM grid
"""
)
# Competition: counts are informative until a coverage review is approved (FZ12), so the
# scoring value stays NULL with a reason, while the evidence carries the counts.
_COMPETITION = (
    _GRID
    + _INSERT
    + """
    SELECT CAST(:b AS uuid), grid.space_id, grid.radius_m, 'competition', NULL, 'count',
        CASE WHEN grid.loc IS NULL THEN 'location_not_confirmed'
             WHEN CAST(:d08 AS uuid) IS NULL THEN 'source_missing'
             ELSE 'coverage_not_reviewed' END,
        jsonb_build_object('precision', grid.precision, 'radius_m', grid.radius_m,
            'area_km2', round((pi() * (grid.radius_m / 1000.0) ^ 2)::numeric, 6),
            'counts', COALESCE(c.counts, '{}'::jsonb), 'total', COALESCE(c.total, 0))
    FROM grid
    LEFT JOIN LATERAL (
        SELECT jsonb_object_agg(category, n) AS counts, sum(n) AS total FROM (
            SELECT k.category, count(*) AS n
            FROM prostoriq.competitor k
            WHERE grid.loc IS NOT NULL AND k.source_version_id = CAST(:d08 AS uuid)
              AND k.lifecycle_status = 'mapped_active'
              AND ST_DWithin(k.geom::geography, grid.loc::geography, grid.radius_m)
            GROUP BY k.category) per_category
    ) c ON true
"""
)


def _insert_metrics(conn: Connection, p: dict[str, Any]) -> None:
    transit_versions = "CAST(:d03 AS uuid), CAST(:d14 AS uuid)"
    for sql in (
        _nearest("transit", "transit", transit_versions),
        _nearest("parking", "parking", "CAST(:d06 AS uuid)"),
        _count("universities", "university", "CAST(:d04 AS uuid)"),
        _count("culture", "culture", "CAST(:d05 AS uuid)"),
        _count("schools", "school", "CAST(:d17 AS uuid), CAST(:d18 AS uuid)"),
        _AREA,
        _STREET,
        _COMPETITION,
        _COST,
    ):
        conn.execute(text(sql), p)


def _validation_report(
    conn: Connection, p: dict[str, Any], versions: dict[str, str]
) -> dict[str, Any]:
    rows = conn.execute(
        text(
            """
            SELECT r.inventory_kind, COALESCE(g.precision_status, 'missing') AS precision,
                   bs.district_assignment, count(*) AS n
            FROM prostoriq.bundle_space bs
            JOIN prostoriq.space_revision r ON r.space_revision_id = bs.space_revision_id
            LEFT JOIN prostoriq.geo_evidence g ON g.geo_evidence_id = bs.geo_evidence_id
            WHERE bs.dataset_bundle_id = CAST(:b AS uuid)
            GROUP BY 1, 2, 3
            """
        ),
        p,
    ).all()
    by_precision: dict[str, int] = {}
    by_district: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for kind, precision, district, n in rows:
        by_precision[precision] = by_precision.get(precision, 0) + int(n)
        by_district[district] = by_district.get(district, 0) + int(n)
        by_kind[kind] = by_kind.get(kind, 0) + int(n)
    total = sum(by_kind.values())
    located = sum(v for k, v in by_precision.items() if k in USABLE)
    metrics = conn.execute(
        text(
            "SELECT criterion, count(*) FILTER (WHERE value IS NOT NULL), count(*) "
            "FROM prostoriq.spatial_metric WHERE dataset_bundle_id = CAST(:b AS uuid) "
            "AND radius_m = 500 GROUP BY criterion ORDER BY criterion"
        ),
        p,
    ).all()
    return {
        "versions": versions,
        "spaces": {"total": total, "by_inventory": by_kind},
        "location": {
            "by_precision": by_precision,
            "usable": located,
            "usable_pct": round(100 * located / total, 1) if total else 0.0,
        },
        "district_assignment": by_district,
        "metrics_with_value_r500": {
            c: {"with_value": int(v), "total": int(t)} for c, v, t in metrics
        },
    }


def activate_bundle(engine: Engine, bundle_id: str | None = None) -> str:
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('prostoriq.active_dataset'))"))
        if bundle_id is None:
            bundle_id = conn.execute(
                text(
                    "SELECT dataset_bundle_id::text FROM prostoriq.dataset_bundle "
                    "WHERE status = 'valid' ORDER BY created_at DESC LIMIT 1"
                )
            ).scalar_one_or_none()
            if bundle_id is None:
                raise BundleError(
                    "Nema valjanog paketa za aktivaciju. Prvo pokreni 'bundle-build'."
                )
        status = conn.execute(
            text(
                "SELECT status FROM prostoriq.dataset_bundle WHERE dataset_bundle_id = CAST(:b AS uuid)"
            ),
            {"b": bundle_id},
        ).scalar_one_or_none()
        if status != "valid":
            raise BundleError(f"Paket {bundle_id} nije valjan (status: {status}).")
        previous = conn.execute(
            text("SELECT dataset_bundle_id::text FROM prostoriq.active_dataset")
        ).scalar_one_or_none()
        conn.execute(
            text(
                """
                INSERT INTO prostoriq.active_dataset (singleton, dataset_bundle_id, activated_at)
                VALUES (true, CAST(:b AS uuid), now())
                ON CONFLICT (singleton) DO UPDATE
                    SET dataset_bundle_id = EXCLUDED.dataset_bundle_id, activated_at = now()
                """
            ),
            {"b": bundle_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO prostoriq.audit_event (action, entity_type, entity_id, request_id,
                    before_value, after_value, reason)
                VALUES ('activate_bundle', 'dataset_bundle', :b, CAST(:rid AS uuid),
                    CAST(:before AS jsonb), CAST(:after AS jsonb), 'CLI bundle-activate')
                """
            ),
            {
                "b": bundle_id,
                "rid": str(uuid.uuid4()),
                "before": _canonical({"dataset_bundle_id": previous}),
                "after": _canonical({"dataset_bundle_id": bundle_id}),
            },
        )
    return str(bundle_id)
