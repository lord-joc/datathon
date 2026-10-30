# ADR20 Približna lokacija i karta (isječak 5)

Datum: 30. 10. 2026.
Status: prihvaćeno; mijenja točku 4.3/5 i stavku „najmanje 4 potvrđena ulaza” iz definicije gotovog u master promptu

## Kontekst
Nakon D11 (57 redaka) 259 od 262 prostora ima lokaciju na razini zgrade (`building_approximate`), a nijedan nema potvrđen ulaz. Za 5340 i 5341 (Aleja tišine 30, Gornja Dubrava) i 12936 (Vatrogasna bb, Sesvete) OSM izvadak nema ni adresu ni ulicu u toj četvrti. Master prompt traži 4–6 prostora s potvrđenim ulazom i kaže da prostori bez lokacije nisu na karti.

## Odluke
1. **Za MVP je dovoljna približna lokacija zgrade.** Tim ne potvrđuje ulaze prije predaje. Sučelje svugdje piše „Približna lokacija zgrade” i „ulaz nije potvrđen”. `entrance_confirmed` ostaje podržan: kad ga tim upiše u D11, ima prednost i prikazuje se punom oznakom.
2. **Prostor bez lokacije prikazuje se unutar svoje četvrti**, isprekidanom oznakom i tekstom „Točna lokacija nepoznata, prikazana je samo četvrt”. Točka je `ST_PointOnSurface` granice D07 (`label_point` u `/api/v1/layers/districts`) i služi samo za prikaz. Ne upisuje se u `geo_evidence`, ne ulazi u metrike, a udaljenosti ostaju „nepoznato” (`missing_coordinate`). Nikad se ne bira „najbliža ulica” ili susjedni broj bez dokaza.
3. **Podloga je Protomaps PMTiles izvadak za Zagreb** (stil „dark” usklađen s tokenima, oznake na hrvatskom, bez POI ikona), poslužen s istog origina na `/tiles/zagreb.pmtiles`. Fontovi Noto Sans (OFL, samo latinični rasponi) i sprite su u `frontend/public/basemap/`. Izvadak (desetci MB) nije u gitu: preuzima ga `scripts/fetch-basemap.ps1` u `data/basemap/`, a Caddy ga poslužuje bez ponovnog sažimanja jer se čita range zahtjevima. Bez izvatka karta crta granice četvrti na neutralnoj pozadini (rezerva iz §7.4).
4. **Prostori su HTML oznake (gumbi)**, a ne simbolni sloj: rade bez fontova za kartu, mogu se fokusirati tipkovnicom i imaju naziv za čitač zaslona. Pri malom zumu postaju točke bez broja umjesto grupiranja. Za 186–262 prostora to je dovoljno brzo.
5. **Slojevi za kartu** dolaze s `GET /api/v1/layers/{layer}` (`districts`, `transit`, `parking`, `universities`, `culture`, `schools`) kao GeoJSON s ETagom. Služe samo za prikaz.
6. `RankingResponse` dobiva `radius_m` i `target_area_m2`, da rezultati, detalj i usporedba prikazuju postavke spremljenog izračuna, a ne trenutne postavke Vodiča.
7. **Boje kriterija su višebojne** (zahtjev tima 30. 10. 2026., mijenja §7.2 „nijanse plave i sive”). Osam boja u stalnom redoslijedu (prijevoz plava, fakulteti narančasta, kultura tirkizna, garaža žuta, škole ružičasta, površina zelena, ulica ljubičasta, konkurencija crvena; trošak siv) provjereno je alatom za palete na tamnoj podlozi `#12151A`: susjedni parovi za daltoniste ΔE ≥ 8,4, kontrast ≥ 3:1. Ista boja vrijedi za traku doprinosa, legendu, tablice i slojeve na karti. Naziv kriterija uvijek je uz boju, pa boja nikad nije jedini nositelj značenja. Svijetloplava `--accent` ostaje samo za fokus i odabir.
8. **Budžet korisnika** (€ mjesečno, neobavezno, u URL-u kao `budzet`) uspoređuje se samo sa stvarnom cijenom iz izvora (`raw_metrics.cost`, jedinica `eur_month`). D01 nema cijenu, pa je do uvoza cijena iz natječaja (D12) svaki prostor „Cijena nepoznata”, a filtar „Samo unutar budžeta” je isključen. Nepoznata cijena nikad se ne tretira kao 0 € ni kao „unutar budžeta”.
9. **D12 je tablica tima s cijenama iz natječaja Grada** (`tender-template`, `import-tenders`). Svaki redak ima početnu mjesečnu zakupninu točno kako je navedena u natječaju (ili prazno), https poveznicu na zagreb.hr kao dokaz i vrijeme provjere. Redci idu u `status_assessment` (`cost_definition_version = tender_start_monthly_v1`). Paket uzima najnoviju procjenu po prostoru i djelatnosti u `bundle_status`. API prikazuje zakupninu kao metriku `cost` (`eur_month`, s poveznicom), a ona služi samo za usporedbu s budžetom. Trošak se i dalje ne boduje, jer početna zakupnina nije ukupni trošak (režije, jamčevina, uređenje), a nije poznata za većinu prostora. Uvjeti iz iste tablice (`da` vrijedi 168 sati) mijenjaju status prostora po postojećim pravilima.

## Posljedice
- Definicija gotovog: „Svi prostori imaju status lokacije” vrijedi, a „najmanje 4 imaju potvrđen ulaz” se ne traži.
- Kad tim kasnije pronađe zgrade za tri prazna prostora, dovoljan je novi redak u D11 i novi paket.
- Lighthouse i e2e provjere karte rade se u isječku 7.
- Dok tim ne unese D12, budžet ostaje „Cijena nepoznata” za sve prostore. To je točno, a nije greška.
