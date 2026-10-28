-- ProstorIQ 3.0.0. Predložena početna migracija; nije implementacija aplikacije.
-- Cilj PostgreSQL 16 i PostGIS 3.5. Izvoditi kao migration role, ne javni API role.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS prostoriq;
SET search_path TO prostoriq, public;

CREATE TABLE admin_user (
 admin_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 username text NOT NULL UNIQUE CHECK (length(username) BETWEEN 3 AND 100),
 password_hash text NOT NULL,
 enabled boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE admin_session (
 session_hash char(64) PRIMARY KEY CHECK (session_hash ~ '^[0-9a-f]{64}$'),
 admin_id uuid NOT NULL REFERENCES admin_user ON DELETE CASCADE,
 csrf_hash char(64) NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 last_seen_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL,
 revoked_at timestamptz,
 CHECK (expires_at > created_at)
);
CREATE INDEX admin_session_expiry_idx ON admin_session(expires_at);

CREATE TABLE source (
 source_code text PRIMARY KEY CHECK (source_code ~ '^(D[0-9]{2}|M01)$'),
 name text NOT NULL,
 publisher text NOT NULL,
 catalog_url text,
 adapter_code text NOT NULL,
 policy jsonb NOT NULL CHECK (jsonb_typeof(policy)='object'),
 policy_sha256 char(64) NOT NULL,
 license_id text NOT NULL,
 attribution text NOT NULL,
 enabled boolean NOT NULL DEFAULT true,
 version integer NOT NULL DEFAULT 1 CHECK (version > 0),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE import_job (
 job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 source_code text NOT NULL REFERENCES source,
 kind text NOT NULL CHECK (kind IN ('source_import','ai_process','demo_check')),
 status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','validating','awaiting_review','succeeded','failed','cancelled')),
 idempotency_key text NOT NULL,
 request_sha256 char(64) NOT NULL,
 request_json jsonb NOT NULL,
 requested_by uuid REFERENCES admin_user,
 requested_at timestamptz NOT NULL DEFAULT now(),
 started_at timestamptz,
 finished_at timestamptz,
 lease_owner text,
 lease_until timestamptz,
 heartbeat_at timestamptz,
 fencing_token bigint NOT NULL DEFAULT 0,
 attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
 accepted_count integer NOT NULL DEFAULT 0 CHECK (accepted_count >= 0),
 rejected_count integer NOT NULL DEFAULT 0 CHECK (rejected_count >= 0),
 error_code text,
 report jsonb NOT NULL DEFAULT '{}'::jsonb,
 UNIQUE(source_code,idempotency_key)
);
CREATE UNIQUE INDEX one_active_source_job ON import_job(source_code)
 WHERE status IN ('queued','running','validating','awaiting_review');
CREATE INDEX queued_jobs_idx ON import_job(requested_at) WHERE status='queued';
CREATE TABLE import_error (
 error_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 job_id uuid NOT NULL REFERENCES import_job,
 source_record_key text,
 code text NOT NULL,
 field_name text,
 detail text NOT NULL,
 severity text NOT NULL CHECK (severity IN ('warning','blocking')),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE source_version (
 source_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 source_code text NOT NULL REFERENCES source,
 job_id uuid REFERENCES import_job,
 resource_id text,
 download_url text NOT NULL,
 sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
 metadata_sha256 char(64) NOT NULL CHECK (metadata_sha256 ~ '^[0-9a-f]{64}$'),
 license_id text NOT NULL,
 policy_sha256 char(64) NOT NULL,
 reference_period text,
 source_modified_at timestamptz,
 fetched_at timestamptz NOT NULL,
 last_checked_at timestamptz NOT NULL,
 raw_storage_key text NOT NULL,
 manifest jsonb NOT NULL,
 record_count integer NOT NULL CHECK (record_count >= 0),
 quality_status text NOT NULL CHECK (quality_status IN ('staged','awaiting_review','valid','rejected')),
 coverage_geom geometry(MultiPolygon,4326),
 UNIQUE(source_code,sha256,metadata_sha256),
 UNIQUE(source_version_id,source_code)
);
CREATE TABLE source_record (
 source_record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 source_version_id uuid NOT NULL REFERENCES source_version,
 natural_key text NOT NULL,
 record_sha256 char(64) NOT NULL,
 raw_values jsonb NOT NULL CHECK (jsonb_typeof(raw_values)='object'),
 UNIQUE(source_version_id,natural_key)
);
CREATE TABLE space (
 space_id text PRIMARY KEY CHECK (space_id ~ '^[0-9]+$'),
 issuer_code text NOT NULL DEFAULT 'CITY_ZAGREB',
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE space_revision (
 space_revision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 space_id text NOT NULL REFERENCES space,
 source_version_id uuid NOT NULL REFERENCES source_version,
 source_record_id uuid NOT NULL REFERENCES source_record,
 inventory_kind text NOT NULL CHECK (inventory_kind IN ('regular','unfit')),
 address text NOT NULL CHECK (length(address)>0),
 district_name_source text,
 area_m2 numeric(12,2) CHECK (area_m2 > 0),
 position_code text CHECK (position_code IN ('street','other')),
 position_source text,
 structure_description text,
 usage_code_source text,
 UNIQUE(space_id,source_version_id),
 UNIQUE(space_revision_id,space_id)
);
CREATE TABLE geo_evidence (
 geo_evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 space_id text NOT NULL REFERENCES space,
 source_version_id uuid NOT NULL REFERENCES source_version,
 geom geometry(Point,4326),
 precision_status text NOT NULL CHECK (precision_status IN ('entrance_confirmed','building_approximate','needs_review','missing')),
 evidence_url text,
 evidence_note text,
 checked_at timestamptz NOT NULL,
 checked_by uuid REFERENCES admin_user,
 license_id text NOT NULL,
 CHECK ((precision_status IN ('entrance_confirmed','building_approximate') AND geom IS NOT NULL) OR precision_status IN ('needs_review','missing')),
 CHECK (geom IS NULL OR (ST_X(geom) BETWEEN -180 AND 180 AND ST_Y(geom) BETWEEN -90 AND 90)),
 UNIQUE(geo_evidence_id,space_id)
);
CREATE INDEX geo_evidence_geog_idx ON geo_evidence USING gist ((geom::geography));
CREATE TABLE status_assessment (
 assessment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 space_id text NOT NULL REFERENCES space,
 source_version_id uuid NOT NULL REFERENCES source_version,
 profile_code text NOT NULL CHECK (profile_code IN ('cafe','office')),
 physical_vacancy text NOT NULL DEFAULT 'unknown' CHECK (physical_vacancy IN ('yes','no','unknown')),
 tender_active text NOT NULL DEFAULT 'unknown' CHECK (tender_active IN ('yes','no','unknown')),
 activity_allowed text NOT NULL DEFAULT 'unknown' CHECK (activity_allowed IN ('yes','no','unknown')),
 technical_suitable text NOT NULL DEFAULT 'unknown' CHECK (technical_suitable IN ('yes','no','unknown')),
 tender_url text,
 evidence_url text NOT NULL,
 checked_at timestamptz NOT NULL,
 checked_by uuid REFERENCES admin_user,
 monthly_total_eur numeric(12,2) CHECK (monthly_total_eur >= 0),
 valid_until timestamptz,
 cost_definition_version text,
 cost_evidence jsonb,
 CHECK (monthly_total_eur IS NULL OR (cost_definition_version IS NOT NULL AND cost_evidence IS NOT NULL)),
 CHECK (valid_until IS NULL OR valid_until>checked_at),
 CHECK (valid_until IS NULL OR valid_until<=checked_at+interval '168 hours'),
 CHECK ((physical_vacancy<>'yes' AND tender_active<>'yes' AND activity_allowed<>'yes' AND technical_suitable<>'yes') OR valid_until IS NOT NULL),
 UNIQUE(assessment_id,space_id,profile_code)
);
CREATE TABLE district (
 source_version_id uuid NOT NULL REFERENCES source_version,
 district_id text NOT NULL,
 name text NOT NULL,
 geom geometry(MultiPolygon,4326) NOT NULL,
 PRIMARY KEY(source_version_id,district_id),
 CHECK (ST_IsValid(geom))
);
CREATE INDEX district_geom_idx ON district USING gist(geom);
CREATE TABLE spatial_feature (
 source_version_id uuid NOT NULL REFERENCES source_version,
 feature_key text NOT NULL,
 category text NOT NULL CHECK (category IN ('transit','university','culture','parking')),
 name text,
 address text,
 geom geometry(Point,4326) NOT NULL,
 properties jsonb NOT NULL DEFAULT '{}'::jsonb,
 PRIMARY KEY(source_version_id,feature_key)
);
CREATE INDEX spatial_feature_geog_idx ON spatial_feature USING gist ((geom::geography));
CREATE INDEX spatial_feature_category_idx ON spatial_feature(category,source_version_id);
CREATE TABLE competitor (
 source_version_id uuid NOT NULL REFERENCES source_version,
 osm_type text NOT NULL CHECK (osm_type IN ('node','way','relation')),
 osm_id bigint NOT NULL CHECK (osm_id>0),
 category text NOT NULL CHECK (category IN ('cafe','bar','pub')),
 name text,
 normalized_name text,
 address text,
 normalized_address text,
 geom geometry(Point,4326) NOT NULL,
 original_geom geometry(Geometry,4326),
 lifecycle_status text NOT NULL CHECK (lifecycle_status IN ('mapped_active','closed','disused','proposed','construction','unknown')),
 tags jsonb NOT NULL,
 osm_timestamp timestamptz,
 PRIMARY KEY(source_version_id,osm_type,osm_id)
);
CREATE INDEX competitor_geog_idx ON competitor USING gist ((geom::geography));
CREATE TABLE competitor_resolution (
 resolution_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 source_version_id uuid NOT NULL,
 osm_type text NOT NULL,
 osm_id bigint NOT NULL,
 decision text NOT NULL CHECK (decision IN ('keep','duplicate','closed','needs_review')),
 canonical_osm_type text,
 canonical_osm_id bigint,
 reason text NOT NULL,
 checked_by uuid REFERENCES admin_user,
 checked_at timestamptz NOT NULL,
 FOREIGN KEY(source_version_id,osm_type,osm_id) REFERENCES competitor,
 FOREIGN KEY(source_version_id,canonical_osm_type,canonical_osm_id) REFERENCES competitor,
 CHECK (decision<>'duplicate' OR (canonical_osm_type IS NOT NULL AND canonical_osm_id IS NOT NULL)),
 CHECK (decision<>'duplicate' OR (canonical_osm_type,canonical_osm_id)<>(osm_type,osm_id)),
 UNIQUE(source_version_id,osm_type,osm_id,checked_at)
);
CREATE TABLE coverage_review (
 coverage_review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 source_version_id uuid NOT NULL REFERENCES source_version,
 space_id text NOT NULL REFERENCES space,
 geo_evidence_id uuid NOT NULL,
 radius_m integer NOT NULL CHECK (radius_m IN (500,1000)),
 complete_circle boolean NOT NULL,
 sample_size integer NOT NULL CHECK (sample_size >= 0),
 object_count integer NOT NULL CHECK (object_count >= 0),
 unresolved_duplicate_count integer NOT NULL DEFAULT 0 CHECK (unresolved_duplicate_count>=0),
 status text NOT NULL CHECK (status IN ('unchecked','approved','rejected')),
 checked_by uuid REFERENCES admin_user,
 checked_at timestamptz,
 note text,
 FOREIGN KEY(geo_evidence_id,space_id) REFERENCES geo_evidence(geo_evidence_id,space_id),
 CHECK (status<>'approved' OR (complete_circle AND sample_size>=LEAST(10,object_count) AND unresolved_duplicate_count=0 AND checked_at IS NOT NULL AND checked_by IS NOT NULL))
);
CREATE TABLE dataset_bundle (
 dataset_bundle_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 label text NOT NULL,
 manifest_sha256 char(64) NOT NULL UNIQUE,
 status text NOT NULL CHECK (status IN ('draft','validating','valid','rejected')),
 version integer NOT NULL DEFAULT 1,
 validation_sha256 char(64),
 validation_report jsonb NOT NULL DEFAULT '{}'::jsonb,
 created_at timestamptz NOT NULL DEFAULT now(),
 created_by uuid REFERENCES admin_user
);
CREATE TABLE bundle_source (
 dataset_bundle_id uuid NOT NULL REFERENCES dataset_bundle,
 source_code text NOT NULL REFERENCES source,
 source_version_id uuid NOT NULL,
 PRIMARY KEY(dataset_bundle_id,source_code),
 FOREIGN KEY(source_version_id,source_code) REFERENCES source_version(source_version_id,source_code)
);
CREATE TABLE bundle_space (
 dataset_bundle_id uuid NOT NULL REFERENCES dataset_bundle,
 space_id text NOT NULL REFERENCES space,
 space_revision_id uuid NOT NULL,
 geo_evidence_id uuid,
 district_id text,
 district_assignment text NOT NULL CHECK (district_assignment IN ('confirmed','source_name','boundary_review','missing')),
 PRIMARY KEY(dataset_bundle_id,space_id),
 FOREIGN KEY(space_revision_id,space_id) REFERENCES space_revision(space_revision_id,space_id),
 FOREIGN KEY(geo_evidence_id,space_id) REFERENCES geo_evidence(geo_evidence_id,space_id)
);
CREATE TABLE bundle_status (
 dataset_bundle_id uuid NOT NULL,
 space_id text NOT NULL,
 profile_code text NOT NULL CHECK (profile_code IN ('cafe','office')),
 assessment_id uuid NOT NULL,
 PRIMARY KEY(dataset_bundle_id,space_id,profile_code),
 FOREIGN KEY(dataset_bundle_id,space_id) REFERENCES bundle_space,
 FOREIGN KEY(assessment_id,space_id,profile_code) REFERENCES status_assessment(assessment_id,space_id,profile_code)
);
CREATE TABLE active_dataset (
 singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
 dataset_bundle_id uuid NOT NULL REFERENCES dataset_bundle,
 activated_at timestamptz NOT NULL DEFAULT now(),
 activated_by uuid REFERENCES admin_user
);
CREATE TABLE spatial_metric (
 dataset_bundle_id uuid NOT NULL,
 space_id text NOT NULL,
 radius_m integer NOT NULL CHECK (radius_m IN (500,1000)),
 criterion text NOT NULL CHECK (criterion IN ('transit','universities','culture','parking','area','street','competition','cost')),
 value numeric,
 unit text NOT NULL,
 reason text,
 evidence jsonb NOT NULL,
 PRIMARY KEY(dataset_bundle_id,space_id,radius_m,criterion),
 FOREIGN KEY(dataset_bundle_id,space_id) REFERENCES bundle_space,
 CHECK ((value IS NULL AND reason IS NOT NULL) OR (value IS NOT NULL AND reason IS NULL))
);
CREATE TABLE notice (
 notice_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 source_code text NOT NULL REFERENCES source,
 canonical_url text NOT NULL UNIQUE,
 first_seen_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE notice_revision (
 notice_revision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 notice_id uuid NOT NULL REFERENCES notice,
 source_version_id uuid NOT NULL REFERENCES source_version,
 title text NOT NULL,
 published_date date,
 published_at timestamptz,
 clean_text text NOT NULL CHECK (length(clean_text)>0),
 content_sha256 char(64) NOT NULL,
 extraction_evidence jsonb NOT NULL,
 reuse_policy_sha256 char(64) NOT NULL,
 UNIQUE(notice_id,content_sha256,reuse_policy_sha256)
);
CREATE TABLE ai_result (
 ai_result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 notice_revision_id uuid NOT NULL REFERENCES notice_revision,
 job_id uuid NOT NULL REFERENCES import_job,
 model_id text NOT NULL,
 model_revision text NOT NULL,
 config_sha256 char(64) NOT NULL,
 pipeline_version text NOT NULL,
 topic text CHECK (topic IN ('traffic_works','public_projects_services','events','irrelevant')),
 status text NOT NULL CHECK (status IN ('classified','uncertain','irrelevant')),
 topic_scores jsonb NOT NULL,
 profile_scores jsonb NOT NULL,
 evidence_spans jsonb NOT NULL,
 processed_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(notice_revision_id,model_revision,config_sha256,pipeline_version)
);
CREATE TABLE context_card (
 card_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 ai_result_id uuid NOT NULL REFERENCES ai_result,
 notice_revision_id uuid NOT NULL REFERENCES notice_revision,
 status text NOT NULL DEFAULT 'pending_review' CHECK (status IN ('pending_review','approved','rejected','needs_review','expired','archived')),
 version integer NOT NULL DEFAULT 1 CHECK (version>0),
 topic text NOT NULL CHECK (topic IN ('traffic_works','public_projects_services','events')),
 profile_codes jsonb NOT NULL CHECK (jsonb_typeof(profile_codes)='array'),
 summary text NOT NULL,
 location_kind text CHECK (location_kind IN ('district','street','stop','point','area')),
 location_label text,
 location_geom geometry(Geometry,4326),
 district_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
 location_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
 valid_from timestamptz,
 valid_to timestamptz,
 review_due_at timestamptz,
 approved_at timestamptz,
 approved_by uuid REFERENCES admin_user,
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK (valid_from IS NULL OR valid_to IS NULL OR valid_to>valid_from),
 CHECK (status<>'approved' OR (approved_at IS NOT NULL AND approved_by IS NOT NULL AND location_kind IS NOT NULL AND location_label IS NOT NULL AND (valid_to IS NOT NULL OR review_due_at IS NOT NULL)))
);
CREATE INDEX context_card_geom_idx ON context_card USING gist(location_geom);
CREATE INDEX context_card_public_idx ON context_card(status,valid_to,review_due_at);
CREATE TABLE criteria_profile (
 profile_version uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 profile_code text NOT NULL CHECK (profile_code IN ('cafe','office')),
 version_label text NOT NULL,
 config_sha256 char(64) NOT NULL UNIQUE,
 weights jsonb NOT NULL,
 target_area_m2 numeric NOT NULL CHECK (target_area_m2>0),
 config jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 created_by uuid REFERENCES admin_user,
 UNIQUE(profile_code,version_label)
);
CREATE TABLE ranking_run (
 ranking_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 dataset_bundle_id uuid NOT NULL REFERENCES dataset_bundle,
 profile_version uuid NOT NULL REFERENCES criteria_profile,
 request_sha256 char(64) NOT NULL,
 request_json jsonb NOT NULL,
 comparison_basis_id char(64) NOT NULL,
 criteria_used jsonb NOT NULL,
 excluded_criteria jsonb NOT NULL,
 coverage_active numeric(7,4) NOT NULL CHECK (coverage_active BETWEEN 0 AND 100),
 coverage_default_profile numeric(7,4) NOT NULL CHECK (coverage_default_profile BETWEEN 0 AND 100),
 config_snapshot jsonb NOT NULL,
 source_versions jsonb NOT NULL,
 access_token_hash char(64) NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL DEFAULT (now()+interval '90 days')
);
CREATE TABLE ranking_item (
 ranking_run_id uuid NOT NULL REFERENCES ranking_run ON DELETE CASCADE,
 space_id text NOT NULL REFERENCES space,
 candidate_status text NOT NULL CHECK (candidate_status IN ('ready','conditional','excluded')),
 rank integer CHECK (rank>0),
 score numeric(12,8) CHECK (score BETWEEN 0 AND 100),
 reasons jsonb NOT NULL,
 raw_metrics jsonb NOT NULL,
 utilities jsonb NOT NULL,
 contributions jsonb NOT NULL,
 status_snapshot jsonb NOT NULL,
 coordinate_snapshot jsonb NOT NULL,
 PRIMARY KEY(ranking_run_id,space_id)
);
CREATE TABLE error_report (
 report_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 target_type text NOT NULL CHECK (target_type IN ('space','competitor')),
 target_id text NOT NULL,
 description text NOT NULL CHECK (length(description) BETWEEN 10 AND 2000),
 contact_ciphertext bytea,
 status text NOT NULL DEFAULT 'new' CHECK (status IN ('new','reviewed','resolved','rejected')),
 created_at timestamptz NOT NULL DEFAULT now(),
 resolved_at timestamptz
);
CREATE TABLE audit_event (
 audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 actor_admin_id uuid REFERENCES admin_user,
 action text NOT NULL,
 entity_type text NOT NULL,
 entity_id text NOT NULL,
 request_id uuid NOT NULL,
 before_value jsonb,
 after_value jsonb NOT NULL,
 reason text NOT NULL,
 occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_entity_idx ON audit_event(entity_type,entity_id,occurred_at);

-- Zaštita povijesnih paketa i izračuna: aplikacijski role dobiva INSERT/SELECT,
-- a ne UPDATE/DELETE na source_record, space_revision, geo_evidence,
-- status_assessment, criteria_profile, ranking_run i ranking_item.
-- Purge retention operacija koristi odvojeni maintenance role i audit događaj.
-- Dodatne provjere u servisu prije aktivacije:
-- 1. Svaka referencirana verzija ima source_version.quality_status='valid'.
-- 2. Geometrije, statusi i metrike pripadaju verzijama bundle_source manifesta.
-- 3. D01 i D02 nemaju neriješen zajednički space_id.
-- 4. profile weights sadrže točno 8 kriterija, zbroj 100 i office competition=0.
-- 5. Sve javne kartice imaju <=60 riječi i valjan lokacijski dokaz.
-- 6. Pri promjeni manifesta invalidirati validation_sha256 i ponoviti validaciju.
