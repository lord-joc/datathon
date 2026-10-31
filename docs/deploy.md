# Objava na javnoj adresi (isječak 8)

Jedan VPS s Docker Composeom: Caddy (HTTPS i statički frontend), API i PostGIS. Podaci se prenose kao izvoz baze, pa je na serveru točno isti aktivni paket, s istim pregledanim oznakama, kao lokalno.

## Što treba

- VPS: Ubuntu 24.04, najmanje 2 vCPU i 4 GB RAM-a (npr. Hetzner CX22). Model zauzima oko 0,5 GB RAM-a.
- Domena s A zapisom koji pokazuje na IP servera. Bez domene nema TLS certifikata ni HSTS-a.
- SSH pristup kao `root` ili korisnik sa `sudo`.

## 1. Lokalno: pripremi datoteke

U Git Bashu, iz korijena repozitorija, dok lokalni stack radi:

```sh
sh scripts/db-export.sh prostoriq.dump
```

Na server se prenose tri stvari koje nisu u gitu: `prostoriq.dump` (oko 6 MB), `data/basemap/zagreb.pmtiles` (oko 33 MB) i, po želji, `data/manual/` (timske D11/D12 datoteke i pregled oznaka, za kasnije ponovne uvoze).

## 2. Server: Docker i vatrozid

```sh
apt-get update && apt-get install -y ca-certificates curl git ufw
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw --force enable
```

Docker objavljene portove otvara mimo `ufw`-a. Zato `compose.prod.yaml` objavljuje samo 80 i 443, a baza i API nemaju objavljen port.

## 3. Server: kod i `.env`

```sh
git clone https://github.com/lord-joc/datathon.git /opt/prostoriq
cd /opt/prostoriq
cp .env.example .env
chmod 600 .env
```

U `.env` postavi `APP_ENV=production`, `SITE_ADDRESS=<domena>` i nove lozinke za `POSTGRES_PASSWORD`, `API_DB_PASSWORD`, `PIPELINE_DB_PASSWORD` i `APP_HMAC_SECRET`. Lozinke ne kopiraj s lokalnog računala. Generiraj ih ovako:

```sh
python3 -c "import secrets; print(secrets.token_hex(24))"
```

## 4. Prijenos datoteka (s lokalnog računala, Windows CMD)

```cmd
scp prostoriq.dump root@<IP>:/opt/prostoriq/
scp data\basemap\zagreb.pmtiles root@<IP>:/opt/prostoriq/data/basemap/
```

## 5. Server: baza, model i pokretanje

```sh
cd /opt/prostoriq
export COMPOSE_FILE=compose.yaml:compose.prod.yaml
docker compose up -d db
# Pričekaj da se baza pokrene dvaput (inicijalizacija, pa pravi start):
until [ "$(docker compose logs db 2>&1 | grep -c 'ready to accept connections')" -ge 2 ]; do sleep 2; done
sh scripts/db-import.sh prostoriq.dump
docker compose build
docker compose run --rm cli python -m app.cli ai-fetch-model
docker compose up -d
```

`db-import.sh` radi samo u praznoj bazi, a sve se uvozi u jednoj transakciji. `ai-fetch-model` preuzima model s huggingface.co i provjerava hash svake datoteke.

## 6. Provjera

```sh
curl -s https://<domena>/api/v1/status
curl -sI https://<domena>/ | grep -iE "strict-transport|content-security|x-content-type"
```

S lokalnog računala pokreni e2e testove nad javnom adresom:

```cmd
cd frontend
set E2E_BASE_URL=https://<domena>
npx playwright test
```

Lighthouse izmjeri na https://pagespeed.web.dev s adresom stranice i rezultat upiši u ADR22.

## 7. Dnevna kopija baze (NF09)

```sh
crontab -e
# 30 3 * * * cd /opt/prostoriq && sh scripts/backup.sh >> /var/log/prostoriq-backup.log 2>&1
```

Skripta čuva zadnjih 7 izvoza u `/var/backups/prostoriq`. Kopiju povremeno prenesi i izvan servera.

## Ažuriranje

```sh
cd /opt/prostoriq && git pull
export COMPOSE_FILE=compose.yaml:compose.prod.yaml
docker compose build && docker compose run --rm cli python -m app.cli migrate && docker compose up -d
```

Novi paket podataka gradi se i aktivira CLI-jem (`bundle-build`, `bundle-activate`). Povratak je aktivacija ranijeg paketa (`bundle-activate --id …`), vidi `docs/evidence/rollback-demo.txt`.
