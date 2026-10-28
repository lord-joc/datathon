# ADR16 Timske odluke nakon dokumentacije v3

Datum: 28. 10. 2026.
Status: prihvaćeno; točku 4 zamjenjuje [ADR18](ADR18-geokodiranje-osm.md)

## Kontekst

Dokumentacija v3 (27. 10. 2026.) definira profile kafić i ured, kriterij „Tramvajsko stajalište”, Leaflet kartu i svijetlu temu. Tim je nakon pregleda donio dopune.

## Odluke

1. **Sedam profila djelatnosti**: `cafe`, `office`, `retail`, `food_takeaway`, `personal_care`, `education`, `workshop`. Profili su konfiguracija (`config/profiles.json`), a ne kod. Migracija `0003_more_profiles` proširuje CHECK ograničenja.
2. **„Javni prijevoz” umjesto „Tramvajsko stajalište”**: najbliže stajalište tramvaja ili autobusa ZET. Formula i prag od 800 m ostaju isti.
3. **Novi kriterij „Škole i vrtići u 600 m”**: `min(count/6, 1)`. Prag je početna pretpostavka.
4. ~~**Geokodiranje svih prostora** DGU adresnim točkama (`building_approximate`), uz ručnu potvrdu ulaza za demo prostore.~~ **Zamijenjeno [ADR18](ADR18-geokodiranje-osm.md):** DGU adrese traže WFS authKey i nemaju navedenu licencu, pa su odgođene za pilot. Svi prostori geokodiraju se OSM adresama (D19, `building_approximate`), a ulaz potvrđuje tim (D11, `entrance_confirmed`). Cilj ostaje isti.
5. **AI** se dodatno koristi za oznake iz polja „Opis strukture” i za prijedlog profila (FZ25 postaje M). Nijedna AI oznaka ne mijenja bodove.
6. **MapLibre GL + PMTiles** s istog originala umjesto Leafleta i vanjskih rasterskih pločica.
7. **Tamna tema** sa svijetloplavim naglaskom.
8. **Administracija preko CLI-ja** u MVP-u. Web admin je P.
9. **Frontend**: React Router 7 umjesto 6 (sigurnosne zakrpe), Vite 7, Vitest 5.

## Posljedice

- Kafić i ured zadržavaju težine iz v3. Referentni primjer 90,55 vrijedi kad je najbliže stajalište tramvajsko.
- Pokrivenost zadanog profila za nove profile računa se istom formulom, uz trošak kao nedostupan.
- `ranking_config.json` iz v3 ostaje u `config/` kao referenca dok isječak 4 ne prijeđe na `profiles.json`.
