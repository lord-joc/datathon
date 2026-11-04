# ProstorIQ

Web aplikacija koja poduzetnicima pomaže usporediti gradske poslovne prostore u Zagrebu na temelju otvorenih podataka (data.gov.hr, Geoportal Grada Zagreba, OpenStreetMap). Datathon Portala otvorenih podataka 2026, izazov C.

**Stanje:** isječak 8. Javna adresa: https://68-210-100-237.sslip.io

- **Isječak 1:** Docker okruženje, baza, API skelet i prvi korak Vodiča.
- **Isječak 2:** uvoz otvorenih podataka. D01/D02 dolaze preko CKAN API-ja data.gov.hr, uz prostorne slojeve D03–D07 te autobusna stajališta, vrtiće i škole (D14, D17, D18).
- **Isječak 3:** geokodiranje prostora (OSM adrese D19, timska provjera D11), konkurencija (D08), sirove prostorne metrike i paket podataka.
- **Isječak 4:** rangiranje kao čista funkcija (7 profila, zajednički kriteriji, potvrda nove osnove usporedbe) i javni API: profili, četvrti, prostori, detalj, izračun i izvori.

- **Isječak 5:** sučelje: Vodič u četiri koraka (živi brojač, razine važnosti, dijalog 409), rezultati s kartom MapLibre, detalj prostora, usporedba do 3 prostora i izvori. Filtri su u URL-u, a pristupni ključ izračuna samo u `sessionStorage`.

- **Isječak 6:** konkurencija iz OSM-a na detalju prostora (samo prikaz, ne boduje se) i lokalni AI: prijedlog djelatnosti iz slobodnog opisa te oznake iz „Opisa strukture” uz ljudsku potvrdu (ADR21).

- **Isječak 7:** ograničenje broja zahtjeva, API bez izlaza na internet, kontrast prema WCAG AA, e2e testovi na desktopu, Androidu i iPhoneu s axe-coreom (ADR22).

- **Isječak 8:** objava na javnoj adresi (Azure for Students, Austria East, 2 vCPU / 4 GB) prema [`docs/deploy.md`](docs/deploy.md): isti paket podataka kao lokalno, HTTPS (Let's Encrypt), dnevna kopija baze. Provjera je u [`docs/evidence/deploy-check.txt`](docs/evidence/deploy-check.txt).

- **Redizajn (ADR23):** svijetli prikaz kao zadani uz automatski tamni, crvena traka s tražilicom prostora i djelatnosti, crveni rub koji prati miš na karticama.

- **Osobni prijedlog i tržište (ADR24):** „Nešto drugo?” iz opisa predlaže djelatnost, površinu, budžet, četvrti i važnost kriterija. Rezultati prikazuju stanje tržišta (OSM i gradske zakupnine), a detalj prostora obavijesti Grada koje je potvrdio član tima. Ništa od toga ne boduje se samo od sebe.

Odluke su u [`docs/adr/`](docs/adr/README.md).

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
- API dokumentacija (samo lokalno): http://localhost:8080/api/docs

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

**2a. Zakupnine iz natječaja Grada (D12, neobavezno):**

```cmd
docker compose run --rm -T cli python -m app.cli tender-template > data\manual\d12.csv
```

Predložak ima jedan redak po prostoru iz popisa (D01). Adresa, četvrt i površina na kraju retka služe samo za snalaženje. Za prostor koji je u natječaju na zagreb.hr upiši:
- `monthly_rent_eur`: početni mjesečni iznos zakupnine iz natječaja, npr. `1.250,00`. Ako ga natječaj ne navodi, ostavi prazno. Nikad ne upisuj procjenu.
- `tender_url`: https poveznica na natječaj na zagreb.hr (drugi hostovi se odbijaju),
- `checked_at`: kad je natječaj pročitan, npr. `30.10.2026.`,
- neobavezno: `profile` (prazno znači sve djelatnosti), `tender_active`, `physical_vacancy`, `activity_allowed`, `technical_suitable` (`da`/`ne`/`nepoznato`) i `evidence_note`.

Neispunjeni redci se preskaču. Upisani `da` vrijedi 7 dana od `checked_at`.

```cmd
docker compose run --rm cli python -m app.cli import-tenders --file /app/manual/d12.csv
```

Zakupnina se ne boduje (ADR20). Prikazuje se uz poveznicu na natječaj i uspoređuje s budžetom korisnika. Nakon uvoza napravi novi paket (korak 3).

**3. Paket i aktivacija:**

```cmd
docker compose run --rm cli python -m app.cli bundle-build
docker compose run --rm cli python -m app.cli bundle-activate
docker compose run --rm cli python -m app.cli bundles
```

`bundle-build` (opcionalno `--label "opis"`) uzima zadnju valjanu verziju svakog izvora. Dodjeljuje gradsku četvrt: točkom u poligonu, a inače po nazivu iz popisa. Zatim računa sirove metrike za radijuse 500 i 1000 m: udaljenost do stajališta javnog prijevoza (tramvaj D03 i autobus D14) i do parkinga, broj fakulteta, kulturnih ustanova te škola i vrtića (D17 + D18) u 600 m, površinu i položaj. Udaljenosti su zračne. Konkurencija se broji, ali ne boduje dok pokrivenost OSM-a nije pregledana. Trošak je zakupnina iz D12 ako je upisana, a inače „nije dostupno”, nikad 0 EUR. Isti skup verzija izvora i odabranih dokaza o lokaciji ne stvara novi paket. Novo geokodiranje ili D11 stvaraju novi paket. `bundle-activate` aktivira najnoviji valjani paket, a `--id <uuid>` određeni paket. Aktivacija je atomska i bilježi se u `audit_event`. Nakon nje `/api/v1/status` javlja `dataset_ready: true`. Povratak na raniji paket: `bundle-activate --id <uuid>` (popis daje `bundles`).

## Rangiranje i javni API

Formule su u `backend/app/ranking/` (čista funkcija, bez baze), težine u `config/profiles.json`, a konstante u `config/ranking_config.json` (ADR19). Kontrolni primjer iz specifikacije, kafić u prostoru 4763, daje **90,55**.

| Ruta | Što vraća |
|---|---|
| `GET /api/v1/profiles` | 7 profila s težinama i verzijom (ETag) |
| `GET /api/v1/districts` | 17 četvrti aktivnog paketa |
| `GET /api/v1/spaces?profile=cafe` | filtri: `area_min_m2`, `area_max_m2`, `district_ids`, `include_conditional`, `include_excluded`, `page`, `page_size` (≤ 100) |
| `GET /api/v1/spaces/{id}?profile=cafe&radius_m=500` | detalj s metrikama, izvorima i razlozima kad vrijednost nedostaje |
| `GET /api/v1/spaces/{id}/competitors?dataset_bundle_id=…&profile=cafe&radius_m=500` | obližnji objekti iz OSM-a (D08) po kategorijama profila, najbliži prvi; samo prikaz, ne boduje se |
| `POST /api/v1/rankings` | novi nepromjenjiv izračun (do 500 prostora): `201` + `access_token`, `409`, `422` |
| `GET /api/v1/rankings/{id}` | spremljeni izračun, uz zaglavlje `X-Ranking-Token` |
| `GET /api/v1/layers/{layer}` | GeoJSON za kartu: `districts`, `transit`, `parking`, `universities`, `culture`, `schools` (samo prikaz) |
| `GET /api/v1/sources` | izvori, licence, datumi i ograničenja |
| `POST /api/v1/profile-suggestions` | prijedlog djelatnosti iz opisa (5–500 znakova): tri najsličnija profila sa sličnošću; korisnik potvrđuje |
| `POST /api/v1/business-brief` | isto, uz površinu, budžet, četvrti i važnost kriterija iz korisnikovih riječi te bliske potvrđene obavijesti; ništa se ne primjenjuje bez korisnikova izbora |
| `GET /api/v1/market?profile=cafe` | po četvrtima: evidentirani slični objekti (D08) i gradske zakupnine (D20); samo prikaz, ne boduje se |
| `GET /api/v1/spaces/{id}/context?profile=cafe` | obavijesti Grada za četvrt prostora koje je potvrdio član tima i koje su u roku; ne mijenjaju bodove |

Kad kriterij nedostaje samo dijelu prostora, `POST /rankings` vraća `409 COMPARISON_BASIS_CHANGED`, s popisom što nedostaje i potpisanim tokenom. Klijent ponavlja zahtjev s `comparison_basis_token` i `basis_choice`: `common_criteria` (svi prostori, manja pokrivenost) ili `remove_incomplete` (bez nepotpunih). Token vrijedi 10 minuta i samo za taj zahtjev. Interaktivna dokumentacija je na http://localhost:8080/api/docs (samo lokalno).

## Lokalni AI (ADR21)

Model je `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` na zaključanoj reviziji, a pokreće se lokalno preko `onnxruntime`, bez plaćenih API-ja i bez slanja podataka trećima. Jednom ga preuzmi (oko 480 MB, hash svake datoteke se provjerava) pa ponovno pokreni API:

```cmd
docker compose run --rm cli python -m app.cli ai-fetch-model
docker compose up -d api
```

**Prijedlog djelatnosti.** Prvi korak Vodiča ima polje „Nešto drugo?”. Model uspoređuje opis s primjerima svake djelatnosti iz `config/ai_config.json` i vraća tri najsličnije, sa sličnošću. Prijedlog daje samo kad je dovoljno siguran, a korisnik uvijek sam bira. Pragove provjerava i kalibrira:

```cmd
docker compose run --rm cli python -m app.cli ai-calibrate-profiles
```

Skup od 36 tekstova (`config/ai_eval_profiles.json`) je mali i pragovi su podešeni na njemu, pa brojevi u ADR21 nisu točnost na stvarnim korisnicima.

**Oznake iz „Opisa strukture”.** Pravila (ne model, vidi ADR21) predlažu oznake poput „Podrum”, „Ulična zgrada” ili „Broj prostorija: 2”. Javno se prikazuju tek kad ih potvrdi član tima:

```cmd
docker compose run --rm cli python -m app.cli ai-tag-descriptions
docker compose run --rm -T cli python -m app.cli tag-review-template > data\manual\oznake-pregled.csv
```

U `oznake-pregled.csv` za svaki redak pročitaj stupac `description` (službeni tekst) i upiši `decision` (`da` ili `ne`), `reviewer` (svoje inicijale) i po želji `review_note`. Prazni redci se preskaču, a datoteka s greškom ne upisuje ništa.

```cmd
docker compose run --rm cli python -m app.cli import-tag-review --file /app/manual/oznake-pregled.csv
```

**Obavijesti Grada i tržište (ADR24).** `import-all` uvozi i registar ugovora o zakupu (D20). Imena zakupnika se ne spremaju. Obavijesti se uvoze zasebno jer dohvat traje nekoliko minuta (jedan zahtjev u 5 sekundi):

```cmd
docker compose run --rm cli python -m app.cli import D09
docker compose run --rm cli python -m app.cli news-classify
docker compose run --rm -T cli python -m app.cli news-review-template > data\manual\obavijesti-pregled.csv
```

U CSV-u pročitaj stupce `title`, `url` i `text`. Za svaki redak upiši `decision` (`da` ili `ne`) i `reviewer` (svoje inicijale). Za odobrenje provjeri ili ispravi `summary` (do 60 riječi), `location_label`, `district_ids` (šifre četvrti odvojene razmakom), `valid_from` i `valid_to` (ISO datum). Bez `valid_to` obavijest vrijedi 30 dana. Neispravna datoteka ne upisuje ništa.

```cmd
docker compose run --rm cli python -m app.cli import-news-review --file /app/manual/obavijesti-pregled.csv
```

Novi izvor, primjerice portal ili oglasnik, dodaje se tek nakon provjere prava (ADR24 §8).

## E2E testovi (Playwright + axe)

Testovi rade nad pravim stackom na http://localhost:8080 (ili `E2E_BASE_URL`). Jednom instaliraj preglednike, pa pokreni. Ograničenje zahtjeva se isključuje samo za taj lokalni prolaz, jer testovi ponavljaju mnogo posjeta s jedne adrese:

```cmd
cd frontend
npx playwright install chromium webkit
cd ..
set RATE_LIMIT_ENABLED=false
docker compose up -d api web
cd frontend
npx playwright test
cd ..
set RATE_LIMIT_ENABLED=
docker compose up -d api
```

Izvještaj je u `frontend/playwright-report/index.html`. Projekti su `desktop-chromium`, `android-chromium` (Pixel 7) i `iphone-webkit` (iPhone 13).

## Razvoj frontenda s automatskim osvježavanjem

Docker drži bazu i API, a Vite poslužuje frontend:

```cmd
cd frontend
npm ci
npm run dev
```

Otvori http://localhost:5173. Zahtjevi na `/api` idu preko Caddyja na portu 8080, jer API nema vlastiti port ni izlaz na internet (ADR21).

Stranice sučelja:

| Put | Što prikazuje |
|---|---|
| `/` | Vodič: djelatnost → prostor → prioriteti → rezultati. Postavke su u URL-u (`?djelatnost=cafe&m2=60&cetvrti=…`). |
| `/rezultati/{id}` | spremljeni izračun: skupine Spremno i Potrebna provjera, traka doprinosa, karta i slojevi |
| `/rezultati/{id}/usporedba?prostori=a,b,c` | do 3 prostora iz istog izračuna |
| `/prostor/{id}?djelatnost=cafe` | detalj: obrazloženje, četiri uvjeta, okolina, lokacija, popis za provjeru |
| `/izvori` | izvori, licence i datumi |

### Podloga karte

Karta koristi Protomaps izvadak za Zagreb (vektorske pločice iz OpenStreetMapa, ODbL), poslužen s istog servera. Izvadak nije u gitu. Preuzmi ga jednom (desetci MB):

```powershell
powershell -ExecutionPolicy Bypass -File scriptsetch-basemap.ps1
docker compose up -d web
```

Skripta preuzima službeni alat `pmtiles` (go-pmtiles) i iz najnovijeg dnevnog builda čita samo područje Zagreba. Bez izvatka karta prikazuje samo granice četvrti.

Spremljeni izračun otvara se samo u kartici u kojoj je napravljen, jer je pristupni ključ u `sessionStorage`. Prostor bez poznate lokacije prikazuje se isprekidano unutar svoje četvrti i ne ulazi u udaljenosti ([ADR20](docs/adr/ADR20-priblizna-lokacija-i-karta.md)).

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
- **Port 8080 ili 5432 je zauzet**: zaustavi drugu aplikaciju na tom portu ili promijeni lijevi broj u `compose.yaml` (npr. `"8081:80"`).

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
