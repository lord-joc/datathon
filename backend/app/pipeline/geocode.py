"""Geocode city premises against OSM address points (D19) and write geo_evidence.

Idempotent and append-only. Every space is matched again with the current matcher and a
new row is written only when the result changes (precision or matched object). The newest
row of a D19 version is that version's answer, so a corrected match also replaces a wrong
earlier one; the bundle then prefers D11 over it. Manual D11 evidence is never touched.
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import Connection, Engine, text

from app.gis.addresses import AddressIndex, AddressPoint, GeocodeResult, district_key

OSM_LICENSE = "ODbL-1.0"


@dataclass
class GeocodeReport:
    address_version_id: str
    address_points: int
    processed: int = 0
    skipped_existing: int = 0
    by_precision: dict[str, int] = field(default_factory=dict)
    by_method: dict[str, int] = field(default_factory=dict)


def latest_valid_version(conn: Connection, code: str) -> str | None:
    value = conn.execute(
        text(
            "SELECT source_version_id::text FROM prostoriq.source_version "
            "WHERE source_code = :c AND quality_status = 'valid' "
            "ORDER BY fetched_at DESC LIMIT 1"
        ),
        {"c": code},
    ).scalar_one_or_none()
    return str(value) if value else None


def _spaces(conn: Connection) -> list[tuple[str, str, str | None]]:
    """(space_id, address, district name) from the latest valid D01 and D02 versions."""
    rows = conn.execute(
        text(
            """
            SELECT r.space_id, r.address, r.district_name_source
            FROM prostoriq.space_revision r
            WHERE r.source_version_id IN (
                SELECT DISTINCT ON (source_code) source_version_id
                FROM prostoriq.source_version
                WHERE source_code IN ('D01', 'D02') AND quality_status = 'valid'
                ORDER BY source_code, fetched_at DESC
            )
            ORDER BY r.space_id::bigint
            """
        )
    ).all()
    return [(str(r[0]), str(r[1]), r[2]) for r in rows]


def _load_index(conn: Connection, version_id: str) -> AddressIndex:
    """Address points with the D07 district they lie in (None without D07 or on a border)."""
    rows = conn.execute(
        text(
            """
            SELECT a.osm_type, a.osm_id, a.street, a.housenumber, ST_X(a.geom), ST_Y(a.geom),
                   d.name
            FROM prostoriq.osm_address a
            LEFT JOIN LATERAL (
                SELECT CASE WHEN count(*) = 1 THEN min(x.name) END AS name
                FROM prostoriq.district x
                WHERE x.source_version_id = CAST(:d07 AS uuid) AND ST_Covers(x.geom, a.geom)
            ) d ON true
            WHERE a.source_version_id = CAST(:v AS uuid)
            """
        ),
        {"v": version_id, "d07": latest_valid_version(conn, "D07")},
    ).all()
    return AddressIndex(
        [
            AddressPoint(r[0], int(r[1]), r[2], r[3], float(r[4]), float(r[5]), district_key(r[6]))
            for r in rows
        ]
    )


def geocode_spaces(engine: Engine) -> GeocodeReport:
    with engine.connect() as conn:
        version = latest_valid_version(conn, "D19")
        if version is None:
            raise RuntimeError("Nema valjane verzije D19. Prvo pokreni 'osm-import --file …'.")
        index = _load_index(conn, version)
        spaces = _spaces(conn)
        # Latest evidence per space for this D19 version: (precision, note).
        existing = {
            str(r[0]): (str(r[1]), str(r[2] or ""))
            for r in conn.execute(
                text(
                    "SELECT DISTINCT ON (space_id) space_id, precision_status, evidence_note "
                    "FROM prostoriq.geo_evidence WHERE source_version_id = CAST(:v AS uuid) "
                    "ORDER BY space_id, checked_at DESC"
                ),
                {"v": version},
            )
        }
    report = GeocodeReport(address_version_id=version, address_points=len(index))
    now = datetime.now(UTC)
    rows = []
    for space_id, address, district in spaces:
        previous = existing.get(space_id)
        result: GeocodeResult = index.geocode(address, district)
        note = f"{result.note} | adresa u popisu: {address}"
        if previous == (result.precision, note):
            report.skipped_existing += 1
            continue
        report.processed += 1
        report.by_precision[result.precision] = report.by_precision.get(result.precision, 0) + 1
        method = result.method.split(":")[0]
        report.by_method[method] = report.by_method.get(method, 0) + 1
        rows.append(
            {
                "id": space_id,
                "v": version,
                "lon": result.lon,
                "lat": result.lat,
                "p": result.precision,
                "url": result.evidence_url,
                "note": note,
                "at": now,
                "lic": OSM_LICENSE,
            }
        )
    if rows:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO prostoriq.geo_evidence (space_id, source_version_id, geom,
                        precision_status, evidence_url, evidence_note, checked_at, license_id)
                    VALUES (:id, CAST(:v AS uuid),
                        CASE WHEN CAST(:lon AS double precision) IS NULL THEN NULL
                             ELSE ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) END,
                        :p, :url, :note, :at, :lic)
                    """
                ),
                rows,
            )
    return report


REVIEW_HEADER = [
    "space_id",
    "lon",
    "lat",
    "precision_status",
    "evidence_url",
    "evidence_note",
    "checked_at",
    # Read-only hint (address and why automatic matching failed). Never counts as evidence.
    "auto_note",
]


def review_csv(engine: Engine) -> str:
    """D11 template: every space whose best automatic evidence is not building-level.

    The output is a ready-to-fill D11 file. Rows stay 'needs_review'/'missing' until a team
    member checks the entrance and fills lon, lat, precision, evidence and checked_at.
    ';' as delimiter so Excel with Croatian regional settings opens it in columns; the CLI
    adds a UTF-8 BOM so Excel reads the diacritics correctly.
    """
    with engine.connect() as conn:
        version = latest_valid_version(conn, "D19")
        rows = conn.execute(
            text(
                """
                SELECT r.space_id, r.address, g.precision_status, g.evidence_note
                FROM prostoriq.space_revision r
                LEFT JOIN (
                    -- Newest automatic answer per space (the table is append-only).
                    SELECT DISTINCT ON (space_id) space_id, precision_status, evidence_note
                    FROM prostoriq.geo_evidence
                    WHERE source_version_id = CAST(:v AS uuid)
                    ORDER BY space_id, checked_at DESC
                ) g ON g.space_id = r.space_id
                WHERE r.source_version_id IN (
                    SELECT DISTINCT ON (source_code) source_version_id
                    FROM prostoriq.source_version
                    WHERE source_code IN ('D01', 'D02') AND quality_status = 'valid'
                    ORDER BY source_code, fetched_at DESC)
                  AND COALESCE(g.precision_status, 'missing') IN ('needs_review', 'missing')
                ORDER BY r.space_id::bigint
                """
            ),
            {"v": version},
        ).all()
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\n")
    writer.writerow(REVIEW_HEADER)
    for space_id, address, precision, note in rows:
        reason = (note or "").split(" | ")[0]
        hint = f"{address}: {reason}" if reason else str(address)
        writer.writerow([space_id, "", "", precision or "missing", "", "", "", hint])
    return out.getvalue()
