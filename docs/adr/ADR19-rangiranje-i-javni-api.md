# ADR19 Rangiranje i javni API (isječak 4)

Datum: 30. 10. 2026.
Status: prihvaćeno

## Kontekst
Master prompt §5.2 i specifikacija v3 određuju formule, zajedničke kriterije i dijalog 409, ali ostavljaju otvorenim kako korisnik potvrđuje novu osnovu usporedbe i što API vraća za kriterij „Ulica”. Ugovor `openapi.yaml` iz v3 poznaje samo kafić i ured, nema kriterij „Škole i vrtići” i koristi drugačiji oblik greške od ostatka API-ja.

## Odluke
1. **Rangiranje je čista funkcija** (`backend/app/ranking/`), bez I/O i u Decimal aritmetici. Rezultati se uspoređuju na 8 decimala (ROUND_HALF_UP), a jednaki rezultati idu po numeričkom ID-u. Referentni primjer (kafić, prostor 4763) daje 90,55357143, uz pokrivenost 77,7778 % aktivnih i 70 % zadanog profila.
2. **Profili su konfiguracija.** Težine su u `config/profiles.json`, a konstante formula u `config/ranking_config.json` (iz njega su uklonjeni profili iz v3). `sources-load` upisuje profile u `criteria_profile`, gdje se nikad ne mijenjaju. Identitet profila je SHA-256 profila i konstanti. Ista oznaka verzije s drugim sadržajem se odbija, a API odbija zahtjev sa zastarjelom verzijom profila (`409 PROFILE_CHANGED`).
3. **Potvrda nove osnove usporedbe.** Kad je kriterij poznat samo dijelu kandidata, `POST /rankings` vraća `409 COMPARISON_BASIS_CHANGED`. Odgovor sadrži popis prostora i kriterija koji nedostaju, dvije opcije (`common_criteria`, `remove_incomplete`) i potpisan `comparison_basis_token`. Klijent ponavlja isti zahtjev s tokenom i poljem `basis_choice`. Ništa nije unaprijed odabrano.
   - Token je HMAC-SHA256 (`APP_HMAC_SECRET`) i vrijedi 10 minuta. Vezan je uz hash zahtjeva (bez tokena i izbora) i uz točan sukob koji je korisnik vidio.
   - Ako se promijeni zahtjev (npr. radijus) ili podaci, traži se nova potvrda.
4. **Trošak i konkurencija.** Trošak je u MVP-u uvijek nedostupan (`cost_not_configured`) i ostaje u nazivniku aktivne pokrivenosti. Kad korisnik uključi konkurenciju, a pokrivenost nije pregledana, kriterij se izostavlja uz razlog `coverage_unchecked`. Kad je korisnik isključi, njegova se težina postavlja na 0.
5. **Snimka je nepromjenjiva.** `ranking_run` i `ranking_item` spremaju zahtjev, težine, konstante, verzije izvora, statuse i koordinate. `ranking_item.reason` (migracija 0007) objašnjava zašto stavka nema rezultat.
   - Pristupni token (32 bajta, URL-safe) vraća se samo jednom. U bazi je samo njegov SHA-256.
   - `GET /rankings/{id}` traži zaglavlje `X-Ranking-Token`. Izračun nad ranijim paketom vraća se nepromijenjen, s oznakom `historical: true`.
6. **Javni API čita samo aktivni paket.** Zahtjev s drugim `dataset_bundle_id` dobiva `409 DATASET_CHANGED`. Bez aktivnog paketa odgovor je `503 DATASET_NOT_READY`.
7. **Status prostora.** D02 je uvijek `excluded`. Potvrđen `no` daje `excluded`, a četiri potvrđena `yes` daju `ready`. Inače je prostor `conditional`, s razlogom za svaki nepotvrđen uvjet. `yes` nakon 168 sati postaje `unknown` (`status_review_due`).
8. **Prikaz vrijednosti.** U API-ju se „Ulica” prikazuje kao korisnost (1 za ulični položaj, 0,4 za ostale), kao u primjeru iz v3. Razlozi iz paketa preslikavaju se u kodove iz ugovora (npr. `location_not_confirmed` u `missing_coordinate`). `Metric.detail` donosi naziv i vrstu najbližeg objekta te napomenu „zračno” za prikaz u detalju.
9. **Pregled uvoza.** Uvoz koji čeka pregled (licenca ili promjena broja zapisa > 20 %) ne koristi se i blokira sljedeće uvoze tog izvora. `reviews` ga prikazuje, a `source-review --approve|--reject --reason` ga razrješava i zapisuje audit događaj.
10. **Greške** su RFC 9457 `application/problem+json` s poljem `code`, kao u isječcima 1–3. Ugovor je ažuriran na taj oblik.

## Posljedice
- `openapi.yaml` dobiva sedam profila, kriterij `schools`, `basis_choice`, `Metric.detail` i problem+json grešku.
- Ograničenje zahtjeva za rangiranje (30 u minuti) i ostala sigurnosna zaglavlja dolaze u isječku 7.
- Rangiranje 186 stvarnih prostora traje oko 180 ms preko Caddyja na lokalnom računalu, uključujući upis snimke.
