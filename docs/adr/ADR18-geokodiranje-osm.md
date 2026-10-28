# ADR18 — Geokodiranje prostora: OSM adrese (D19) + timska provjera (D11)

Status: prihvaćeno, 28.10.2026.

## Kontekst
D01/D02 imaju samo adresu (npr. `TRG ANTE STARČEVIĆA 0007`), bez koordinata. Prostorne metrike (FZ03) traže točku. Pogrešna točka je gora od nepoznate: daje uvjerljiv, ali netočan rezultat.

## Razmotrene opcije
1. **DGU INSPIRE adrese** (data.gov.hr, Otvorena dozvola). Službene, ali dostupne kao GML preko WFS-a (traži authKey) ili Atom feeda za cijelu Hrvatsku. WFS zapis ne navodi licencu. Odgođeno za pilot.
2. **Javni geokoder (Nominatim API)**: pravila korištenja zabranjuju skupne upite, rezultat nije ponovljiv. Odbačeno.
3. **OSM adrese iz Geofabrik PBF-a (ODbL-1.0)**: lokalno, ponovljivo, verzionirano po SHA-256. Ista datoteka daje D08 (konkurencija). **Odabrano.**

## Odluka
- `osm-import` iz jednog PBF-a uvozi D19 (`osm_address`) i D08 (`competitor`); relacije se preskaču i broje.
- Uparivanje je determinističko: normalizacija ulice (bez dijakritika, kratice), kućni broj i slovo. Približno ime ulice prihvaća se samo ako je omjer ≥ 0,88 i jasno bolji od drugog (razlika ≥ 0,04).
- Kad slovo kućnog broja nije isto, kad su pogoci više od 80 m razmaknuti ili su slična imena dvosmislena, rezultat je `needs_review`, bez točke.
- Obris zgrade (way) ima prednost pred točkama tvrtki s istom adresom.
- `geocode-review` izvozi D11 predložak; tim upisuje provjerene točke s dokazom. D11 `entrance_confirmed` uvijek ima prednost.
- U metrike ulaze samo `entrance_confirmed` i `building_approximate`; ostalo ostaje „nepoznato” s razlogom `location_not_confirmed`.

## Posljedice
- Atribucija „© OpenStreetMap contributors, ODbL” obavezna je u aplikaciji i dokumentaciji.
- Točnost je razina zgrade, a ne ulaza, i to se prikazuje korisniku.
- Prelazak na DGU adrese mijenja samo izvor D19; pravila uparivanja ostaju ista.
