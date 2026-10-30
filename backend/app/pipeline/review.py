"""Human decision on an import that stopped at awaiting_review (FZ22).

An import waits for review when its license is unclear or its record count moved by more
than 20 %. Until someone decides, the version is not used by any bundle and the source is
blocked for new imports (one open job per source).

approve -> source_version valid, job succeeded: the next bundle-build uses it.
reject  -> source_version rejected, job failed (review_rejected): the previous valid
           version stays in use.
Both write an audit event with the reason.
"""

import json
import uuid
from dataclasses import dataclass

from sqlalchemy import Engine, text


class ReviewError(Exception):
    pass


@dataclass(frozen=True)
class PendingReview:
    job_id: str
    source_code: str
    source_version_id: str
    record_count: int
    warnings: list[str]


@dataclass(frozen=True)
class ReviewOutcome:
    job_id: str
    source_code: str
    source_version_id: str
    decision: str


def pending_reviews(engine: Engine) -> list[PendingReview]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT j.job_id::text, j.source_code, j.report->>'source_version_id',
                       COALESCE((j.report->>'record_count')::int, 0),
                       COALESCE(array_agg(e.detail ORDER BY e.error_id)
                           FILTER (WHERE e.error_id IS NOT NULL), ARRAY[]::text[])
                FROM prostoriq.import_job j
                LEFT JOIN prostoriq.import_error e ON e.job_id = j.job_id
                WHERE j.status = 'awaiting_review'
                GROUP BY j.job_id
                ORDER BY j.requested_at
                """
            )
        ).all()
    return [PendingReview(r[0], r[1], r[2], int(r[3]), list(r[4])) for r in rows]


def review_import(engine: Engine, job_id: str, *, approve: bool, reason: str) -> ReviewOutcome:
    if not reason.strip():
        raise ReviewError("Razlog odluke je obavezan.")
    try:
        uuid.UUID(job_id)
    except ValueError as exc:
        raise ReviewError(f"'{job_id}' nije valjan ID posla.") from exc
    decision = "approved" if approve else "rejected"
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT source_code, status, report->>'source_version_id' "
                "FROM prostoriq.import_job WHERE job_id = CAST(:j AS uuid) FOR UPDATE"
            ),
            {"j": job_id},
        ).first()
        if row is None:
            raise ReviewError(f"Posao {job_id} ne postoji.")
        code, status, version_id = str(row[0]), str(row[1]), row[2]
        if status != "awaiting_review" or not version_id:
            raise ReviewError(f"Posao {job_id} ne čeka pregled (status: {status}).")
        conn.execute(
            text(
                "UPDATE prostoriq.source_version SET quality_status = :q "
                "WHERE source_version_id = CAST(:v AS uuid) AND quality_status = 'awaiting_review'"
            ),
            {"q": "valid" if approve else "rejected", "v": version_id},
        )
        conn.execute(
            text(
                "UPDATE prostoriq.import_job SET status = :s, error_code = :e, finished_at = now() "
                "WHERE job_id = CAST(:j AS uuid)"
            ),
            {
                "s": "succeeded" if approve else "failed",
                "e": None if approve else "review_rejected",
                "j": job_id,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO prostoriq.audit_event (action, entity_type, entity_id, request_id,
                    before_value, after_value, reason)
                VALUES ('review_import', 'source_version', :v, CAST(:rid AS uuid),
                    CAST(:before AS jsonb), CAST(:after AS jsonb), :reason)
                """
            ),
            {
                "v": version_id,
                "rid": str(uuid.uuid4()),
                "before": json.dumps({"quality_status": "awaiting_review", "job_id": job_id}),
                "after": json.dumps({"quality_status": "valid" if approve else "rejected"}),
                "reason": reason.strip()[:500],
            },
        )
    return ReviewOutcome(job_id, code, str(version_id), decision)
