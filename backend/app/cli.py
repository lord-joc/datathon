"""ProstorIQ command line. Run inside the api container:

    docker compose run --rm api python -m app.cli <command>

Commands
  migrate                 apply database migrations (owner role)
  db-check                check the API role connection
  sources-load            load config/source_registry*.json into the database
  source-resources CODE   list CKAN resources of a source (to confirm resource_id)
  import CODE [--file F]  import one source (network, or a manually downloaded file)
  import-all              import D01-D07 and the team additions that have a resource
  sources-status          latest version, record count and last job per source
"""

import argparse
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from app.adapters.ckan import fetch_package
from app.adapters.http import FetchError, SafeFetcher
from app.adapters.registry import Registry, load_registry
from app.core.config import get_settings
from app.pipeline.importer import ImportBusyError, Importer, ImportOutcome, sync_sources

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_IMPORT_ORDER = ("D07", "D01", "D02", "D03", "D04", "D05", "D06", "D14", "D17", "D18")


def _owner_url() -> str:
    """Migrations run as the owner/migration role, never as the API role."""
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        sys.exit("MIGRATION_DATABASE_URL nije postavljen.")
    return url


def _pipeline_engine() -> Engine:
    url = get_settings().pipeline_database_url
    if not url:
        sys.exit("PIPELINE_DATABASE_URL nije postavljen.")
    return create_engine(
        url,
        connect_args={"connect_timeout": 5, "application_name": "prostoriq-pipeline"},
    )


def _registry() -> Registry:
    return load_registry(get_settings().config_dir)


def _alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def cmd_migrate(_: argparse.Namespace) -> int:
    command.upgrade(_alembic_config(_owner_url()), "head")
    print("Migracije su primijenjene.")
    return 0


def cmd_db_check(_: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url, connect_args={"connect_timeout": 5})
    with engine.connect() as conn:
        who = conn.execute(text("SELECT current_user")).scalar_one()
        postgis = conn.execute(text("SELECT postgis_lib_version()")).scalar_one()
        tables = conn.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'prostoriq'")
        ).scalar_one()
    print(f"Spojen kao: {who}")
    print(f"PostGIS: {postgis}")
    print(f"Tablica u shemi prostoriq: {tables}")
    return 0


def cmd_sources_load(_: argparse.Namespace) -> int:
    registry = _registry()
    with _pipeline_engine().begin() as conn:
        count = sync_sources(conn, registry)
    print(f"Učitano izvora iz registra: {count}")
    return 0


def cmd_source_resources(args: argparse.Namespace) -> int:
    registry = _registry()
    spec = registry.get(args.code)
    if not spec.metadata_endpoint:
        print(
            f"{spec.code} nema CKAN metapodatke; URL iz registra: {', '.join(spec.resource_urls)}"
        )
        return 0
    with SafeFetcher(registry.allowed_hosts) as fetcher:
        package = fetch_package(fetcher, spec.metadata_endpoint)
    print(f"Paket: {package.package_id} ({package.title})")
    print(f"Licenca: {package.license_id} / {package.license_title}")
    for res in package.resources:
        marker = "  <- u registru" if res.resource_id == spec.resource_id else ""
        print(f"- {res.resource_id}  [{res.format}]  {res.name}{marker}\n    {res.url}")
    return 0


def _print_outcome(o: ImportOutcome) -> None:
    label = {
        "succeeded": "USPJEH",
        "awaiting_review": "ČEKA PREGLED",
        "failed": "NEUSPJEH",
    }.get(o.status, o.status.upper())
    detail = "bez promjene" if o.unchanged else f"{o.record_count} zapisa"
    if o.status == "failed":
        detail = f"kod {o.error_code}"
    reused = " (ponovljen isti zahtjev)" if o.reused_job else ""
    print(f"[{o.source_code}] {label}: {detail}{reused}  job={o.job_id}")
    for message in o.errors[:10]:
        print(f"    greška: {message}")
    for message in o.warnings[:10]:
        print(f"    upozorenje: {message}")


def _run_import(
    importer: Importer, fetcher: SafeFetcher, code: str, file: Path | None, key: str
) -> ImportOutcome | None:
    try:
        return importer.run(code, idempotency_key=key, fetcher=fetcher, local_file=file)
    except ImportBusyError as exc:
        print(f"[{code}] SOURCE_BUSY: {exc}")
    except ValueError as exc:
        print(f"[{code}] {exc}")
    return None


def cmd_import(args: argparse.Namespace) -> int:
    settings = get_settings()
    registry = _registry()
    engine = _pipeline_engine()
    with engine.begin() as conn:
        sync_sources(conn, registry)
    importer = Importer(engine, registry, settings.raw_storage_dir)
    file = Path(args.file) if args.file else None
    if file is not None and not file.is_file():
        sys.exit(f"Datoteka ne postoji: {file}")
    key = args.key or f"cli-{uuid.uuid4()}"
    with SafeFetcher(registry.allowed_hosts) as fetcher:
        outcome = _run_import(importer, fetcher, args.code, file, key)
    if outcome is None:
        return 1
    _print_outcome(outcome)
    return 0 if outcome.status in {"succeeded", "awaiting_review"} else 1


def cmd_import_all(_: argparse.Namespace) -> int:
    settings = get_settings()
    registry = _registry()
    engine = _pipeline_engine()
    with engine.begin() as conn:
        sync_sources(conn, registry)
    importer = Importer(engine, registry, settings.raw_storage_dir)
    day = datetime.now(UTC).strftime("%Y%m%d")
    failures = 0
    with SafeFetcher(registry.allowed_hosts) as fetcher:
        for code in DEFAULT_IMPORT_ORDER:
            if code not in registry.sources:
                continue
            outcome = _run_import(
                importer, fetcher, code, None, f"import-all-{day}-{uuid.uuid4().hex[:8]}"
            )
            if outcome is None:
                failures += 1
                continue
            _print_outcome(outcome)
            failures += outcome.status == "failed"
    print(f"Gotovo. Neuspjelih izvora: {failures}")
    return 0 if failures == 0 else 1


def cmd_sources_status(_: argparse.Namespace) -> int:
    with _pipeline_engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT s.source_code, s.name,
                       v.record_count, v.quality_status, v.fetched_at, v.last_checked_at,
                       j.status AS job_status, j.error_code
                FROM prostoriq.source s
                LEFT JOIN LATERAL (
                    SELECT * FROM prostoriq.source_version sv
                    WHERE sv.source_code = s.source_code ORDER BY fetched_at DESC LIMIT 1
                ) v ON true
                LEFT JOIN LATERAL (
                    SELECT * FROM prostoriq.import_job ij
                    WHERE ij.source_code = s.source_code ORDER BY requested_at DESC LIMIT 1
                ) j ON true
                ORDER BY s.source_code
                """
            )
        ).all()
    print(f"{'Izvor':<6} {'Zapisa':>6}  {'Kvaliteta':<16} {'Zadnji posao':<16} Naziv")
    for r in rows:
        count = "-" if r.record_count is None else str(r.record_count)
        job = (r.job_status or "-") + (f" ({r.error_code})" if r.error_code else "")
        print(f"{r.source_code:<6} {count:>6}  {(r.quality_status or '-'):<16} {job:<16} {r.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="ProstorIQ CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="Primijeni sve migracije baze").set_defaults(func=cmd_migrate)
    sub.add_parser("db-check", help="Provjeri vezu API uloge s bazom").set_defaults(
        func=cmd_db_check
    )
    sub.add_parser("sources-load", help="Učitaj registar izvora u bazu").set_defaults(
        func=cmd_sources_load
    )
    res = sub.add_parser("source-resources", help="Prikaži CKAN resurse izvora")
    res.add_argument("code")
    res.set_defaults(func=cmd_source_resources)
    imp = sub.add_parser("import", help="Uvezi jedan izvor")
    imp.add_argument("code")
    imp.add_argument("--file", help="Ručno preuzeta datoteka umjesto dohvata s mreže")
    imp.add_argument("--key", help="Idempotency-Key (isti ključ vraća isti posao)")
    imp.set_defaults(func=cmd_import)
    sub.add_parser("import-all", help="Uvezi sve podržane izvore").set_defaults(func=cmd_import_all)
    sub.add_parser("sources-status", help="Stanje izvora i zadnjih uvoza").set_defaults(
        func=cmd_sources_status
    )
    args = parser.parse_args(argv)
    try:
        result: int = args.func(args)
    except FetchError as exc:
        print(f"Dohvat nije uspio ({exc.code}): {exc.detail}")
        return 1
    except KeyError as exc:
        print(str(exc.args[0]) if exc.args else str(exc))
        return 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
