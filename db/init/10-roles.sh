#!/bin/sh
# Runs ONCE, when the database volume is first created (postgis image entrypoint).
# Creates login users for the API and the pipeline. Privileges come from the
# group roles created by migration 0002, so membership is granted here up front.
set -eu

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v api_password="$API_DB_PASSWORD" \
  -v pipeline_password="$PIPELINE_DB_PASSWORD" <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_read') THEN CREATE ROLE app_read NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_ranking_write') THEN CREATE ROLE app_ranking_write NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pipeline') THEN CREATE ROLE pipeline NOLOGIN; END IF;
END
$$;

SELECT format('CREATE ROLE prostoriq_api LOGIN PASSWORD %L', :'api_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'prostoriq_api') \gexec
SELECT format('CREATE ROLE prostoriq_pipeline LOGIN PASSWORD %L', :'pipeline_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'prostoriq_pipeline') \gexec

GRANT app_read, app_ranking_write TO prostoriq_api;
GRANT pipeline TO prostoriq_pipeline;
ALTER ROLE prostoriq_api SET search_path = prostoriq, public;
ALTER ROLE prostoriq_pipeline SET search_path = prostoriq, public;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL
