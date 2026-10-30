"""POST /rankings (immutable snapshot) and GET /rankings/{id} (X-Ranking-Token).

Flow (FZ07, FZ08):
1. The request must name the active bundle and the current profile version (else 409).
2. Status per space: excluded never ranked; conditional only if include_conditional.
3. If a criterion is known for only some candidates, nothing is chosen silently:
   409 COMPARISON_BASIS_CHANGED with a signed token valid for 10 minutes and only for
   this request. The client repeats the request with the token and basis_choice
   (common_criteria | remove_incomplete).
4. The result is stored with every input it used and returned with a one-time access
   token; only the token's SHA-256 is stored.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Path

from app.api.v1 import presenters as p
from app.api.v1.schemas import Coordinate, Metric, RankingRequest, RankingResponse, Status
from app.core import basis_token
from app.core.errors import ProblemError
from app.db import public as q
from app.db.engine import get_engine
from app.ranking.config import CRITERIA, canonical
from app.ranking.scoring import (
    BasisChoice,
    BasisConflict,
    Candidate,
    NoActiveCriteriaError,
    RawMetric,
    find_conflict,
    rank,
)

router = APIRouter(tags=["rankings"])


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _conflict_problem(
    conflict: BasisConflict, request_sha: str, conflict_sha: str, *, expired: bool
) -> ProblemError:
    ttl = p.profiles().constants.confirmation_ttl_s
    detail = (
        "Potvrda je istekla ili su se podaci promijenili. Odaberite ponovno."
        if expired
        else "Jedan kriterij nije dostupan svim kandidatima. Odaberite: usporedba po "
        "zajedničkim kriterijima ili uklanjanje nepotpunih prostora."
    )
    return ProblemError(
        409,
        "COMPARISON_BASIS_CHANGED",
        detail,
        extra={
            "missing_by_space": conflict.missing_by_space,
            "partial_criteria": conflict.partial_criteria,
            "proposed_criteria": conflict.proposed_criteria,
            "options": ["common_criteria", "remove_incomplete"],
            "comparison_basis_token": basis_token.issue(request_sha, conflict_sha, ttl),
            "expires_in_s": ttl,
        },
    )


@router.post("/rankings", status_code=201, response_model=RankingResponse, summary="Novi izračun")
def create_ranking(body: RankingRequest) -> RankingResponse:
    profile_set = p.profiles()
    profile = profile_set.get(body.profile)
    constants = profile_set.constants
    now = datetime.now(UTC)
    space_ids = list(body.space_ids)

    with get_engine().begin() as conn:
        bundle = p.require_active(conn)
        p.check_bundle(str(body.dataset_bundle_id), bundle)
        current = q.profile_versions(conn, [profile.config_sha256]).get(profile.config_sha256)
        if current is None:
            raise ProblemError(
                503, "PROFILES_NOT_LOADED", "Profili još nisu učitani u bazu (sources-load)."
            )
        if str(body.profile_version) != current:
            raise ProblemError(
                409,
                "PROFILE_CHANGED",
                "Profil je u međuvremenu promijenjen. Učitajte profile ponovno.",
                extra={"profile_version": current},
            )
        spaces = {
            s.space_id: s for s in q.load_spaces(conn, bundle.bundle_id, body.profile, space_ids)
        }
        unknown = [i for i in space_ids if i not in spaces]
        if unknown:
            raise ProblemError(
                422,
                "UNKNOWN_SPACES",
                "Neki prostori nisu u aktivnom paketu.",
                extra={"space_ids": sorted(unknown, key=int)},
            )
        metrics = q.load_metrics(conn, bundle.bundle_id, body.radius_m, space_ids)

        if body.weights is not None:
            weights = {k: Decimal(str(v)) for k, v in body.weights.model_dump().items()}
        else:
            weights = dict(profile.weights)
        if not body.prefer_lower_competition:
            weights["competition"] = Decimal(0)
        target = (
            Decimal(str(body.target_area_m2)) if body.target_area_m2 else profile.target_area_m2
        )

        statuses = {i: p.status_out(spaces[i], now) for i in space_ids}
        rankable = [
            i
            for i in space_ids
            if statuses[i]["candidate_status"] == "ready"
            or (statuses[i]["candidate_status"] == "conditional" and body.include_conditional)
        ]
        candidates = [
            Candidate(
                i,
                {c: RawMetric(m.value, m.reason) for c, m in metrics.get(i, {}).items()},
                body.radius_m,
            )
            for i in rankable
        ]

        request_core = body.model_dump(
            mode="json", exclude={"comparison_basis_token", "basis_choice"}
        )
        request_sha = _sha(request_core)
        choice: BasisChoice | None = None
        conflict = find_conflict(candidates, weights) if any(weights.values()) else None
        if conflict is not None:
            conflict_sha = _sha(
                {
                    "bundle": bundle.bundle_id,
                    "missing": conflict.missing_by_space,
                    "partial": conflict.partial_criteria,
                }
            )
            if body.comparison_basis_token is None:
                raise _conflict_problem(conflict, request_sha, conflict_sha, expired=False)
            if body.basis_choice is None:
                raise ProblemError(
                    422, "BASIS_CHOICE_REQUIRED", "Uz potvrdu odaberite način usporedbe."
                )
            try:
                basis_token.verify(body.comparison_basis_token, request_sha, conflict_sha)
            except basis_token.TokenError:
                raise _conflict_problem(conflict, request_sha, conflict_sha, expired=True) from None
            choice = body.basis_choice

        try:
            result = rank(
                candidates,
                weights=weights,
                default_weights=profile.weights,
                target_area_m2=target,
                constants=constants,
                choice=choice,
            )
        except NoActiveCriteriaError as exc:
            raise ProblemError(422, "NO_ACTIVE_CRITERIA", str(exc)) from exc
        assert not isinstance(result, BasisConflict)

        other = constants.other_position_utility
        scored = {s.space_id: s for s in result.items}
        removed = set(result.removed_space_ids)
        items: list[dict[str, Any]] = []
        for i in space_ids:
            space = spaces[i]
            status = Status.model_validate(statuses[i]).model_dump(mode="json")
            reasons = list(status["reasons"])
            s = scored.get(i)
            if i in removed:
                reasons.append("removed_incomplete")
                reason: str | None = "partial_coverage"
            elif s is None:
                if status["candidate_status"] == "conditional":
                    reasons.append("conditional_not_included")
                reason = "not_applicable"
            else:
                reason = s.reason
            raw = {
                c: Metric.model_validate(
                    p.metric_out(c, metrics.get(i, {}).get(c), space, bundle, other)
                ).model_dump(mode="json")
                for c in result.criteria_active
            }
            items.append(
                {
                    "space_id": i,
                    "candidate_status": status["candidate_status"],
                    "rank": s.rank if s else None,
                    "score": s.score if s else None,
                    "reason": reason,
                    "reasons": reasons,
                    "raw_metrics": raw,
                    "utilities": {k: float(v) for k, v in (s.utilities if s else {}).items()},
                    "contributions": {
                        k: float(v) for k, v in (s.contributions if s else {}).items()
                    },
                    "status_snapshot": status,
                    "coordinate_snapshot": Coordinate.model_validate(
                        p.coordinate_out(space)
                    ).model_dump(mode="json"),
                }
            )
        items.sort(key=lambda x: (x["rank"] is None, x["rank"] or 0, int(x["space_id"])))

        ranked_ids = sorted((x["space_id"] for x in items if x["rank"]), key=int)
        weights_used = {k: str(weights[k]) for k in CRITERIA}
        token = secrets.token_urlsafe(32)
        run: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "bundle": bundle.bundle_id,
            "profile_version": current,
            "request_sha256": request_sha,
            "request_json": {**request_core, "basis_choice": choice},
            "basis": _sha(
                {
                    "bundle": bundle.bundle_id,
                    "profile_version": current,
                    "criteria": result.criteria_used,
                    "spaces": ranked_ids,
                    "radius_m": body.radius_m,
                    "weights": weights_used,
                    "target_area_m2": str(target),
                }
            ),
            "criteria_used": result.criteria_used,
            "excluded": [{"criterion": c, "reason": r} for c, r in result.excluded_criteria],
            "coverage_active": result.coverage_active,
            "coverage_default": result.coverage_default,
            "config": {
                **profile.config,
                "weights_used": weights_used,
                "target_area_m2": str(target),
                "radius_m": body.radius_m,
                "basis_choice": choice,
            },
            "source_versions": bundle.versions,
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "created_at": now,
            "expires_at": now + timedelta(days=constants.ranking_ttl_days),
        }
        q.insert_ranking(conn, run, items)

    return _response(
        run_id=run["id"],
        bundle_id=bundle.bundle_id,
        profile=body.profile,
        profile_version=current,
        config_version=constants.version,
        source_versions=bundle.versions,
        basis=run["basis"],
        criteria_used=result.criteria_used,
        excluded=run["excluded"],
        coverage_active=result.coverage_active,
        coverage_default=result.coverage_default,
        items=items,
        created_at=now,
        expires_at=run["expires_at"],
        historical=False,
        token=token,
        radius_m=body.radius_m,
        target_area_m2=target,
    )


@router.get(
    "/rankings/{ranking_run_id}", response_model=RankingResponse, summary="Spremljeni izračun"
)
def get_ranking(
    ranking_run_id: Annotated[UUID, Path()],
    x_ranking_token: Annotated[str, Header(min_length=32, max_length=100)],
) -> RankingResponse:
    with get_engine().connect() as conn:
        found = q.get_ranking(conn, str(ranking_run_id))
        active = q.active_bundle(conn)
    if found is None:
        raise ProblemError(404, "NOT_FOUND", "Izračun ne postoji.")
    run, items = found
    given = hashlib.sha256(x_ranking_token.encode()).hexdigest()
    if not hmac.compare_digest(given, str(run["access_token_hash"])):
        raise ProblemError(403, "FORBIDDEN", "Token ne odgovara ovom izračunu.")
    if run["expires_at"] <= datetime.now(UTC):
        raise ProblemError(410, "GONE", "Izračun je istekao.")
    return _response(
        run_id=run["id"],
        bundle_id=run["bundle"],
        profile=run["profile_code"],
        profile_version=run["profile_version"],
        config_version=str(run["config_snapshot"]["ranking"]["version"]),
        source_versions=run["source_versions"],
        basis=str(run["comparison_basis_id"]),
        criteria_used=list(run["criteria_used"]),
        excluded=list(run["excluded_criteria"]),
        coverage_active=run["coverage_active"],
        coverage_default=run["coverage_default_profile"],
        items=items,
        created_at=run["created_at"],
        expires_at=run["expires_at"],
        historical=active is None or active.bundle_id != run["bundle"],
        token=None,
        radius_m=int(run["config_snapshot"]["radius_m"]),
        target_area_m2=Decimal(str(run["config_snapshot"]["target_area_m2"])),
    )


def _response(
    *,
    run_id: str,
    bundle_id: str,
    profile: str,
    profile_version: str,
    config_version: str,
    source_versions: dict[str, str],
    basis: str,
    criteria_used: list[str],
    excluded: list[dict[str, str]],
    coverage_active: Decimal,
    coverage_default: Decimal,
    items: list[dict[str, Any]],
    created_at: datetime,
    expires_at: datetime,
    historical: bool,
    token: str | None,
    radius_m: int,
    target_area_m2: Decimal,
) -> RankingResponse:
    warnings = [p.TRUTH_BANNER, p.AIR_DISTANCE]
    if historical:
        warnings.append("Izračun je napravljen nad ranijim paketom podataka.")
    unlocated = sum(1 for i in items if i["coordinate_snapshot"]["geometry"] is None)
    if unlocated:
        warnings.append(f"{unlocated} prostora nema potvrđenu lokaciju i nije na karti.")
    return RankingResponse.model_validate(
        {
            "ranking_run_id": run_id,
            "dataset_bundle_id": bundle_id,
            "profile": profile,
            "profile_version": profile_version,
            "config_version": config_version,
            "source_versions": source_versions,
            "comparison_basis_id": basis,
            "criteria_used": criteria_used,
            "excluded_criteria": excluded,
            "coverage_active": float(coverage_active),
            "coverage_default_profile": float(coverage_default),
            "radius_m": radius_m,
            "target_area_m2": float(target_area_m2),
            "items": [
                {**i, "score": float(i["score"]) if i["score"] is not None else None} for i in items
            ],
            "created_at": created_at,
            "expires_at": expires_at,
            "historical": historical,
            "warnings": warnings,
            "access_token": token,
        }
    )
