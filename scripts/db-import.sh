#!/bin/sh
# Restore a dump from scripts/db-export.sh into a NEW, empty compose database.
# Usage (repo root): sh scripts/db-import.sh prostoriq.dump
# Refuses to run when the target already has a "prostoriq" schema, so it can never overwrite data.
set -eu

dump="${1:?Navedi datoteku izvoza, npr. prostoriq.dump}"
[ -f "$dump" ] || { echo "Nema datoteke $dump" >&2; exit 1; }

psql_db() {
  docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "$0"' "$1"
}

if [ "$(psql_db "select count(*) from pg_namespace where nspname = 'prostoriq'")" != "0" ]; then
  echo "Baza već ima shemu prostoriq. Uvoz je samo za praznu bazu; ništa nije promijenjeno." >&2
  exit 1
fi

# Extensions the schema relies on (the PostGIS image creates postgis itself).
psql_db "CREATE EXTENSION IF NOT EXISTS pgcrypto;"

# One transaction: any error leaves the database as empty as before. The "public" schema
# already exists in the PostGIS image, so its CREATE entry is left out of the restore list.
docker compose exec -T db sh -c 'cat > /tmp/prostoriq.dump' < "$dump"
docker compose exec -T db sh -c '
  set -eu
  pg_restore -l /tmp/prostoriq.dump | grep -v " SCHEMA - public " > /tmp/prostoriq.list
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error \
    --single-transaction -L /tmp/prostoriq.list /tmp/prostoriq.dump
  rm -f /tmp/prostoriq.dump /tmp/prostoriq.list
'

echo "Migracija: $(psql_db 'select version_num from public.alembic_version')"
echo "Aktivni paket: $(psql_db 'select dataset_bundle_id from prostoriq.active_dataset')"
echo "Prostora u paketu: $(psql_db 'select count(*) from prostoriq.bundle_space b join prostoriq.active_dataset a using (dataset_bundle_id)')"
