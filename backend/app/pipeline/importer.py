"""Source import job (FZ02, FZ18, FZ22, TI01, TI02).

One call imports one source version:
  job row -> metadata (CKAN) -> download -> raw file -> parse -> versioned rows.

Guarantees
- Idempotent: the same source + idempotency key returns the same job. Identical content
  and metadata never create a second version; only last_checked_at moves.
- A failed import writes errors and the job status, never partial domain rows.
- One running job per source (unique partial index) -> SOURCE_BUSY.
- Record count change above 20 % vs the last valid version -> awaiting_review.
- Raw files are write-once, named by SHA-256.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from app.adapters.ckan import fetch_package
from app.adapters.coordinates_csv import parse_coordinates_csv
from app.adapters.districts_shp import parse_districts_shp
from app.adapters.geojson_points import parse_geojson_points
from app.adapters.http import FetchError, SafeFetcher
from app.adapters.osm import OsmExtract, as_parse_result, extract_osm, extract_timestamp
from app.adapters.parsing import ParseIssue, ParseResult
from app.adapters.registry import Registry, SourceSpec
from app.adapters.spaces_csv import parse_spaces_csv
from app.adapters.tender_csv import CONDITIONS as _CONDITIONS
from app.adapters.tender_csv import COST_DEFINITION, parse_tender_csv

logger = logging.getLogger("app.pipeline")

COUNT_CHANGE_REVIEW_RATIO = 0.20
MAX_STORED_ERRORS = 500
_EXT = {
    "spaces_csv": "csv",
    "geojson_points": "geojson",
    "districts_shp": "zip",
    "osm_competitors": "osm.pbf",
    "osm_addresses": "osm.pbf",
    "coordinates_csv": "csv",
    "tender_csv": "csv",
}
_OSM_KINDS = {"osm_competitors", "osm_addresses"}
# One PBF feeds two sources (D08, D19); parse it once per process and content hash.
_OSM_CACHE: dict[str, OsmExtract] = {}
BATCH = 2000


class ImportBusyError(Exception):
    """Another import of the same source is still running (SOURCE_BUSY)."""


@dataclass
class ImportOutcome:
    job_id: str
    source_code: str
    status: str
    error_code: str | None = None
    source_version_id: str | None = None
    record_count: int = 0
    unchanged: bool = False
    reused_job: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Download:
    content: bytes
    download_url: str
    resource_id: str | None
    metadata: dict[str, Any]
    metadata_sha256: str
    license_open: bool
    source_modified_at: datetime | None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def sync_sources(conn: Connection, registry: Registry) -> int:
    """Upsert the registry into prostoriq.source. Bumps version only when the policy changes."""
    count = 0
    for spec in registry.sources.values():
        conn.execute(
            text(
                """
                INSERT INTO prostoriq.source (source_code, name, publisher, catalog_url,
                    adapter_code, policy, policy_sha256, license_id, attribution, enabled)
                VALUES (:code, :name, :publisher, :catalog_url, :adapter, CAST(:policy AS jsonb),
                    :policy_sha, :license, :attribution, true)
                ON CONFLICT (source_code) DO UPDATE SET
                    name = EXCLUDED.name, publisher = EXCLUDED.publisher,
                    catalog_url = EXCLUDED.catalog_url, adapter_code = EXCLUDED.adapter_code,
                    policy = EXCLUDED.policy, license_id = EXCLUDED.license_id,
                    attribution = EXCLUDED.attribution,
                    version = prostoriq.source.version + 1, updated_at = now(),
                    policy_sha256 = EXCLUDED.policy_sha256
                WHERE prostoriq.source.policy_sha256 IS DISTINCT FROM EXCLUDED.policy_sha256
                """
            ),
            {
                "code": spec.code,
                "name": spec.name,
                "publisher": spec.publisher or "nepoznato",
                "catalog_url": spec.catalog_url,
                "adapter": spec.kind,
                "policy": _canonical(spec.raw),
                "policy_sha": spec.policy_sha256,
                "license": spec.license_id,
                "attribution": spec.attribution or spec.publisher or "nepoznato",
            },
        )
        count += 1
    return count


def _parse(spec: SourceSpec, content: bytes, raw_path: Path, sha: str) -> ParseResult:
    if spec.kind in _OSM_KINDS:
        if sha not in _OSM_CACHE:
            _OSM_CACHE.clear()
            _OSM_CACHE[sha] = extract_osm(raw_path)
        return as_parse_result(_OSM_CACHE[sha], spec.kind)
    if spec.kind == "coordinates_csv":
        return parse_coordinates_csv(content, spec)
    if spec.kind == "tender_csv":
        return parse_tender_csv(content, spec)
    if spec.kind == "spaces_csv":
        return parse_spaces_csv(content, spec)
    if spec.kind == "geojson_points":
        return parse_geojson_points(content, spec)
    if spec.kind == "districts_shp":
        return parse_districts_shp(content, spec)
    result = ParseResult()
    result.block("adapter_missing", f"Za izvor {spec.code} još ne postoji adapter.")
    return result


def download(spec: SourceSpec, fetcher: SafeFetcher) -> Download:
    """Resolve the resource through CKAN metadata when available, then download it."""
    metadata: dict[str, Any] = {"source_code": spec.code}
    resource_id = spec.resource_id
    license_open = True
    modified: datetime | None = None
    if spec.metadata_endpoint:
        package = fetch_package(fetcher, spec.metadata_endpoint)
        resource = package.resource(spec.resource_id, spec.resource_format)
        url = resource.url
        resource_id = resource.resource_id
        license_open = package.license_is_open
        modified = _parse_ts(resource.last_modified)
        metadata.update(
            {
                "package_id": package.package_id,
                "package_title": package.title,
                "license_id": package.license_id,
                "license_title": package.license_title,
                "metadata_modified": package.metadata_modified,
                "resource": {
                    "id": resource.resource_id,
                    "name": resource.name,
                    "format": resource.format,
                    "url": resource.url,
                    "last_modified": resource.last_modified,
                },
                "package_sha256": package.metadata_sha256,
            }
        )
    elif spec.resource_urls:
        url = spec.resource_urls[0]
        metadata["resource"] = {"url": url, "from": "registry"}
    else:
        raise FetchError("registry_mapping_missing", f"Izvor {spec.code} nema URL ni metapodatke.")

    result = fetcher.get(url, max_bytes=spec.max_response_bytes)
    metadata["http"] = {
        "final_url": result.final_url,
        "content_type": result.content_type,
        "etag": result.etag,
        "last_modified": result.last_modified,
        "bytes": len(result.content),
    }
    # The metadata hash covers what identifies the resource, not volatile HTTP headers.
    identity = {k: v for k, v in metadata.items() if k != "http"}
    return Download(
        content=result.content,
        download_url=url,
        resource_id=resource_id,
        metadata=metadata,
        metadata_sha256=_sha(_canonical(identity).encode("utf-8")),
        license_open=license_open,
        source_modified_at=modified,
    )


def local_download(spec: SourceSpec, path: Path) -> Download:
    content = path.read_bytes()
    metadata = {"source_code": spec.code, "manual_file": path.name, "bytes": len(content)}
    return Download(
        content=content,
        download_url=f"file:{path.name}",
        resource_id=spec.resource_id,
        metadata=metadata,
        metadata_sha256=_sha(_canonical({"source_code": spec.code, "manual": True}).encode()),
        license_open=True,
        source_modified_at=None,
    )


class Importer:
    def __init__(self, engine: Engine, registry: Registry, raw_dir: Path) -> None:
        self.engine = engine
        self.registry = registry
        self.raw_dir = raw_dir

    # -- job bookkeeping -------------------------------------------------------------------

    def _start_job(self, spec: SourceSpec, key: str, request: dict[str, Any]) -> tuple[str, bool]:
        body = _canonical(request)
        with self.engine.begin() as conn:
            existing = conn.execute(
                text(
                    "SELECT job_id::text, request_sha256 FROM prostoriq.import_job "
                    "WHERE source_code = :c AND idempotency_key = :k"
                ),
                {"c": spec.code, "k": key},
            ).first()
            if existing:
                if existing[1] != _sha(body.encode()):
                    raise ValueError("Isti Idempotency-Key je već korišten s drugačijim zahtjevom.")
                return str(existing[0]), True
            try:
                job_id = conn.execute(
                    text(
                        """
                        INSERT INTO prostoriq.import_job (source_code, kind, status,
                            idempotency_key, request_sha256, request_json, started_at, attempt)
                        VALUES (:c, 'source_import', 'running', :k, :sha, CAST(:body AS jsonb),
                            now(), 1)
                        RETURNING job_id::text
                        """
                    ),
                    {"c": spec.code, "k": key, "sha": _sha(body.encode()), "body": body},
                ).scalar_one()
            except IntegrityError as exc:
                raise ImportBusyError(
                    f"Uvoz izvora {spec.code} već traje ili čeka pregled "
                    "(provjeri: python -m app.cli reviews)."
                ) from exc
        return str(job_id), False

    def _finish_job(
        self,
        conn: Connection,
        job_id: str,
        status: str,
        *,
        accepted: int = 0,
        rejected: int = 0,
        error_code: str | None = None,
        report: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            text(
                """
                UPDATE prostoriq.import_job SET status = :s, finished_at = now(),
                    accepted_count = :a, rejected_count = :r, error_code = :e,
                    report = CAST(:report AS jsonb)
                WHERE job_id = CAST(:j AS uuid)
                """
            ),
            {
                "s": status,
                "a": accepted,
                "r": rejected,
                "e": error_code,
                "report": _canonical(report or {}),
                "j": job_id,
            },
        )

    def _store_issues(self, conn: Connection, job_id: str, issues: list[ParseIssue]) -> None:
        for issue in issues[:MAX_STORED_ERRORS]:
            conn.execute(
                text(
                    """
                    INSERT INTO prostoriq.import_error (job_id, source_record_key, code,
                        field_name, detail, severity)
                    VALUES (CAST(:j AS uuid), :k, :c, :f, :d, :s)
                    """
                ),
                {
                    "j": job_id,
                    "k": issue.record_key,
                    "c": issue.code,
                    "f": issue.field_name,
                    "d": issue.detail[:1000],
                    "s": issue.severity,
                },
            )

    def _job_outcome(self, job_id: str, code: str) -> ImportOutcome:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT status, error_code, report FROM prostoriq.import_job "
                    "WHERE job_id = CAST(:j AS uuid)"
                ),
                {"j": job_id},
            ).one()
        report = row[2] or {}
        return ImportOutcome(
            job_id=job_id,
            source_code=code,
            status=row[0],
            error_code=row[1],
            source_version_id=report.get("source_version_id"),
            record_count=int(report.get("record_count", 0)),
            unchanged=bool(report.get("unchanged", False)),
            reused_job=True,
        )

    # -- main entry ------------------------------------------------------------------------

    def run(
        self,
        code: str,
        *,
        idempotency_key: str,
        fetcher: SafeFetcher | None = None,
        local_file: Path | None = None,
    ) -> ImportOutcome:
        spec = self.registry.get(code)
        request = {"source_code": code, "file": local_file.name if local_file else None}
        job_id, reused = self._start_job(spec, idempotency_key, request)
        if reused:
            return self._job_outcome(job_id, code)

        outcome = ImportOutcome(job_id=job_id, source_code=code, status="running")
        try:
            if local_file is not None:
                dl = local_download(spec, local_file)
            else:
                if fetcher is None:
                    raise FetchError("no_fetcher", "Nije zadan ni dohvat ni lokalna datoteka.")
                dl = download(spec, fetcher)
        except FetchError as exc:
            with self.engine.begin() as conn:
                self._store_issues(conn, job_id, [ParseIssue(exc.code, exc.detail, "blocking")])
                self._finish_job(conn, job_id, "failed", error_code=exc.code)
            outcome.status, outcome.error_code, outcome.errors = "failed", exc.code, [exc.detail]
            return outcome

        content_sha = _sha(dl.content)
        with self.engine.begin() as conn:
            same = conn.execute(
                text(
                    "SELECT source_version_id::text, record_count FROM prostoriq.source_version "
                    "WHERE source_code = :c AND sha256 = :s AND metadata_sha256 = :m"
                ),
                {"c": code, "s": content_sha, "m": dl.metadata_sha256},
            ).first()
            if same:
                conn.execute(
                    text(
                        "UPDATE prostoriq.source_version SET last_checked_at = now() "
                        "WHERE source_version_id = CAST(:v AS uuid)"
                    ),
                    {"v": same[0]},
                )
                report = {"unchanged": True, "source_version_id": same[0], "record_count": same[1]}
                self._finish_job(conn, job_id, "succeeded", accepted=0, report=report)
                outcome.status, outcome.unchanged = "succeeded", True
                outcome.source_version_id, outcome.record_count = same[0], int(same[1])
                return outcome

        raw_key = self._write_raw(spec, content_sha, dl.content)
        parsed = _parse(spec, dl.content, self.raw_dir / raw_key, content_sha)
        if spec.kind in _OSM_KINDS and content_sha in _OSM_CACHE:
            stamp = extract_timestamp(_OSM_CACHE[content_sha])
            if stamp is not None:
                dl = Download(**{**dl.__dict__, "source_modified_at": stamp})
        if parsed.blocking:
            with self.engine.begin() as conn:
                self._store_issues(conn, job_id, parsed.issues)
                self._finish_job(
                    conn,
                    job_id,
                    "failed",
                    rejected=len(parsed.blocking),
                    error_code=parsed.first_blocking_code,
                    report={"raw_storage_key": raw_key, "sha256": content_sha},
                )
            outcome.status, outcome.error_code = "failed", parsed.first_blocking_code
            outcome.errors = [i.detail for i in parsed.blocking[:20]]
            return outcome

        warnings = list(parsed.issues)
        if not dl.license_open:
            warnings.append(
                ParseIssue(
                    "license_review",
                    "Licenca u CKAN metapodacima nije prepoznata kao Otvorena dozvola.",
                    "warning",
                )
            )
        if local_file is not None:
            warnings.append(
                ParseIssue(
                    "manual_file", f"Uvezeno iz lokalne datoteke {local_file.name}.", "warning"
                )
            )

        with self.engine.begin() as conn:
            previous = conn.execute(
                text(
                    "SELECT record_count FROM prostoriq.source_version "
                    "WHERE source_code = :c AND quality_status = 'valid' "
                    "ORDER BY fetched_at DESC LIMIT 1"
                ),
                {"c": code},
            ).scalar_one_or_none()
            count = len(parsed.records)
            if previous and abs(count - previous) / previous > COUNT_CHANGE_REVIEW_RATIO:
                warnings.append(
                    ParseIssue(
                        "count_changed",
                        f"Broj zapisa promijenjen s {previous} na {count} (više od 20 %).",
                        "warning",
                    )
                )
            needs_review = any(w.code in {"license_review", "count_changed"} for w in warnings)
            quality = "awaiting_review" if needs_review else "valid"

            version_id = self._insert_version(
                conn, spec, dl, job_id, content_sha, raw_key, count, quality
            )
            self._insert_records(conn, spec, version_id, parsed)
            self._store_issues(conn, job_id, warnings)
            report = {
                "source_version_id": version_id,
                "record_count": count,
                "sha256": content_sha,
                "raw_storage_key": raw_key,
                "warnings": len(warnings),
                "quality_status": quality,
            }
            status = "awaiting_review" if needs_review else "succeeded"
            self._finish_job(conn, job_id, status, accepted=count, report=report)

        outcome.status = status
        outcome.source_version_id = version_id
        outcome.record_count = count
        outcome.warnings = [w.detail for w in warnings[:20]]
        logger.info(
            "import_finished",
            extra={"extra_fields": {"source": code, "status": status, "records": count}},
        )
        return outcome

    # -- persistence -----------------------------------------------------------------------

    def _write_raw(self, spec: SourceSpec, sha: str, content: bytes) -> str:
        ext = _EXT.get(spec.kind, "bin")
        key = f"{spec.code}/{sha}.{ext}"
        path = self.raw_dir / key
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(content)
            tmp.replace(path)
        return key

    def _insert_version(
        self,
        conn: Connection,
        spec: SourceSpec,
        dl: Download,
        job_id: str,
        sha: str,
        raw_key: str,
        count: int,
        quality: str,
    ) -> str:
        now = datetime.now(UTC)
        version_id = conn.execute(
            text(
                """
                INSERT INTO prostoriq.source_version (source_code, job_id, resource_id, download_url,
                    sha256, metadata_sha256, license_id, policy_sha256, reference_period,
                    source_modified_at, fetched_at, last_checked_at, raw_storage_key, manifest,
                    record_count, quality_status)
                VALUES (:c, CAST(:j AS uuid), :rid, :url, :sha, :msha, :lic, :psha, :ref,
                    :mod, :now, :now, :raw, CAST(:manifest AS jsonb), :n, :q)
                RETURNING source_version_id::text
                """
            ),
            {
                "c": spec.code,
                "j": job_id,
                "rid": dl.resource_id,
                "url": dl.download_url,
                "sha": sha,
                "msha": dl.metadata_sha256,
                "lic": spec.license_id,
                "psha": spec.policy_sha256,
                "ref": spec.reference_period,
                "mod": dl.source_modified_at,
                "now": now,
                "raw": raw_key,
                "manifest": _canonical({**dl.metadata, "parser": spec.kind}),
                "n": count,
                "q": quality,
            },
        ).scalar_one()
        return str(version_id)

    def _insert_records(
        self, conn: Connection, spec: SourceSpec, version_id: str, parsed: ParseResult
    ) -> None:
        if spec.kind in _OSM_KINDS:
            # Tens of thousands of rows: batched, and provenance is the version + raw PBF hash
            # (no per-object source_record copy of the tags).
            self._insert_osm(conn, spec.kind, version_id, parsed.records)
            return
        if spec.kind == "coordinates_csv":
            self._insert_coordinates(conn, version_id, parsed.records)
            return
        if spec.kind == "tender_csv":
            self._insert_assessments(conn, version_id, parsed.records)
            return
        for rec in parsed.records:
            natural_key = rec.get("space_id") or rec.get("feature_key") or rec.get("district_id")
            record_id = conn.execute(
                text(
                    """
                    INSERT INTO prostoriq.source_record (source_version_id, natural_key,
                        record_sha256, raw_values)
                    VALUES (CAST(:v AS uuid), :k, :sha, CAST(:raw AS jsonb))
                    RETURNING source_record_id::text
                    """
                ),
                {
                    "v": version_id,
                    "k": natural_key,
                    "sha": rec["sha256"],
                    "raw": _canonical(rec["raw"]),
                },
            ).scalar_one()
            if spec.kind == "spaces_csv":
                self._insert_space(conn, version_id, str(record_id), rec)
            elif spec.kind == "geojson_points":
                self._insert_feature(conn, version_id, rec)
            elif spec.kind == "districts_shp":
                self._insert_district(conn, version_id, rec)

    @staticmethod
    def _insert_space(
        conn: Connection, version_id: str, record_id: str, rec: dict[str, Any]
    ) -> None:
        conn.execute(
            text("INSERT INTO prostoriq.space (space_id) VALUES (:id) ON CONFLICT DO NOTHING"),
            {"id": rec["space_id"]},
        )
        conn.execute(
            text(
                """
                INSERT INTO prostoriq.space_revision (space_id, source_version_id, source_record_id,
                    inventory_kind, address, district_name_source, area_m2, position_code,
                    position_source, structure_description, usage_code_source)
                VALUES (:id, CAST(:v AS uuid), CAST(:r AS uuid), :kind, :addr, :district, :area,
                    :pos, :pos_src, :desc, :usage)
                """
            ),
            {
                "id": rec["space_id"],
                "v": version_id,
                "r": record_id,
                "kind": rec["inventory_kind"],
                "addr": rec["address"],
                "district": rec["district_name_source"],
                "area": rec["area_m2"],
                "pos": rec["position_code"],
                "pos_src": rec["position_source"],
                "desc": rec["structure_description"],
                "usage": rec["usage_code_source"],
            },
        )

    @staticmethod
    def _insert_feature(conn: Connection, version_id: str, rec: dict[str, Any]) -> None:
        conn.execute(
            text(
                """
                INSERT INTO prostoriq.spatial_feature (source_version_id, feature_key, category,
                    name, address, geom, properties)
                VALUES (CAST(:v AS uuid), :k, :cat, :name, :addr,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), CAST(:props AS jsonb))
                """
            ),
            {
                "v": version_id,
                "k": rec["feature_key"],
                "cat": rec["category"],
                "name": rec["name"],
                "addr": rec["address"],
                "lon": rec["lon"],
                "lat": rec["lat"],
                "props": _canonical(rec["properties"]),
            },
        )

    @staticmethod
    def _insert_district(conn: Connection, version_id: str, rec: dict[str, Any]) -> None:
        conn.execute(
            text(
                """
                INSERT INTO prostoriq.district (source_version_id, district_id, name, geom)
                VALUES (CAST(:v AS uuid), :id, :name, ST_Multi(ST_GeomFromText(:wkt, 4326)))
                """
            ),
            {
                "v": version_id,
                "id": rec["district_id"],
                "name": rec["name"],
                "wkt": rec["geom_wkt"],
            },
        )

    @staticmethod
    def _insert_osm(
        conn: Connection, kind: str, version_id: str, records: list[dict[str, Any]]
    ) -> None:
        if kind == "osm_addresses":
            from app.gis.addresses import parse_house_number, street_key

            rows = []
            for r in records:
                house = parse_house_number(r["housenumber"])
                if house is None:
                    continue
                rows.append(
                    {
                        "v": version_id,
                        "t": r["osm_type"],
                        "id": r["osm_id"],
                        "street": r["street"],
                        "hn": r["housenumber"],
                        "key": street_key(r["street"]),
                        "num": house.number,
                        "letter": house.letter,
                        "lon": r["lon"],
                        "lat": r["lat"],
                    }
                )
            sql = text(
                """
                INSERT INTO prostoriq.osm_address (source_version_id, osm_type, osm_id, street,
                    housenumber, street_key, number, letter, geom)
                VALUES (CAST(:v AS uuid), :t, :id, :street, :hn, :key, :num, :letter,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
                """
            )
        else:
            rows = [
                {
                    "v": version_id,
                    "t": r["osm_type"],
                    "id": r["osm_id"],
                    "cat": r["category"],
                    "name": r["name"],
                    "nname": r["normalized_name"],
                    "addr": r["address"],
                    "naddr": r["normalized_address"],
                    "lon": r["lon"],
                    "lat": r["lat"],
                    "life": r["lifecycle_status"],
                    "tags": _canonical(r["tags"]),
                    "ts": r["osm_timestamp"],
                }
                for r in records
            ]
            sql = text(
                """
                INSERT INTO prostoriq.competitor (source_version_id, osm_type, osm_id, category,
                    name, normalized_name, address, normalized_address, geom, lifecycle_status,
                    tags, osm_timestamp)
                VALUES (CAST(:v AS uuid), :t, :id, :cat, :name, :nname, :addr, :naddr,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :life, CAST(:tags AS jsonb),
                    CAST(:ts AS timestamptz))
                """
            )
        for start in range(0, len(rows), BATCH):
            conn.execute(sql, rows[start : start + BATCH])

    @staticmethod
    def _insert_coordinates(
        conn: Connection, version_id: str, records: list[dict[str, Any]]
    ) -> None:
        for r in records:
            conn.execute(
                text("INSERT INTO prostoriq.space (space_id) VALUES (:id) ON CONFLICT DO NOTHING"),
                {"id": r["space_id"]},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO prostoriq.geo_evidence (space_id, source_version_id, geom,
                        precision_status, evidence_url, evidence_note, checked_at, license_id)
                    VALUES (:id, CAST(:v AS uuid),
                        CASE WHEN CAST(:lon AS double precision) IS NULL THEN NULL
                             ELSE ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) END,
                        :p, :url, :note, :at, 'per_record_provenance')
                    """
                ),
                {
                    "id": r["space_id"],
                    "v": version_id,
                    "lon": r["lon"],
                    "lat": r["lat"],
                    "p": r["precision_status"],
                    "url": r["evidence_url"],
                    "note": r["evidence_note"],
                    "at": r["checked_at"],
                },
            )

    @staticmethod
    def _insert_assessments(
        conn: Connection, version_id: str, records: list[dict[str, Any]]
    ) -> None:
        """D12: one status_assessment per space and profile. A 'yes' is valid for 168 hours."""
        for r in records:
            conn.execute(
                text("INSERT INTO prostoriq.space (space_id) VALUES (:id) ON CONFLICT DO NOTHING"),
                {"id": r["space_id"]},
            )
            has_yes = any(r[c] == "yes" for c in _CONDITIONS)
            rent = r["monthly_rent_eur"]
            conn.execute(
                text(
                    """
                    INSERT INTO prostoriq.status_assessment (space_id, source_version_id,
                        profile_code, physical_vacancy, tender_active, activity_allowed,
                        technical_suitable, tender_url, evidence_url, checked_at,
                        monthly_total_eur, valid_until, cost_definition_version, cost_evidence)
                    VALUES (:id, CAST(:v AS uuid), :p, :pv, :ta, :aa, :ts, :url, :url, :at,
                        :rent,
                        CASE WHEN :yes THEN CAST(:at AS timestamptz) + interval '168 hours' END,
                        :def, CAST(:ev AS jsonb))
                    """
                ),
                {
                    "id": r["space_id"],
                    "v": version_id,
                    "p": r["profile"],
                    "pv": r["physical_vacancy"],
                    "ta": r["tender_active"],
                    "aa": r["activity_allowed"],
                    "ts": r["technical_suitable"],
                    "url": r["tender_url"],
                    "at": r["checked_at"],
                    "rent": rent,
                    "yes": has_yes,
                    "def": COST_DEFINITION if rent is not None else None,
                    "ev": _canonical(
                        {
                            "source": "D12",
                            "basis": "početni mjesečni iznos zakupnine iz natječaja",
                            "tender_url": r["tender_url"],
                            "note": r["evidence_note"],
                        }
                    )
                    if rent is not None
                    else None,
                },
            )
