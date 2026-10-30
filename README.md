# ProstorIQ

Web aplikacija koja poduzetnicima pomaže usporediti gradske poslovne prostore u Zagrebu na temelju otvorenih podataka (data.gov.hr, Geoportal Grada Zagreba, OpenStreetMap). Datathon Portala otvorenih podataka 2026, izazov C.

**Stanje:** isječak 4.

- **Isječak 1:** Docker okruženje, baza, API skelet i prvi korak Vodiča.
- **Isječak 2:** uvoz otvorenih podataka. D01/D02 dolaze preko CKAN API-ja data.gov.hr, uz prostorne slojeve D03–D07 te autobusna stajališta, vrtiće i škole (D14, D17, D18).
- **Isječak 3:** geokodiranje prostora (OSM adrese D19, timska provjera D11), konkurencija (D08), sirove prostorne metrike i paket podataka.
- **Isječak 4:** rangiranje kao čista funkcija (7 profila, zajednički kriteriji, potvrda nove osnove usporedbe) i javni API: profili, četvrti, prostori, detalj, izračun i izvori.

Sljedeći je isječak 5 (frontend s kartom). Odluke su u [`docs/adr/`](docs/adr/README.md).

## Stack

| Sloj | Tehnologija |
|---|---|
| API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 Core, Alembic |
| Baza | PostgreSQL 16 + PostGIS 3.5 |
| Frontend | React 18, TypeScript (strict), Vite 7, React Router 7, TanStack Query, Zustand, Tailwind CSS |
| Web poslužitelj | Caddy 2: statički frontend, `/api` proxy, HTTPS, sigurnosna zaglavlja |
| Kvaliteta | ruff, mypy, pytest, ESLint, Prettier, Vitest, pip-audit, npm audit |

## Pokretanje (Windows CMD)

Potrebno: Docker Desktop (pokrenut) i Git. Za lokalni razvoj i provjere još i Python 3.12, uv i Node 24 (CI koristi Node 24; najmanje podržana verzija je 20.19).

**1. Tajne.** Kopiraj predložak:

```cmd
copy .env.example .env
```

Generiraj **četiri** različite vrijednosti (pokreni naredbu četiri puta):

```cmd
py -c "import secrets; print(secrets.token_hex(24))"
```

Otvori `.env` u VS Codeu (`code .env`) i zamijeni svaku vrijednost `promijeni_me` jednom od generiranih (`POSTGRES_PASSWORD`, `API_DB_PASSWORD`, `PIPELINE_DB_PASSWORD`, `APP_HMAC_SECRET`).

**2. Pokreni sve servise:**

```cmd
docker compose up -d --build
```

**3. Migracije baze** (stvara 32 tablice u shemi `prostoriq`, uloge i ovlasti):

```cmd
docker compose run --rm cli python -m app.cli migrate
```

**4. Provjera da API vidi bazu kao ograničena uloga:**

```cmd
docker compose run --rm cli python -m app.cli db-check
```

Očekivano: `Spojen kao: prostoriq_api` i verzija PostGIS-a.

**5. Otvori u pregledniku:**

- aplikacija: http://localhost:8080
- status: http://localhost:8080/api/v1/status (očekivano `"database": "up"`, `"dataset_ready": false`)
- API dokumentacija (samo lokalno): http://localhost:8000/api/docs

## Uvoz otvorenih podataka

Migracije i uvoz pokreće servis `cli`. Samo on ima lozinke vlasnika baze i uloge `pipeline`; javni `api` ih nema.

**Svi podržani izvori odjednom:**

```cmd
docker compose run --rm cli python -m app.cli import-all
docker compose run --rm cli python -m app.cli sources-status
```

**Jedan izvor:**

```cmd
docker compose run --rm cli python -m app.cli import D01
```

Što se događa:
- D01/D02 se pronalaze preko CKAN `package_show` na data.gov.hr. Resurs se potvrđuje po `resource_id` iz registra, a datoteka se preuzima s URL-a iz metapodataka.
- Isti sadržaj ne stvara novu verziju („bez promjene”), a isti `--key` vraća isti posao.
- Neuspjeli uvoz (npr. promijenjeno zaglavlje) zapisuje grešku i ne dira postojeće podatke.
- Promjena broja zapisa veća od 20 % ili neprepoznata licenca stavlja verziju u status **ČEKA PREGLED**. Takva se verzija ne koristi i blokira nove uvoze tog izvora dok netko ne odluči:
  ```cmd
  docker compose run --rm cli python -m app.cli reviews
  docker compose run --rm cli python -m app.cli source-review <posao> --approve --reason "Popis je stvarno skraćen"
  docker compose run --rm cli python -m app.cli source-review <posao> --reject --reason "Pogrešna datoteka"
  ```
  Odluka i razlog bilježe se u `audit_event`. Kod odbijanja ostaje prethodna valjana verzija.
- Izvorne datoteke čuvaju se po SHA-256 u volumenu `raw_data`.

**Novi izvori (D14 autobusi, D17 vrtići, D18 škole):** `resource_id` je potvrđen 28. 10. 2026. i upisan u `config/source_registry_extra.json`. D14 i D18 su GeoJSON. Za D17 koristimo SHP (ZIP), jer resurs označen kao GeoJSON zapravo vraća Esri File Geodatabase. Ako portal promijeni resurse, uvoz javlja `resource_missing`. Tada pogledaj resurse i upiši novi `resource_id`:

```cmd
docker compose run --rm cli python -m app.cli source-resources D14
```

Registar se u bazu učitava sam pri svakom uvozu. `sources-load` učitava registar i **profile djelatnosti** (`config/profiles.json`). Pokreni ga nakon `migrate` i nakon svake promjene profila. Promjena težina traži novu oznaku `version` u datoteci, jer se izračuni vežu uz točnu verziju profila.

**Ručno preuzeta datoteka** (ako portal ne radi ili blokira automatski dohvat): spremi datoteku u `data\manual\` i pokreni:

```cmd
docker compose run --rm cli python -m app.cli import D01 --file /app/manual/prazni-poslovni-prostori-2024.csv
```

**Host nije dopušten:** dohvat smije ići samo na hostove iz `allowed_hosts` u `config/source_registry_extra.json`: `data.gov.hr`, `data.zagreb.hr` i `opendata.arcgis.com`. Ako preuzimanje javi `host_not_allowed`, provjeri gdje URL pokazuje i dodaj **točno taj host**. Nemoj dodavati cijelu domenu `.arcgis.com`, jer na njezinim poddomenama svatko može objaviti sadržaj.

## Lokacije, metrike i paket podataka

Zagrebački popis prostora ima samo adresu, bez koordinata. Lokaciju dobivamo u tri razine (ADR18):

| Razina | Izvor | Ulazi u metrike |
|---|---|---|
| `entrance_confirmed` | D11, tim provjerio ulaz | da |
| `building_approximate` | D19, OSM adresa zgrade | da |
| `needs_review` / `missing` | nesiguran ili nepostojeći pogodak | ne, vrijednost ostaje „nepoznato” |

**1. OSM (jednom, ~200 MB):**

```cmd
curl -L -o data\manual\croatia-latest.osm.pbf https://download.geofabrik.de/europe/croatia-latest.osm.pbf
docker compose run --rm cli python -m app.cli osm-import --file /app/manual/croatia-latest.osm.pbf
```

Iz iste datoteke nastaju D19 (adrese) i D08 (kafići, barovi, pekare, frizeri…). Datoteka se čita samo u obuhvatu Zagreba.

**2. Geokodiranje i popis za ručnu provjeru:**

```cmd
docker compose run --rm cli python -m app.cli geocode
docker compose run --rm -T cli python -m app.cli geocode-review > data\manual\d11.csv
```

`-T` je obavezan da izlaz ne dobije terminalne znakove. Logovi idu na stderr, pa ne završavaju u datoteci.

`d11.csv` sadrži prostore koje nismo sigurno smjestili. Datoteka ima razdjelnik `;` i UTF-8 BOM, pa se u Excelu s hrvatskim postavkama otvara dvoklikom, u stupcima i s ispravnim dijakriticima.

Za svaki provjereni prostor upiši:
- `lon` i `lat` (decimalni zarez je u redu),
- `precision_status`: `entrance_confirmed` ili `building_approximate`,
- dokaz u `evidence_url` ili `evidence_note`, npr. „Obilazak tima, ulaz iz dvorišta”,
- `checked_at`, npr. `27.10.2026.` ili `2026-10-27`.

Stupac `auto_note` samo je pomoć (adresa i razlog zašto automatsko uparivanje nije uspjelo). Ne računa se kao dokaz, pa redak bez vlastitog dokaza bude odbijen. Odbijen je i redak s upisanim koordinatama ako je `precision_status` ostao `needs_review` ili `missing`. Neispunjeni redci se preskaču. Spremi kao „CSV (razdvojeno točkom sa zarezom)”.

```cmd
docker compose run --rm cli python -m app.cli import-coordinates --file /app/manual/d11.csv
```

Ponovno geokodiranje provjerava sve prostore i zapisuje novi redak samo kad se rezultat promijeni. Najnoviji rezultat iste verzije D19 zamjenjuje stariji, pa ispravak uparivanja ispravlja i krivu točku. Ako se ista adresa nalazi na mjestima udaljenima više od 500 m (npr. dvije Ulice Slavka Kolara), odlučuje četvrt iz popisa. Ako ona ne može odlučiti, prostor ide na ručnu provjeru.

**3. Paket i aktivacija:**

```cmd
docker compose run --rm cli python -m app.cli bundle-build
docker compose run --rm cli python -m app.cli bundle-activate
docker compose run --rm cli python -m app.cli bundles
```

`bundle-build` (opcionalno `--label "opis"`) uzima zadnju valjanu verziju svakog izvora. Dodjeljuje gradsku četvrt: točkom u poligonu, a inače po nazivu iz popisa. Zatim računa sirove metrike za radijuse 500 i 1000 m: udaljenost do stajališta javnog prijevoza (tramvaj D03 i autobus D14) i do parkinga, broj fakulteta, kulturnih ustanova te škola i vrtića (D17 + D18) u 600 m, površinu i položaj. Udaljenosti su zračne. Konkurencija se broji, ali ne boduje dok pokrivenost OSM-a nije pregledana. Trošak je „nije dostupno”, nikad 0 EUR. Isti skup verzija izvora i odabranih dokaza o lokaciji ne stvara novi paket. Novo geokodiranje ili D11 stvaraju novi paket. `bundle-activate` aktivira najnoviji valjani paket, a `--id <uuid>` određeni paket. Aktivacija je atomska i bilježi se u `audit_event`. Nakon nje `/api/v1/status` javlja `dataset_ready: true`. Povratak na raniji paket: `bundle-activate --id <uuid>` (popis daje `bundles`).

## Rangiranje i javni API

Formule su u `backend/app/ranking/` (čista funkcija, bez baze), težine u `config/profiles.json`, a konstante u `config/ranking_config.json` (ADR19). Kontrolni primjer iz specifikacije, kafić u prostoru 4763, daje **90,55**.

| Ruta | Što vraća |
|---|---|
| `GET /api/v1/profiles` | 7 profila s težinama i verzijom (ETag) |
| `GET /api/v1/districts` | 17 četvrti aktivnog paketa |
| `GET /api/v1/spaces?profile=cafe` | filtri: `area_min_m2`, `area_max_m2`, `district_ids`, `include_conditional`, `include_excluded`, `page`, `page_size` (≤ 100) |
| `GET /api/v1/spaces/{id}?profile=cafe&radius_m=500` | detalj s metrikama, izvorima i razlozima kad vrijednost nedostaje |
| `POST /api/v1/rankings` | novi nepromjenjiv izračun (do 500 prostora): `201` + `access_token`, `409`, `422` |
| `GET /api/v1/rankings/{id}` | spremljeni izračun, uz zaglavlje `X-Ranking-Token` |
| `GET /api/v1/sources` | izvori, licence, datumi i ograničenja |

Kad kriterij nedostaje samo dijelu prostora, `POST /rankings` vraća `409 COMPARISON_BASIS_CHANGED`, s popisom što nedostaje i potpisanim tokenom. Klijent ponavlja zahtjev s `comparison_basis_token` i `basis_choice`: `common_criteria` (svi prostori, manja pokrivenost) ili `remove_incomplete` (bez nepotpunih). Token vrijedi 10 minuta i samo za taj zahtjev. Interaktivna dokumentacija je na http://localhost:8000/api/docs (samo lokalno).

## Razvoj frontenda s automatskim osvježavanjem

Docker drži bazu i API, a Vite poslužuje frontend:

```cmd
cd frontend
npm ci
npm run dev
```

Otvori http://localhost:5173. Zahtjevi na `/api` idu na API na portu 8000.

## Provjere prije commita

Backend:

```cmd
cd backend
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

Frontend:

```cmd
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

Iste provjere, uz stvarne migracije na PostGIS-u, pokreće GitHub Actions na svakom pushu (`.github/workflows/ci.yml`).

## Česti problemi

- **`failed to connect to the docker API`**: Docker Desktop nije pokrenut. Otvori ga i pričekaj „Engine running”.
- **Promijenio sam lozinke u `.env`, a baza ih ne prihvaća**: korisnici baze stvaraju se samo pri prvom pokretanju. Obriši bazu i kreni ispočetka (briše sve lokalne podatke):
  ```cmd
  docker compose down -v
  docker compose up -d --build
  docker compose run --rm cli python -m app.cli migrate
  ```
- **Port 8080, 8000 ili 5432 je zauzet**: zaustavi drugu aplikaciju na tom portu ili promijeni lijevi broj u `compose.yaml` (npr. `"8081:80"`).

## Sigurnost (sažetak)

- Uvoz se izvodi kao `prostoriq_pipeline`: smije dodavati verzije i zapise, a na postojećoj verziji smije mijenjati samo `last_checked_at` i `quality_status` (odluka `source-review`).
- Pristupni token izračuna vraća se samo jednom, a u bazi je samo njegov SHA-256. Potvrda nove osnove usporedbe potpisana je s `APP_HMAC_SECRET`, koji u produkciji mora imati barem 32 znaka.
- Dohvat izvora: samo HTTPS, popis dopuštenih hostova, provjera svakog preusmjeravanja i odbijanje privatnih adresa (zaštita od SSRF-a), ograničenje veličine i vremena, ponavljanje samo za 408/429/5xx. ZIP se raspakirava u memoriji, bez `..`, apsolutnih putanja i symlinkova.
- API se na bazu spaja kao `prostoriq_api`. Ta uloga ima samo `SELECT` i `INSERT` na snapshote rangiranja, ne vidi admin tablice i ne može mijenjati povijesne zapise.
- Caddy postavlja CSP, HSTS (na HTTPS-u), `X-Frame-Options`, `Permissions-Policy` i ostala zaglavlja. Frontend i API su na istom originu, bez CORS-a u produkciji.
- CSP dopušta skripte samo s vlastitog originala. Slike su dopuštene s vlastitog originala te kao `data:` i `blob:`, jer ih MapLibre koristi za sprite i ikone. Vlastiti resursi nikad se ne ugrađuju kao `data:` URI-ji (Vite `assetsInlineLimit: 0`). Stilovi dopuštaju `'unsafe-inline'`, jer ga trebaju React `style` atributi i MapLibre.
- Fontovi (`@fontsource`) se poslužuju lokalno, bez trećih strana.
- Greške se vraćaju kao RFC 9457 `problem+json`, bez stack traceova. Logovi su JSON, bez lozinki, tokena i IP adresa.
- `.env` se nikad ne commita.

## Struktura

```text
backend/    FastAPI aplikacija, migracije, CLI, testovi
frontend/   React SPA, Caddyfile, PWA manifest
config/     registar izvora, profili djelatnosti, AI i ranking konfiguracija
db/init/    jednokratna skripta za korisnike baze
docs/       ugovori (OpenAPI, sheme, sljedivost) i ADR-ovi
```

`docs/contracts/` je **ciljni** ugovor za MVP. `openapi.yaml` opisuje sve planirane rute. Implementirane su `health`, `status` i javne rute iz isječka 4 (vidi gore), a ostale dolaze s isječcima koji ih uvode.

## Licenca

Kod: MIT. Podaci zadržavaju vlastite licence (Otvorena dozvola RH, ODbL za OpenStreetMap). Popis je na ekranu „Izvori podataka”.
