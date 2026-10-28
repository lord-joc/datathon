# ProstorIQ

Web aplikacija koja poduzetnicima pomaže usporediti gradske poslovne prostore u Zagrebu na temelju otvorenih podataka (data.gov.hr, Geoportal Grada Zagreba, OpenStreetMap). Datathon Portala otvorenih podataka 2026, izazov C.

**Stanje:** isječak 2. Uz Docker okruženje, bazu, API skelet i prvi korak Vodiča (isječak 1) postoji uvoz otvorenih podataka: D01/D02 preko CKAN API-ja data.gov.hr, prostorni slojevi D03–D07 te autobusna stajališta, vrtići i škole (D14, D17, D18). Geokodiranje i metrike dolaze u isječku 3.

## Stack

| Sloj | Tehnologija |
|---|---|
| API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 Core, Alembic |
| Baza | PostgreSQL 16 + PostGIS 3.5 |
| Frontend | React 18, TypeScript (strict), Vite 7, React Router 7, TanStack Query, Zustand, Tailwind CSS |
| Web poslužitelj | Caddy 2: statički frontend, `/api` proxy, HTTPS, sigurnosna zaglavlja |
| Kvaliteta | ruff, mypy, pytest, ESLint, Prettier, Vitest, pip-audit, npm audit |

## Pokretanje (Windows CMD)

Potrebno: Docker Desktop (pokrenut), Git, Python 3.12, Node 24, uv.

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

**3. Migracije baze** (stvara 31 tablicu, uloge i ovlasti):

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
- Promjena broja zapisa veća od 20 % ili neprepoznata licenca stavlja verziju u status **ČEKA PREGLED**.
- Izvorne datoteke čuvaju se po SHA-256 u volumenu `raw_data`.

**Novi izvori (D14 autobusi, D17 vrtići, D18 škole):** njihov `resource_id` još nije potvrđen. Prvo pogledaj resurse:

```cmd
docker compose run --rm cli python -m app.cli source-resources D14
```

Ako paket ima točno jedan GeoJSON resurs, uvoz ga sam odabere. Ako ih ima više, upiši odabrani `resource_id` u `config/source_registry_extra.json`.

**Ručno preuzeta datoteka** (ako portal ne radi ili blokira automatski dohvat): spremi datoteku u `data\manual\` i pokreni:

```cmd
docker compose run --rm cli python -m app.cli import D01 --file /app/manual/prazni-poslovni-prostori-2024.csv
```

**Host nije dopušten:** dohvat smije ići samo na hostove iz `allowed_hosts` u `config/source_registry_extra.json`. Ako preuzimanje javi `host_not_allowed` za neki ArcGIS ili gradski host, provjeri gdje pokazuje i tek ga onda dodaj.

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

- Uvoz se izvodi kao `prostoriq_pipeline`: smije dodavati verzije i zapise, a na postojećoj verziji smije mijenjati samo `last_checked_at` i `quality_status`.
- Dohvat izvora: samo HTTPS, popis dopuštenih hostova, provjera svakog preusmjeravanja i odbijanje privatnih adresa (zaštita od SSRF-a), ograničenje veličine i vremena, ponavljanje samo za 408/429/5xx. ZIP se raspakirava u memoriji, bez `..`, apsolutnih putanja i symlinkova.
- API se na bazu spaja kao `prostoriq_api`. Ta uloga ima samo `SELECT` i `INSERT` na snapshote rangiranja, ne vidi admin tablice i ne može mijenjati povijesne zapise.
- Caddy postavlja CSP, HSTS (na HTTPS-u), `X-Frame-Options`, `Permissions-Policy` i ostala zaglavlja. Frontend i API su na istom originu, bez CORS-a u produkciji.
- Fontovi se poslužuju lokalno, bez trećih strana. Vite ne ugrađuje resurse kao `data:` URI-je, pa CSP ostaje strog.
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

## Licenca

Kod: MIT. Podaci zadržavaju vlastite licence (Otvorena dozvola RH, ODbL za OpenStreetMap). Popis je na ekranu „Izvori podataka”.
