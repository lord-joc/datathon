# ADR18 Geokodiranje prostora: OSM adrese (D19) + timska provjera (D11)

Datum: 28. 10. 2026.
Status: prihvaćeno; zamjenjuje točku 4 iz [ADR16](ADR16-timske-odluke-v3-1.md)

## Kontekst
D01/D02 imaju samo adresu (npr. `TRG ANTE STARČEVIĆA 0007`), bez koordinata. Prostorne metrike (FZ03) traže točku. Pogrešna točka je gora od nepoznate: daje uvjerljiv, ali netočan rezultat.

## Razmotrene opcije
1. **DGU INSPIRE adrese** (data.gov.hr, Otvorena dozvola). Službene, ali dostupne kao GML preko WFS-a (traži authKey) ili Atom feeda za cijelu Hrvatsku. WFS zapis ne navodi licencu. Odgođeno za pilot.
2. **Javni geokoder (Nominatim API)**: pravila korištenja zabranjuju skupne upite, rezultat nije ponovljiv. Odbačeno.
3. **OSM adrese iz Geofabrik PBF-a (ODbL-1.0)**: lokalno, ponovljivo, verzionirano po SHA-256. Ista datoteka daje D08 (konkurencija). **Odabrano.**

## Odluka
- `osm-import` iz jednog PBF-a uvozi D19 (`osm_address`) i D08 (`competitor`); relacije se preskaču i broje.
- Uparivanje je determinističko: normalizacija ulice (bez dijakritika, kratice), kućni broj i slovo. Približno ime ulice prihvaća se samo ako je omjer ≥ 0,88 i jasno bolji od drugog (razlika ≥ 0,04).
- Riječ „ulica” ne ulazi u ključ ulice, jer je popis često izostavlja („VLAŠKA” prema „Vlaška ulica”).
- Popis koristi posvojni oblik imena („HEINZELOVA”), a OSM službeni naziv („Ulica Vjekoslava Heinzela”). Takve OSM ulice dobivaju aliase `-ova` i `-eva` iz prezimena. Alias se koristi samo kad nema točnog pogotka i samo ako vodi na točno jednu OSM ulicu; inače je rezultat `needs_review`.
- `geo_evidence` se samo dopunjuje. Ponovno geokodiranje obrađuje samo prostore koji još nemaju lokaciju zgrade i upisuje novi redak samo kad se rezultat promijeni. Paket uzima najbolji dokaz po prostoru, a identitet paketa uključuje i odabrane dokaze, pa novo geokodiranje ili D11 stvaraju novi paket.
- Učinak na stvarnim podacima (28. 10. 2026.): upotrebljiva lokacija za D01 porasla je s 55 na 143 od 186 prostora. Svih 13 alias pogodaka ručno je provjereno.
- Kad slovo kućnog broja nije isto, kad su pogoci više od 80 m razmaknuti ili su slična imena dvosmislena, rezultat je `needs_review`, bez točke.
- Obris zgrade (way) ima prednost pred točkama tvrtki s istom adresom.
- `geocode-review` izvozi D11 predložak; tim upisuje provjerene točke s dokazom. Automatski razlog je u zasebnom stupcu `auto_note` i nikad se ne računa kao dokaz. D11 `entrance_confirmed` uvijek ima prednost.
- U metrike ulaze samo `entrance_confirmed` i `building_approximate`; ostalo ostaje „nepoznato” s razlogom `location_not_confirmed`.

## Posljedice
- Atribucija „© OpenStreetMap contributors, ODbL” obavezna je u aplikaciji i dokumentaciji.
- Točnost je razina zgrade, a ne ulaza, i to se prikazuje korisniku.
- Prelazak na DGU adrese mijenja samo izvor D19; pravila uparivanja ostaju ista.
