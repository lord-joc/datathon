"""Public API request and response models (docs/contracts/openapi.yaml)."""

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ProfileCode = Literal[
    "cafe", "office", "retail", "food_takeaway", "personal_care", "education", "workshop"
]
Criterion = Literal[
    "transit",
    "universities",
    "culture",
    "parking",
    "schools",
    "area",
    "street",
    "competition",
    "cost",
]
CandidateStatus = Literal["ready", "conditional", "excluded"]
Precision = Literal["entrance_confirmed", "building_approximate", "needs_review", "missing"]
SpaceId = Annotated[str, Field(pattern=r"^[0-9]{1,12}$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Weights(Strict):
    transit: float = Field(ge=0, le=100)
    universities: float = Field(ge=0, le=100)
    culture: float = Field(ge=0, le=100)
    parking: float = Field(ge=0, le=100)
    schools: float = Field(ge=0, le=100)
    area: float = Field(ge=0, le=100)
    street: float = Field(ge=0, le=100)
    competition: float = Field(ge=0, le=100)
    cost: float = Field(ge=0, le=100)


class Profile(Strict):
    profile: ProfileCode
    profile_version: UUID
    version_label: str
    name: str
    summary: str
    icon: str
    target_area_m2: float
    weights: Weights
    competitor_categories: list[str]
    config_version: str
    cost_enabled: bool


class ProfileList(Strict):
    items: list[Profile]


class District(Strict):
    district_id: str
    name: str


class DistrictList(Strict):
    dataset_bundle_id: UUID
    items: list[District]


class Metric(Strict):
    value: float | None
    unit: Literal["m", "count", "m2", "objects_per_km2", "eur_month", "utility"]
    reason: str | None
    source_version_ids: list[UUID]
    detail: dict[str, Any] = Field(default_factory=dict)


class Point(Strict):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class Coordinate(Strict):
    geometry: Point | None
    precision_status: Precision
    reason: str | None
    geo_evidence_id: UUID | None
    checked_at: datetime | None


class Status(Strict):
    inventory_kind: Literal["regular", "unfit"]
    physical_vacancy: Literal["yes", "no", "unknown"]
    tender_active: Literal["yes", "no", "unknown"]
    activity_allowed: Literal["yes", "no", "unknown"]
    technical_suitable: Literal["yes", "no", "unknown"]
    candidate_status: CandidateStatus
    reasons: list[str]
    checked_at: datetime | None
    evidence_url: str | None
    tender_url: str | None
    valid_until: datetime | None
    evaluated_at: datetime


class SpaceSummary(Strict):
    space_id: str
    address: str
    area: Metric
    position_code: Literal["street", "other"] | None
    position_reason: str | None
    district_id: str | None
    district_name: str | None
    district_assignment: Literal["confirmed", "source_name", "boundary_review", "missing"]
    coordinate: Coordinate
    status: Status
    reference_period: str | None
    historical_inventory: bool


class SpaceList(Strict):
    dataset_bundle_id: UUID
    profile: ProfileCode
    items: list[SpaceSummary]
    total: int
    page: int
    page_size: int
    without_usable_coordinate: int
    warnings: list[str]


class DescriptionTag(Strict):
    """A tag from the official description that a team member approved. Not scored."""

    tag: str
    label: str
    value: int | None
    method: Literal["rule", "model"]
    reviewed_at: datetime


class SpaceDetail(Strict):
    dataset_bundle_id: UUID
    space: SpaceSummary
    radius_m: Literal[500, 1000]
    metrics: dict[str, Metric]
    source_versions: dict[str, UUID]
    attribution: list[str]
    context_count: int
    description_tags: list[DescriptionTag]
    description_tags_pending: int = Field(ge=0)


CompetitorCategory = Literal["cafe", "bar", "pub", "fast_food", "bakery", "hairdresser", "beauty"]


class Competitor(Strict):
    osm_type: Literal["node", "way", "relation"]
    osm_id: int = Field(ge=1)
    name: str | None
    category: CompetitorCategory
    coordinate: Point
    distance_m: float = Field(ge=0)
    lifecycle_status: Literal["mapped_active", "unknown"]


class CompetitionResponse(Strict):
    """OSM objects near a space: informative only, never scored until coverage is approved."""

    dataset_bundle_id: UUID
    space_id: str
    source_version_id: UUID | None
    radius_m: Literal[500, 1000]
    count: int | None = Field(ge=0)
    counts_by_category: dict[str, int | None]
    area_km2: float = Field(gt=0)
    density_per_km2: float | None = Field(ge=0)
    coverage_status: Literal["unchecked", "approved", "partial", "unavailable"]
    reason: str | None
    checked_at: datetime | None
    items: list[Competitor]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    warnings: list[str]


class ProfileSuggestionRequest(Strict):
    description: str = Field(min_length=5, max_length=500)

    @field_validator("description")
    @classmethod
    def _plain_text(cls, value: str) -> str:
        text = " ".join(value.split())
        if len(text) < 5:
            raise ValueError("Opis mora imati barem 5 znakova.")
        return text


class ProfileCandidate(Strict):
    profile: ProfileCode
    similarity: float = Field(ge=-1, le=1)
    matched_example: str


class ProfileSuggestion(Strict):
    """A suggestion only; the user always confirms (FZ25). Never changes any score."""

    suggested_profile: ProfileCode | None
    status: Literal["suggested", "unsupported"]
    requires_confirmation: Literal[True] = True
    candidates: list[ProfileCandidate]
    min_similarity: float
    min_margin: float
    method: str
    model_id: str
    model_revision: str
    config_sha256: str


class BriefDistrict(Strict):
    district_id: str
    name: str
    words: str


class BriefPriority(Strict):
    criterion: Literal["transit", "universities", "culture", "parking", "schools", "area", "street"]
    level: Literal[0, 3]
    words: str


class ContextLocation(Strict):
    kind: Literal["district", "street", "stop", "point", "area"]
    label: str
    district_ids: list[str]


class ContextCard(Strict):
    """Reviewed by a person (FZ17). Context only: it never changes any score (FZ16)."""

    card_id: UUID
    version: int
    status: Literal["approved"] = "approved"
    topic: Literal["traffic_works", "public_projects_services", "events"]
    summary: str
    location: ContextLocation
    source_url: str
    publisher: str
    published_date: date | None
    valid_from: datetime | None
    valid_to: datetime | None
    review_due_at: datetime | None
    temporal_label: Literal["announced", "current", "date_not_confirmed"]
    approved_at: datetime


class ContextList(Strict):
    dataset_bundle_id: UUID
    space_id: str
    profile: ProfileCode
    items: list[ContextCard]
    total: int
    pending_review: int


class BusinessBrief(Strict):
    """Proposals from the user's description. Nothing applies until the user confirms it."""

    suggestion: ProfileSuggestion
    area_m2: float | None
    budget_eur: float | None
    districts: list[BriefDistrict]
    priorities: list[BriefPriority]
    notices: list[ContextCard]


class RentStats(Strict):
    contracts: int
    median_eur_per_m2: float | None
    p25_eur_per_m2: float | None
    p75_eur_per_m2: float | None


class MarketDistrict(Strict):
    district_id: str
    name: str
    competitors: int | None
    competitors_per_km2: float | None
    rent: RentStats


class MarketSummary(Strict):
    """Context only (ADR24). Not scored and not a price offer for any space."""

    dataset_bundle_id: UUID
    profile: ProfileCode
    competitor_categories: list[str]
    city_rent: RentStats
    districts: list[MarketDistrict]
    lease_source_version_id: UUID | None
    lease_reference_period: str | None
    pending_notices: int
    warnings: list[str]


class RankingRequest(Strict):
    profile: ProfileCode
    profile_version: UUID
    dataset_bundle_id: UUID
    space_ids: list[SpaceId] = Field(min_length=1, max_length=500)
    target_area_m2: float | None = Field(default=None, gt=0, le=100000)
    radius_m: Literal[500, 1000] = 500
    prefer_lower_competition: bool
    include_conditional: bool
    weights: Weights | None = None
    missing_policy: Literal["require_ack"]
    comparison_basis_token: str | None = Field(default=None, min_length=20, max_length=2048)
    basis_choice: Literal["common_criteria", "remove_incomplete"] | None = None

    @field_validator("space_ids")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("space_ids ne smije sadržavati duplikate")
        return value


class ExcludedCriterion(Strict):
    criterion: Criterion
    reason: str


class RankingItem(Strict):
    space_id: str
    candidate_status: CandidateStatus
    rank: int | None
    score: float | None
    reason: str | None
    reasons: list[str]
    raw_metrics: dict[str, Metric]
    utilities: dict[str, float]
    contributions: dict[str, float]
    status_snapshot: Status
    coordinate_snapshot: Coordinate


class RankingResponse(Strict):
    ranking_run_id: UUID
    dataset_bundle_id: UUID
    profile: ProfileCode
    profile_version: UUID
    config_version: str
    source_versions: dict[str, UUID]
    comparison_basis_id: str
    criteria_used: list[Criterion]
    excluded_criteria: list[ExcludedCriterion]
    coverage_active: float
    coverage_default_profile: float
    radius_m: Literal[500, 1000]
    target_area_m2: float
    items: list[RankingItem]
    created_at: datetime
    expires_at: datetime
    historical: bool
    warnings: list[str]
    access_token: str | None = None


class SourcePublic(Strict):
    source_code: str
    name: str
    publisher: str
    catalog_url: str | None
    license_id: str
    attribution: str
    active_source_version_id: UUID | None
    reference_period: str | None
    fetched_at: datetime | None
    last_checked_at: datetime | None
    availability: Literal["available", "unavailable", "disabled"]
    limitations: list[str]


class SourceList(Strict):
    dataset_bundle_id: UUID
    items: list[SourcePublic]
