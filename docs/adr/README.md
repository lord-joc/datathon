# Arhitekturne odluke (ADR)

| ADR | Naslov | Status |
|---|---|---|
| [ADR16](ADR16-timske-odluke-v3-1.md) | Timske odluke nakon dokumentacije v3 | prihvaćeno; točku 4 zamjenjuje ADR18 |
| [ADR17](ADR17-uvoz-izvora.md) | Uvoz izvora u isječku 2 | prihvaćeno |
| [ADR18](ADR18-geokodiranje-osm.md) | Geokodiranje prostora: OSM adrese (D19) + timska provjera (D11) | prihvaćeno; dopunjeno 30. 10. 2026. |
| [ADR19](ADR19-rangiranje-i-javni-api.md) | Rangiranje i javni API (isječak 4) | prihvaćeno |
| [ADR20](ADR20-priblizna-lokacija-i-karta.md) | Približna lokacija i karta (isječak 5) | prihvaćeno |
| [ADR21](ADR21-lokalni-ai-i-konkurencija.md) | Lokalni AI i konkurencija iz OSM-a (isječak 6) | prihvaćeno, dopunjeno ADR22 |
| [ADR22](ADR22-sigurnost-pristupacnost-e2e.md) | Sigurnost, pristupačnost i e2e (isječak 7) | prihvaćeno |
| [ADR23](ADR23-svijetli-prikaz-i-trazilica.md) | Svijetli prikaz, crvena traka i tražilica | prihvaćeno |
| [ADR24](ADR24-osobni-prijedlog-i-trzisni-kontekst.md) | Osobni prijedlog, obavijesti Grada i stanje tržišta | prihvaćeno |

ADR01–ADR15 dio su timske dokumentacije v3 (27. 10. 2026.) i nisu u ovom repozitoriju. Tamo su i master prompt te oznake zahtjeva (FZ, NF). Strojno čitljivi zahtjevi i sljedivost su u [`docs/contracts/`](../contracts/): `requirements.json` i `traceability.csv`.

Kad odluka mijenja raniju, novi ADR to navodi u polju „Status”, a stari ADR dobiva poveznicu na novi.
