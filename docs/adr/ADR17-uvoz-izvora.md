# ADR17 Uvoz izvora u isječku 2

Datum: 28. 10. 2026.
Status: prihvaćeno

## Odluke

1. **Uvoz je CLI posao, ne worker.** `python -m app.cli import CODE` i `import-all` koriste istu tablicu `import_job` (idempotentnost, jedan aktivni posao po izvoru, izvještaj), ali bez leasea i heartbeata. Worker iz ADR05 ostaje plan za pilot.
2. **Zaseban servis `cli`** u Composeu drži vlasničke i pipeline vjerodajnice. Javni `api` ima samo `prostoriq_api`.
3. **Zaglavlje D01/D02 traži se po imenima polja** u prvih 6 redaka (D01 je u 2., a D02 u 3. retku), a ne po fiksnoj poziciji.
4. **Licenca:** CKAN licenca koja nije prepoznata kao Otvorena dozvola ne zaustavlja uvoz, nego verziju stavlja u `awaiting_review`.
5. **Novi izvori:** D14 autobusna stajališta ZET, D17 dječji vrtići i D18 osnovne škole. Numeracija se razlikuje od master prompta (D17 vrtići i škole zajedno), jer je svaki skup zaseban CKAN paket. HŽ stajališta i stanovništvo dobit će sljedeće slobodne oznake.
6. **Ručna datoteka** (`--file`) je dopuštena kao rezervni put i uvijek se bilježi upozorenjem `manual_file`.
7. **Migracija 0005** daje ulozi `pipeline` pravo na `UPDATE` samo stupaca `last_checked_at` i `quality_status` u `source_version`.

## Poznato ograničenje

DNS se razrješava pri provjeri i ponovno pri spajanju, pa napad DNS rebindingom na domenu s popisa teoretski ostaje moguć. U produkciji se izlazni promet ograničava i na vatrozidu.
