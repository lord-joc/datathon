"""Public read endpoints: profiles, districts, spaces, map layers, sources (active bundle only)."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request, Response
from pydantic import BaseModel

from app.api.v1 import presenters as p
from app.api.v1.schemas import (
    District,
    DistrictList,
    Metric,
    Profile,
    ProfileCode,
    ProfileList,
    SourceList,
    SourcePublic,
    SpaceDetail,
    SpaceList,
    SpaceSummary,
)
from app.core.errors import ProblemError
from app.db import public as q
from app.db.engine import get_engine
from app.ranking.config import CRITERIA

router = APIRouter(tags=["public"])

_REFERENCE_CACHE = "public, max-age=300"
# Known, stable limitations shown on the Sources screen.
_LIMITATIONS = {
    "D01": ["Popis iz 2024. je povijesni pregled; nije potvrda aktivnog natječaja."],
    "D02": ["Neuvjetni prostori nikad nisu u poretku."],
    "D08": ["Evidentirani objekti u OSM-u; popis možda nije potpun."],
    "D11": ["Ručna provjera tima; dio točaka je procjena na razini zgrade."],
    "D12": [
        "Početna zakupnina iz natječaja nije konačan ukupni trošak i ne boduje se.",
        "Upisano je samo ono što tim pročita u natječaju na zagreb.hr.",
    ],
    "D19": ["OSM adrese: točnost je razina zgrade, a ne ulaza."],
}


def _cached(request: Request, response: Response, model: BaseModel) -> BaseModel | Response:
    """ETag + short public cache for reference data that changes only with a new bundle."""
    etag = '"' + hashlib.sha256(model.model_dump_json().encode()).hexdigest()[:32] + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": _REFERENCE_CACHE})
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = _REFERENCE_CACHE
    return model


@router.get("/profiles", response_model=ProfileList, summary="Profili djelatnosti")
def list_profiles(request: Request, response: Response) -> BaseModel | Response:
    profile_set = p.profiles()
    with get_engine().connect() as conn:
        ids = q.profile_versions(conn, [x.config_sha256 for x in profile_set.profiles.values()])
    missing = [x.code for x in profile_set.profiles.values() if x.config_sha256 not in ids]
    if missing:
        raise ProblemError(
            503, "PROFILES_NOT_LOADED", "Profili još nisu učitani u bazu (sources-load)."
        )
    items = [
        Profile(
            profile=x.code,
            profile_version=UUID(ids[x.config_sha256]),
            version_label=x.version_label,
            name=x.name,
            summary=x.summary,
            icon=x.icon,
            target_area_m2=float(x.target_area_m2),
            weights={k: float(v) for k, v in x.weights.items()},
            competitor_categories=sorted(
                {v for values in (x.competitor_tags or {}).values() for v in values}
            ),
            config_version=profile_set.constants.version,
            cost_enabled=False,
        )
        for x in profile_set.profiles.values()
    ]
    return _cached(request, response, ProfileList(items=items))


@router.get("/districts", response_model=DistrictList, summary="Četvrti aktivnog paketa")
def list_districts(
    request: Request, response: Response, dataset_bundle_id: UUID | None = None
) -> BaseModel | Response:
    with get_engine().connect() as conn:
        bundle = p.require_active(conn)
        p.check_bundle(str(dataset_bundle_id) if dataset_bundle_id else None, bundle)
        rows = q.districts(conn, bundle)
    model = DistrictList(
        dataset_bundle_id=UUID(bundle.bundle_id),
        items=[District(district_id=i, name=n) for i, n in rows],
    )
    return _cached(request, response, model)


@router.get("/spaces", response_model=SpaceList, summary="Filtrirani popis prostora")
def list_spaces(
    profile: ProfileCode,
    dataset_bundle_id: UUID | None = None,
    area_min_m2: Annotated[float | None, Query(ge=0, le=100000)] = None,
    area_max_m2: Annotated[float | None, Query(ge=0, le=100000)] = None,
    district_ids: Annotated[list[str] | None, Query(max_length=17)] = None,
    include_conditional: bool = True,
    include_excluded: bool = False,
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SpaceList:
    if area_min_m2 is not None and area_max_m2 is not None and area_min_m2 > area_max_m2:
        raise ProblemError(422, "INVALID_RANGE", "Najmanja površina je veća od najveće.")
    now = datetime.now(UTC)
    with get_engine().connect() as conn:
        bundle = p.require_active(conn)
        p.check_bundle(str(dataset_bundle_id) if dataset_bundle_id else None, bundle)
        rows = q.load_spaces(conn, bundle.bundle_id, profile)

    wanted_districts = set(district_ids or [])
    matched = []
    unknown_area = 0
    for space in rows:
        status = p.status_out(space, now)
        kind = status["candidate_status"]
        if (kind == "excluded" and not include_excluded) or (
            kind == "conditional" and not include_conditional
        ):
            continue
        if wanted_districts and space.district_id not in wanted_districts:
            continue
        if area_min_m2 is not None or area_max_m2 is not None:
            if space.area_m2 is None:
                unknown_area += 1
                continue
            area = float(space.area_m2)
            if (area_min_m2 is not None and area < area_min_m2) or (
                area_max_m2 is not None and area > area_max_m2
            ):
                continue
        matched.append((space, status))

    start = (page - 1) * page_size
    warnings = [p.TRUTH_BANNER]
    if unknown_area:
        warnings.append(f"{unknown_area} prostora nema poznatu površinu pa nisu u rasponu.")
    return SpaceList(
        dataset_bundle_id=UUID(bundle.bundle_id),
        profile=profile,
        items=[
            SpaceSummary.model_validate(p.summary_out(s, st))
            for s, st in matched[start : start + page_size]
        ],
        total=len(matched),
        page=page,
        page_size=page_size,
        without_usable_coordinate=sum(
            1 for s, _ in matched if p.coordinate_out(s)["geometry"] is None
        ),
        warnings=warnings,
    )


@router.get("/spaces/{space_id}", response_model=SpaceDetail, summary="Detalj prostora")
def get_space(
    space_id: Annotated[str, Path(pattern=r"^[0-9]{1,12}$")],
    profile: ProfileCode,
    dataset_bundle_id: UUID | None = None,
    radius_m: Literal[500, 1000] = 500,
) -> SpaceDetail:
    now = datetime.now(UTC)
    with get_engine().connect() as conn:
        bundle = p.require_active(conn)
        p.check_bundle(str(dataset_bundle_id) if dataset_bundle_id else None, bundle)
        rows = q.load_spaces(conn, bundle.bundle_id, profile, [space_id])
        if not rows:
            raise ProblemError(404, "NOT_FOUND", "Prostor nije u aktivnom paketu.")
        metrics = q.load_metrics(conn, bundle.bundle_id, radius_m, [space_id]).get(space_id, {})
        source_rows = q.sources(conn, bundle)
    space = rows[0]
    other = p.profiles().constants.other_position_utility
    attribution = sorted(
        {str(r["attribution"]) for r in source_rows if r["version_id"] is not None}
    )
    if {"D08", "D19"} & set(bundle.versions):
        attribution.append(p.OSM_ATTRIBUTION)
    return SpaceDetail(
        dataset_bundle_id=UUID(bundle.bundle_id),
        space=SpaceSummary.model_validate(p.summary_out(space, p.status_out(space, now))),
        radius_m=radius_m,
        metrics={
            c: Metric.model_validate(p.metric_out(c, metrics.get(c), space, bundle, other))
            for c in CRITERIA
        },
        source_versions={k: UUID(v) for k, v in bundle.versions.items()},
        attribution=list(dict.fromkeys(attribution)),
        context_count=0,
    )


LayerName = Literal["districts", "transit", "parking", "universities", "culture", "schools"]


@router.get(
    "/layers/{layer}",
    summary="GeoJSON sloj za kartu",
    responses={200: {"content": {"application/geo+json": {}}}},
)
def get_layer(request: Request, layer: LayerName) -> Response:
    """Display only: district outlines (with a point inside each) or reference points."""
    with get_engine().connect() as conn:
        bundle = p.require_active(conn)
        data = (
            q.district_layer(conn, bundle)
            if layer == "districts"
            else q.point_layer(conn, bundle, layer)
        )
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    etag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
    headers = {"ETag": etag, "Cache-Control": _REFERENCE_CACHE}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="application/geo+json", headers=headers)


@router.get("/sources", response_model=SourceList, summary="Izvori, licence i datumi")
def list_sources(request: Request, response: Response) -> BaseModel | Response:
    with get_engine().connect() as conn:
        bundle = p.require_active(conn)
        rows = q.sources(conn, bundle)
    items = [
        SourcePublic(
            source_code=r["source_code"],
            name=r["name"],
            publisher=r["publisher"],
            catalog_url=r["catalog_url"],
            license_id=r["license_id"],
            attribution=r["attribution"],
            active_source_version_id=UUID(r["version_id"]) if r["version_id"] else None,
            reference_period=r["reference_period"],
            fetched_at=r["fetched_at"],
            last_checked_at=r["last_checked_at"],
            availability=(
                "disabled"
                if not r["enabled"]
                else ("available" if r["version_id"] else "unavailable")
            ),
            limitations=_LIMITATIONS.get(r["source_code"], []),
        )
        for r in rows
    ]
    return _cached(
        request, response, SourceList(dataset_bundle_id=UUID(bundle.bundle_id), items=items)
    )
