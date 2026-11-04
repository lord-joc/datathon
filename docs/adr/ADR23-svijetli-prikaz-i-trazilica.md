# ADR23 Svijetli prikaz, crvena traka i tražilica (redizajn sučelja)

Datum: 4. 11. 2026.
Status: prihvaćeno; mijenja paletu i tipografiju iz §7.2 master prompta (tamna tema s plavim akcentom)

## Kontekst
Tim je tražio izgled u stilu javnih e-usluga: svijetli, pregledni prikaz s crvenom trakom, tražilicom u zaglavlju i manje vizualnog šuma. Tamni prikaz ostaje za one koji ga imaju uključenog u sustavu.

## Odluke
1. **Svijetli prikaz je zadani.** Bez izbora korisnika aplikacija prati `prefers-color-scheme`. Gumb u zaglavlju prebacuje prikaz i pamti izbor u `localStorage` samo u tom pregledniku (`lib/theme.ts`). Tema se postavlja na `html[data-theme]` prije prvog crtanja, bez inline skripte (CSP `script-src 'self'`).
2. **Jedan akcent: crvena.** Light #C8102E (5,9:1 na bijeloj), dark #FF7480 (7,0:1 na površini). Isti nazivi tokena za obje teme (`styles/tokens.css`), pa komponente ne znaju za temu. Boje kriterija (ADR20) ostaju iste jer imaju barem 3:1 i na bijeloj pozadini.
3. **Vlastiti znak, ne državni simboli.** Traka nosi ProstorIQ znak (tlocrt s istaknutom prostorijom). Grb, šahovnica i oznake ministarstva ne koriste se: projekt nije služba Grada ni državne uprave i to piše u podnožju.
4. **Tražilica u zaglavlju** pretražuje djelatnosti i prostore (adresa, četvrt, ID). Popis od 262 prostora učitava se jednom, pri prvom fokusu, i filtrira u pregledniku, pa tipkanje ne šalje zahtjeve ni ne troši ograničenje zahtjeva. Svaka riječ upita mora biti početak riječi u zapisu („vlaška 8” ne nalazi Vlašku 96 prostora 4008). ARIA combobox s tipkovnicom.
5. **Crveno svjetlo koje prati miš** na interaktivnim karticama (djelatnosti, rezultati, izbor osnove usporedbe): jedan delegirani `pointermove` piše `--mx/--my`, crta CSS. Na dodir, olovku i uz `prefers-reduced-motion` ostaje tanki crveni rub bez praćenja.
6. **Manje šuma:** jedan font (Inter; Fraunces se više ne učitava), oznake iznad naslova bez velikih slova, status podataka u zaglavlju vidi se samo kad nešto ne valja, kraća napomena o popisu, Vodič na mobitelu bez okvira oko okvira.
7. **Karta prati temu:** svijetla ili tamna Protomaps podloga i boje vlastitih slojeva; promjena teme ponovno gradi kartu i zadržava pogled.

## Provjera
axe (WCAG 2.2 AA) bez nalaza za Vodič, tražilicu i detalj prostora u oba prikaza i na mobitelu (390 px, bez vodoravnog pomicanja). tsc, ESLint, Vitest i produkcijski build prolaze. E2E nad cijelim stackom treba ponoviti lokalno.
