/** Public API shapes (docs/contracts/openapi.yaml v3.1). */

export type ProfileCode =
  | "cafe"
  | "office"
  | "retail"
  | "food_takeaway"
  | "personal_care"
  | "education"
  | "workshop";

export const CRITERIA = [
  "transit",
  "universities",
  "culture",
  "parking",
  "schools",
  "area",
  "street",
  "competition",
  "cost",
] as const;
export type Criterion = (typeof CRITERIA)[number];
export type Weights = Record<Criterion, number>;

export type CandidateStatus = "ready" | "conditional" | "excluded";
export type Precision = "entrance_confirmed" | "building_approximate" | "needs_review" | "missing";
export type Tri = "yes" | "no" | "unknown";
export type Radius = 500 | 1000;

export interface Profile {
  profile: ProfileCode;
  profile_version: string;
  version_label: string;
  name: string;
  summary: string;
  icon: string;
  target_area_m2: number;
  weights: Weights;
  competitor_categories: string[];
  config_version: string;
  cost_enabled: boolean;
}

export interface District {
  district_id: string;
  name: string;
}

export interface MetricDetail {
  name?: string;
  mode?: string;
  distance?: string;
  nearest_names?: string[];
  radius_m?: number;
  counts?: Record<string, number>;
  total?: number;
  /** Cost from a city tender (D12): starting monthly rent, evidence link, check time. */
  basis?: "tender_start_monthly";
  tender_url?: string;
  checked_at?: string;
  note?: string | null;
}

export interface Metric {
  value: number | null;
  unit: "m" | "count" | "m2" | "objects_per_km2" | "eur_month" | "utility";
  reason: string | null;
  source_version_ids: string[];
  detail: MetricDetail;
}

export interface Coordinate {
  geometry: { type: "Point"; coordinates: [number, number] } | null;
  precision_status: Precision;
  reason: string | null;
  geo_evidence_id: string | null;
  checked_at: string | null;
}

export interface Status {
  inventory_kind: "regular" | "unfit";
  physical_vacancy: Tri;
  tender_active: Tri;
  activity_allowed: Tri;
  technical_suitable: Tri;
  candidate_status: CandidateStatus;
  reasons: string[];
  checked_at: string | null;
  evidence_url: string | null;
  tender_url: string | null;
  valid_until: string | null;
  evaluated_at: string;
}

export interface SpaceSummary {
  space_id: string;
  address: string;
  area: Metric;
  position_code: "street" | "other" | null;
  position_reason: string | null;
  district_id: string | null;
  district_name: string | null;
  district_assignment: "confirmed" | "source_name" | "boundary_review" | "missing";
  coordinate: Coordinate;
  status: Status;
  reference_period: string | null;
  historical_inventory: boolean;
}

export interface SpaceList {
  dataset_bundle_id: string;
  profile: ProfileCode;
  items: SpaceSummary[];
  total: number;
  page: number;
  page_size: number;
  without_usable_coordinate: number;
  warnings: string[];
}

export type CompetitorCategory =
  | "cafe"
  | "bar"
  | "pub"
  | "fast_food"
  | "bakery"
  | "hairdresser"
  | "beauty";

export interface Competitor {
  osm_type: "node" | "way" | "relation";
  osm_id: number;
  name: string | null;
  category: CompetitorCategory;
  coordinate: { type: "Point"; coordinates: [number, number] };
  distance_m: number;
  lifecycle_status: "mapped_active" | "unknown";
}

/** OSM objects near a space. Informative only: competition is never scored (ADR21). */
export interface CompetitionResponse {
  dataset_bundle_id: string;
  space_id: string;
  source_version_id: string | null;
  radius_m: Radius;
  count: number | null;
  counts_by_category: Partial<Record<CompetitorCategory, number | null>>;
  area_km2: number;
  density_per_km2: number | null;
  coverage_status: "unchecked" | "approved" | "partial" | "unavailable";
  reason: string | null;
  checked_at: string | null;
  items: Competitor[];
  total: number;
  page: number;
  page_size: number;
  warnings: string[];
}

export interface ProfileCandidate {
  profile: ProfileCode;
  similarity: number;
  matched_example: string;
}

/** Local MiniLM suggestion; the user always confirms (ADR21). */
export interface ProfileSuggestion {
  suggested_profile: ProfileCode | null;
  status: "suggested" | "unsupported";
  requires_confirmation: true;
  candidates: ProfileCandidate[];
  min_similarity: number;
  min_margin: number;
  method: string;
  model_id: string;
  model_revision: string;
  config_sha256: string;
}

/** A city notice a team member approved (FZ17). Context only: it never changes a score. */
export interface ContextCard {
  card_id: string;
  version: number;
  status: "approved";
  topic: "traffic_works" | "public_projects_services" | "events";
  summary: string;
  location: {
    kind: "district" | "street" | "stop" | "point" | "area";
    label: string;
    district_ids: string[];
  };
  source_url: string;
  publisher: string;
  published_date: string | null;
  valid_from: string | null;
  valid_to: string | null;
  review_due_at: string | null;
  temporal_label: "announced" | "current" | "date_not_confirmed";
  approved_at: string;
}

export interface ContextList {
  dataset_bundle_id: string;
  space_id: string;
  profile: ProfileCode;
  items: ContextCard[];
  total: number;
  pending_review: number;
}

/** Proposals from a free-text description (ADR24). Nothing applies until the user chooses. */
export interface BusinessBrief {
  suggestion: ProfileSuggestion;
  area_m2: number | null;
  budget_eur: number | null;
  districts: { district_id: string; name: string; words: string }[];
  priorities: { criterion: Criterion; level: 0 | 3; words: string }[];
  notices: ContextCard[];
}

export interface RentStats {
  contracts: number;
  median_eur_per_m2: number | null;
  p25_eur_per_m2: number | null;
  p75_eur_per_m2: number | null;
}

export interface MarketDistrict {
  district_id: string;
  name: string;
  competitors: number | null;
  competitors_per_km2: number | null;
  rent: RentStats;
}

export interface MarketSummary {
  dataset_bundle_id: string;
  profile: ProfileCode;
  competitor_categories: string[];
  city_rent: RentStats;
  districts: MarketDistrict[];
  lease_source_version_id: string | null;
  lease_reference_period: string | null;
  pending_notices: number;
  warnings: string[];
}

/** A tag from the official description that a team member approved (ADR21). Not scored. */
export interface DescriptionTag {
  tag: string;
  label: string;
  value: number | null;
  method: "rule" | "model";
  reviewed_at: string;
}

export interface SpaceDetail {
  dataset_bundle_id: string;
  space: SpaceSummary;
  radius_m: Radius;
  metrics: Record<Criterion, Metric>;
  source_versions: Record<string, string>;
  attribution: string[];
  context_count: number;
  description_tags: DescriptionTag[];
  description_tags_pending: number;
}

export type BasisChoice = "common_criteria" | "remove_incomplete";

export interface RankingRequest {
  profile: ProfileCode;
  profile_version: string;
  dataset_bundle_id: string;
  space_ids: string[];
  target_area_m2?: number;
  radius_m: Radius;
  prefer_lower_competition: boolean;
  include_conditional: boolean;
  weights?: Weights;
  missing_policy: "require_ack";
  comparison_basis_token?: string;
  basis_choice?: BasisChoice;
}

export interface RankingItem {
  space_id: string;
  candidate_status: CandidateStatus;
  rank: number | null;
  score: number | null;
  reason: string | null;
  reasons: string[];
  raw_metrics: Partial<Record<Criterion, Metric>>;
  utilities: Partial<Record<Criterion, number>>;
  contributions: Partial<Record<Criterion, number>>;
  status_snapshot: Status;
  coordinate_snapshot: Coordinate;
}

export interface RankingResponse {
  ranking_run_id: string;
  dataset_bundle_id: string;
  profile: ProfileCode;
  profile_version: string;
  config_version: string;
  source_versions: Record<string, string>;
  comparison_basis_id: string;
  criteria_used: Criterion[];
  excluded_criteria: { criterion: Criterion; reason: string }[];
  coverage_active: number;
  coverage_default_profile: number;
  radius_m: Radius;
  target_area_m2: number;
  items: RankingItem[];
  created_at: string;
  expires_at: string;
  historical: boolean;
  warnings: string[];
  access_token?: string | null;
}

/** Extension members of 409 COMPARISON_BASIS_CHANGED. */
export interface BasisConflict {
  missing_by_space: Record<string, Criterion[]>;
  partial_criteria: Criterion[];
  proposed_criteria: Criterion[];
  options: BasisChoice[];
  comparison_basis_token: string;
  expires_in_s: number;
}

export interface SourcePublic {
  source_code: string;
  name: string;
  publisher: string;
  catalog_url: string | null;
  license_id: string;
  attribution: string;
  active_source_version_id: string | null;
  reference_period: string | null;
  fetched_at: string | null;
  last_checked_at: string | null;
  availability: "available" | "unavailable" | "disabled";
  limitations: string[];
}

export interface SourceList {
  dataset_bundle_id: string;
  items: SourcePublic[];
}

export interface DistrictFeature {
  type: "Feature";
  id: string;
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon;
  properties: { district_id: string; name: string; label_point: [number, number] };
}

export interface DistrictLayer {
  type: "FeatureCollection";
  features: DistrictFeature[];
}

export type PointLayerName = "transit" | "parking" | "universities" | "culture" | "schools";
