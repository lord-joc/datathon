"""ProstorIQ command line. Run in the cli container (the only one with owner/pipeline roles):

    docker compose run --rm cli python -m app.cli <command>

Commands
  migrate                 apply database migrations (owner role)
  db-check                check the API role connection
  sources-load            load config/source_registry*.json and config/profiles.json
  source-resources CODE   list CKAN resources of a source (to confirm resource_id)
  import CODE [--file F]  import one source (network, or a manually downloaded file)
  import-all              import D01-D07 and the team additions that have a resource
  sources-status          latest version, record count and last job per source
  reviews                 imports waiting for a human decision (awaiting_review)
  source-review JOB --approve|--reject --reason TEXT   decide on such an import
  osm-import --file F     D08 competitors + D19 address points from one Geofabrik PBF
  import-coordinates --file F   D11 team-checked coordinates (CSV)
  geocode                 match D01/D02 addresses to D19 address points
  geocode-review          D11 template (';' CSV with BOM on stdout) for a manual check
  tender-template         D12 template: every D01 space, to fill rents from city tenders
  import-tenders --file F D12 rents and conditions read from zagreb.hr tenders (CSV)
  bundle-build [--label]  build and validate a dataset bundle with spatial metrics
  bundle-activate [--id]  make a valid bundle the active one (default: newest valid)
  bundles                 list bundles and the active one
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
from app.pipeline.bundle import BundleError, activate_bundle, build_bundle
from app.pipeline.geocode import geocode_spaces, review_csv
from app.pipeline.importer import ImportBusyError, Importer, ImportOutcome, sync_sources
from app.pipeline.profiles import ProfileVersionError, sync_profiles
from app.pipeline.review import ReviewError, pending_reviews, review_import
from app.pipeline.tenders import tender_template_csv
from app.ranking.config import load_profiles

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
    profiles = load_profiles(get_settings().config_dir)
    try:
        with _pipeline_engine().begin() as conn:
            count = sync_sources(conn, registry)
            created = sync_profiles(conn, profiles)
    except ProfileVersionError as exc:
        print(str(exc))
        return 1
    print(f"Učitano izvora iz registra: {count}")
    print(f"Profili verzije {profiles.version}: {len(profiles.profiles)} ({created} novih)")
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
    if o.status == "awaiting_review":
        print(
            "    Verzija se ne koristi dok je netko ne odobri: "
            f'python -m app.cli source-review {o.job_id} --approve|--reject --reason "..."'
        )


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


def _local_import(code: str, file_arg: str, key: str | None) -> ImportOutcome | None:
    settings = get_settings()
    registry = _registry()
    engine = _pipeline_engine()
    with engine.begin() as conn:
        sync_sources(conn, registry)
    file = Path(file_arg)
    if not file.is_file():
        sys.exit(f"Datoteka ne postoji: {file}")
    importer = Importer(engine, registry, settings.raw_storage_dir)
    with SafeFetcher(registry.allowed_hosts) as fetcher:
        return _run_import(importer, fetcher, code, file, key or f"cli-{uuid.uuid4()}")


def cmd_osm_import(args: argparse.Namespace) -> int:
    print("Čitam OSM PBF (Hrvatska, može potrajati 1-3 minute)...")
    failures = 0
    for code in ("D19", "D08"):
        outcome = _local_import(code, args.file, None)
        if outcome is None:
            failures += 1
            continue
        _print_outcome(outcome)
        failures += outcome.status == "failed"
    return 0 if failures == 0 else 1


def cmd_import_coordinates(args: argparse.Namespace) -> int:
    outcome = _local_import("D11", args.file, args.key)
    if outcome is None:
        return 1
    _print_outcome(outcome)
    return 0 if outcome.status in {"succeeded", "awaiting_review"} else 1


def cmd_import_tenders(args: argparse.Namespace) -> int:
    outcome = _local_import("D12", args.file, args.key)
    if outcome is None:
        return 1
    _print_outcome(outcome)
    if outcome.status == "succeeded":
        print("Zatim: bundle-build pa bundle-activate, da cijene vidi aplikacija.")
    return 0 if outcome.status in {"succeeded", "awaiting_review"} else 1


def cmd_tender_template(_: argparse.Namespace) -> int:
    sys.stdout.write("﻿" + tender_template_csv(_pipeline_engine()))
    return 0


def cmd_geocode(_: argparse.Namespace) -> int:
    try:
        report = geocode_spaces(_pipeline_engine())
    except RuntimeError as exc:
        print(str(exc))
        return 1
    print(f"Adresnih točaka u D19: {report.address_points}")
    print(f"Obrađeno prostora: {report.processed} (već obrađeno ranije: {report.skipped_existing})")
    labels = {
        "building_approximate": "približno (zgrada)",
        "needs_review": "za ručnu provjeru",
        "missing": "nije pronađeno",
    }
    for key, label in labels.items():
        print(f"  {label:<22} {report.by_precision.get(key, 0)}")
    if report.by_method:
        print("Način: " + ", ".join(f"{k}={v}" for k, v in sorted(report.by_method.items())))
    return 0


def cmd_geocode_review(_: argparse.Namespace) -> int:
    # BOM: Excel otherwise reads UTF-8 as Windows-1250 and breaks Č/Ć/Š/Ž in addresses.
    sys.stdout.write("\ufeff" + review_csv(_pipeline_engine()))
    return 0


def cmd_bundle_build(args: argparse.Namespace) -> int:
    try:
        result = build_bundle(_pipeline_engine(), args.label)
    except BundleError as exc:
        print(str(exc))
        return 1
    state = "novi paket" if result.created else "isti paket već postoji"
    print(f"Paket {result.bundle_id}: {result.status} ({state})")
    r = result.report
    if "error" in r:
        print(f"  greška: {r['error']} {r.get('space_ids', '')}")
        return 1
    loc = r["location"]
    print(f"  prostora: {r['spaces']['total']} {r['spaces']['by_inventory']}")
    print(f"  lokacija upotrebljiva: {loc['usable']} ({loc['usable_pct']} %) {loc['by_precision']}")
    print(f"  četvrti: {r['district_assignment']}")
    for criterion, counts in r["metrics_with_value_r500"].items():
        print(f"  metrika {criterion:<13} s vrijednošću {counts['with_value']}/{counts['total']}")
    print("Aktiviraj: python -m app.cli bundle-activate")
    return 0


def cmd_bundle_activate(args: argparse.Namespace) -> int:
    try:
        bundle_id = activate_bundle(_pipeline_engine(), args.id)
    except BundleError as exc:
        print(str(exc))
        return 1
    print(f"Aktivni paket: {bundle_id}")
    return 0


def cmd_bundles(_: argparse.Namespace) -> int:
    with _pipeline_engine().connect() as conn:
        active = conn.execute(
            text("SELECT dataset_bundle_id::text FROM prostoriq.active_dataset")
        ).scalar_one_or_none()
        rows = conn.execute(
            text(
                "SELECT dataset_bundle_id::text, status, created_at, label "
                "FROM prostoriq.dataset_bundle ORDER BY created_at DESC LIMIT 20"
            )
        ).all()
    for r in rows:
        marker = "  <- aktivan" if r[0] == active else ""
        print(f"{r[0]}  {r[1]:<10} {r[2]:%Y-%m-%d %H:%M}  {r[3]}{marker}")
    if not rows:
        print("Nema paketa.")
    return 0


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


def cmd_reviews(_: argparse.Namespace) -> int:
    pending = pending_reviews(_pipeline_engine())
    if not pending:
        print("Nijedan uvoz ne čeka pregled.")
        return 0
    for p in pending:
        print(f"{p.job_id}  {p.source_code}  zapisa: {p.record_count}")
        for warning in p.warnings:
            print(f"    {warning}")
    print('Odluka: python -m app.cli source-review <posao> --approve|--reject --reason "..."')
    return 0


def cmd_source_review(args: argparse.Namespace) -> int:
    try:
        outcome = review_import(
            _pipeline_engine(), args.job, approve=args.approve, reason=args.reason
        )
    except ReviewError as exc:
        print(str(exc))
        return 1
    if outcome.decision == "approved":
        print(f"[{outcome.source_code}] Odobreno: verzija {outcome.source_version_id} je valjana.")
        print("Sljedeći korak: python -m app.cli bundle-build")
    else:
        print(f"[{outcome.source_code}] Odbijeno: ostaje prethodna valjana verzija.")
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
    sub.add_parser("reviews", help="Uvozi koji čekaju pregled").set_defaults(func=cmd_reviews)
    rev = sub.add_parser("source-review", help="Odobri ili odbij uvoz koji čeka pregled")
    rev.add_argument("job")
    decision = rev.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve", action="store_true")
    decision.add_argument("--reject", action="store_true")
    rev.add_argument("--reason", required=True, help="Zašto (zapisuje se u audit)")
    rev.set_defaults(func=cmd_source_review)
    osm = sub.add_parser("osm-import", help="Uvezi D08 i D19 iz Geofabrik PBF-a")
    osm.add_argument("--file", required=True)
    osm.set_defaults(func=cmd_osm_import)
    coords = sub.add_parser("import-coordinates", help="Uvezi D11 provjerene koordinate")
    coords.add_argument("--file", required=True)
    coords.add_argument("--key")
    coords.set_defaults(func=cmd_import_coordinates)
    tenders = sub.add_parser("import-tenders", help="Uvezi D12 zakupnine iz natječaja")
    tenders.add_argument("--file", required=True)
    tenders.add_argument("--key")
    tenders.set_defaults(func=cmd_import_tenders)
    sub.add_parser("tender-template", help="D12 predložak za upis zakupnina").set_defaults(
        func=cmd_tender_template
    )
    sub.add_parser("geocode", help="Geokodiraj prostore na D19").set_defaults(func=cmd_geocode)
    sub.add_parser("geocode-review", help="D11 predložak za ručnu provjeru").set_defaults(
        func=cmd_geocode_review
    )
    build = sub.add_parser("bundle-build", help="Izgradi paket i metrike")
    build.add_argument("--label")
    build.set_defaults(func=cmd_bundle_build)
    act = sub.add_parser("bundle-activate", help="Aktiviraj paket")
    act.add_argument("--id")
    act.set_defaults(func=cmd_bundle_activate)
    sub.add_parser("bundles", help="Popis paketa").set_defaults(func=cmd_bundles)
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
