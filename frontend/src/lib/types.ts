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

export interface SpaceDetail {
  dataset_bundle_id: string;
  space: SpaceSummary;
  radius_m: Radius;
  metrics: Record<Criterion, Metric>;
  source_versions: Record<string, string>;
  attribution: string[];
  context_count: number;
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
