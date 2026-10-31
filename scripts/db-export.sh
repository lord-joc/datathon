#!/bin/sh
# Export the ProstorIQ data (schema "prostoriq" + Alembic version) from the running compose DB.
# Usage (repo root, Linux/macOS or Git Bash): sh scripts/db-export.sh [out.dump]
# The dump holds only public open data and pipeline records; it never contains passwords
# (login roles are created on the target by db/init/10-roles.sh from its own .env).
set -eu

out="${1:-prostoriq.dump}"
docker compose exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner -n prostoriq -n public' \
  > "$out"
size=$(wc -c < "$out")
if [ "$size" -lt 1000000 ]; then
  echo "Izvoz je premalen ($size B); provjeri da baza radi." >&2
  exit 1
fi
if command -v sha256sum >/dev/null 2>&1; then sha256sum "$out"; fi
echo "Spremljeno: $out ($size B)"
