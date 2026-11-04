# ADR24 Osobni prijedlog, obavijesti Grada i stanje tržišta

Datum: 4. 11. 2026.
Status: prihvaćeno; dopunjuje ADR21 (§9 obavijesti) i FZ25, potvrđuje FZ13–FZ17

## Kontekst
Traži se da „Nešto drugo?” daje osobniji rezultat i da se uzme u obzir stanje tržišta i vijesti. Lokalni MiniLM nije generativan: uspoređuje tekstove, ali ne može čitati vijesti ni pisati savjete. Tim je 4. 11. 2026. odlučio ostati na lokalnom modelu i predlošcima (bez plaćenog API-ja), da AI predlaže težine uz potvrdu korisnika i da obavijesti odobrava tim preko CSV-a.

## Odluke
1. **Prijedlog iz opisa.** `POST /api/v1/business-brief` vraća prijedlog djelatnosti (model, ADR21) te površinu, budžet, četvrti i važnost kriterija iz korisnikovih riječi. Te vrijednosti čitaju pravila, jer su provjerljiva i svaka nosi riječi koje su je izazvale. Ništa se ne primjenjuje dok korisnik ne odabere djelatnost; nakon toga su to obične postavke koje može promijeniti u koracima 2 i 3. Opis se ne sprema i ne bilježi.
2. **Što to znači za bodove.** Formule i preporučene težine profila ostaju iste. Korisnik je i prije mogao mijenjati razine važnosti; prijedlog samo unaprijed popunjava te razine, vidljivo i uz razlog. FZ25 („izvorne težine nisu izmijenjene”) i dalje vrijedi za težine profila.
3. **Obavijesti Grada (D09).** Dohvat s `www.zagreb.hr` ide kroz postojeći uvoz: samo stranice iz registra, samo članci na istom hostu, najviše 100 dokumenata, jedan zahtjev u 5 sekundi. Uvjeti Grada dopuštaju ponovnu uporabu uz poveznicu na izvor, osim sadržaja preuzetog iz drugih izvora; to provjerava osoba pri pregledu.
4. **Model samo predlaže temu.** `news-classify` računa najveći kosinus po temi preko naslova i blokova 96/16 te stvara karticu `pending_review` samo za razvrstanu obavijest. Mjesto i datumi dolaze iz izričitih riječi u tekstu. Sažetak je predložak od činjenica iz objave. Javna je samo kartica koju je potvrdio član tima (`import-news-review`), i to samo dok je u roku; rok se provjerava pri svakom čitanju. Kartice ne mijenjaju bodove (FZ16).
5. **Tko potvrđuje.** Administratorski računi ne postoje, pa je dodan `context_card.reviewed_by_name`. Odobrenje traži ime ili administratora. Kao i kod oznaka, ime koje izgleda kao AI se odbija.
6. **Stanje tržišta.** `GET /api/v1/market` po četvrtima daje evidentirane slične objekte iz D08 i zakupnine iz novog izvora D20, „Registar ugovora o zakupu poslovnih prostora” (Grad Zagreb, Otvorena dozvola). Prikaz je samo za orijentaciju i ne boduje se. Medijan se prikazuje tek od 5 ugovora. Uz prikaz uvijek stoji da su to gradske zakupnine, a ne tržišne cijene privatnih prostora.
7. **Osobni podaci u D20.** Registar imenuje zakupnike, često fizičke osobe, u posebnom stupcu i unutar „Predmeta ugovora”. Parser je popis dopuštenih polja: ID prostora, adresa, površina, zakupnina, datum i tekst nakon riječi „djelatnost”. Imena ne ulaze u bazu ni u API. Izvorna datoteka ostaje samo u privatnoj pohrani sirovih datoteka, kao i svaka druga.
8. **Izvori koji nisu uključeni (provjereno 4. 11. 2026.).**
   - **Njuškalo:** automatski zahtjev je blokiran porukom za botove. Zaštita se ne zaobilazi.
   - **Večernji i Poslovni:** uvjeti izričito zabranjuju pohranu i kopiranje sadržaja osim za osobnu uporabu.
   - **Index i ostali novinski portali:** uvjeti nisu potvrđeni, pa se ne dohvaćaju.
   - **DZS „Statistika u nizu”:** skup nema navedenu dozvolu na portalu.

   Novi izvor ulazi tek s provjerenim pravima, kroz registar i `allowed_hosts`. Pravila Datathona traže da dozvola dopušta korištenje.

## Posljedice
- Evaluacija teme (NF14, 12 + 28 ručno označenih tekstova) nije napravljena. Pragovi 0,45 i 0,05 ostaju početne vrijednosti. Do tada je ljudska potvrda jedina zaštita točnosti.
- Bez odobrenih kartica javni prikaz kaže da obavijesti nisu potvrđene i koliko ih čeka. Za video treba barem jedna kartica koju je potvrdio član tima.
- Prvi uvoz D09 traje nekoliko minuta zbog razmaka među zahtjevima. API i dalje nema izlaz na internet; dohvat radi samo CLI.
- Promjena `topic_profiles` i pragova mijenja hash konfiguracije, pa `news-classify` obrađuje obavijesti ponovno, a postojeće odluke ostaju.
