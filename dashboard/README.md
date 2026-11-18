# Trading Desk dashboard

A small, read-only web dashboard for the reports and journal that the skills in this
repo produce. It runs in one Docker container on your home network.

What it shows:

| Section | Where the data comes from |
|---|---|
| Exposure ceiling, breadth, uptrend tiles and history charts | `reports/exposure_posture_*.json`, `market_breadth_*.json`, `uptrend_analysis_*.json` |
| Circuit breaker | `reports/circuit_breaker_decision_*.json` (drawdown-circuit-breaker) |
| Broker account and positions | Alpaca API, read-only (GET account and positions only) |
| Theses, review-due list, journal | `state/**/th_*.yaml` and `state/**/pm_*.md` (trader-memory-core) |
| Latest VCP screen | `reports/vcp_screener_*.json` |
| Reports page | Every report above, rendered from its `.md` or `.json` |

What it can't do: place, change or cancel orders. The Alpaca client in
`app/alpaca.py` only sends `GET /v2/account` and `GET /v2/positions`. The `reports/`
and `state/` folders are mounted read-only into the web container.

Your balances, P&L and journal stay on the machine that runs the dashboard.
`reports/`, `state/` and `dashboard/.env` are all git-ignored, so they never reach GitHub.

---

## Set up on the homelab (CT 106 on juno)

These steps follow the same pattern as the Jarvis containers. Run them in order.
Anything in `<angle brackets>` is a value you fill in.

| Setting | Value |
|---|---|
| Node | juno |
| CT ID | 106 (check it's free) |
| Hostname | `trading` |
| Template | Debian 13 standard, unprivileged, `nesting=1` (for Docker) |
| CPU / RAM / swap / disk | 1 core / 1024 MB / 512 MB / 8 GB on `local-zfs` |
| Network | `vmbr0`, 192.168.40.26/24, gateway and DNS 192.168.40.1 |
| Name | `https://trading.lab.silkytech.org` through Caddy |

### 1. Create the container (shell on juno)

```bash
pct list                     # 106 must not be listed
pveam list local | grep debian-13
pct create 106 local:vztmpl/<debian-13 template file> \
  --hostname trading --ostype debian --unprivileged 1 --features nesting=1 \
  --cores 1 --memory 1024 --swap 512 --rootfs local-zfs:8 \
  --net0 name=eth0,bridge=vmbr0,ip=192.168.40.26/24,gw=192.168.40.1 \
  --nameserver 192.168.40.1 --onboot 1
pct start 106
pct enter 106
```

### 2. Inside the container: basics, time zone and Docker

```bash
passwd                                   # save it in Vaultwarden
apt update && apt full-upgrade -y
apt install -y ca-certificates curl git cron
timedatectl set-timezone America/New_York

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt update && apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
docker compose version                   # should print a version
```

### 3. Get the repo and make the data folders

```bash
git clone https://github.com/Maso1634/claude-trading-skills.git /opt/claude-trading-skills
cd /opt/claude-trading-skills
mkdir -p reports state/theses state/journal
chown -R 1000:1000 reports state        # the containers run as user 1000
```

To bring your existing theses over from the laptop, run this **on the laptop**
(adjust the path if your repo lives somewhere else):

```bash
scp -r ~/claude-trading-skills/state/. root@192.168.40.26:/opt/claude-trading-skills/state/
scp -r ~/claude-trading-skills/reports/. root@192.168.40.26:/opt/claude-trading-skills/reports/
```

Then on the CT run `chown -R 1000:1000 /opt/claude-trading-skills/reports /opt/claude-trading-skills/state` again.

### 4. Add your keys

```bash
cd /opt/claude-trading-skills/dashboard
cp .env.example .env
chmod 600 .env
nano .env        # paste your Alpaca PAPER key and secret, keep ALPACA_ENV=paper
```

Your keys go in this file and in Vaultwarden. Don't paste them into chat or into the vault.

### 5. Start it

```bash
cd /opt/claude-trading-skills/dashboard
docker compose up -d --build
docker compose ps                        # STATUS should say "healthy" after a minute
curl -s http://127.0.0.1:8080/healthz    # {"ok": true, ...}
```

Open `http://192.168.40.26:8080` from the Admin Workstation or over WireGuard.

### 6. Fill it with market data, then refresh every weekday

Run the refresh once by hand. It takes about a minute and writes breadth, uptrend and
exposure reports:

```bash
cd /opt/claude-trading-skills/dashboard
docker compose run --rm refresh
```

Then schedule it for 4:20 PM ET on weekdays with `crontab -e`, adding this line:

```cron
20 16 * * 1-5 cd /opt/claude-trading-skills/dashboard && docker compose run --rm refresh >> /var/log/trading-refresh.log 2>&1
```

With only breadth and uptrend as inputs, exposure-coach reports **low** confidence.
That's expected; more inputs (FTD, market top, macro regime) can be added later.
To also run the VCP screen nightly, set `RUN_VCP=true` and `FMP_API_KEY` in `.env`.
That uses FMP API calls, so watch the free tier's 250 a day.

### 7. Give it a name in Caddy

On CT 102 add a block to `/etc/caddy/Caddyfile` next to the others, above the catch-all `abort`:

```caddyfile
@trading host trading.lab.silkytech.org
handle @trading {
	reverse_proxy 192.168.40.26:8080
}
```

```bash
caddy validate --config /etc/caddy/Caddyfile && systemctl reload caddy
```

Watch for the colon before the port. `192.168.40.26.8080` passes `caddy validate` but gives a 502.

On janus: **Services → Unbound DNS → Overrides → Hosts → +**, host `trading`, domain
`lab.silkytech.org`, IP `192.168.40.22` (Caddy). Save and Apply.

### Updating

```bash
cd /opt/claude-trading-skills && git pull
cd dashboard && docker compose up -d --build
```

---

## Switching from paper to your real (live) account

The dashboard stays read-only either way. Live only changes which account it shows.

1. In Alpaca, switch to your live account and create a live API key pair. Save it in Vaultwarden.
2. On the CT, edit `.env`:
   ```bash
   cd /opt/claude-trading-skills/dashboard && nano .env
   ```
   Set `ALPACA_ENV=live` and replace `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` with the **live** pair.
   Paper keys don't work against the live API, and live keys don't work against paper.
3. Restart: `docker compose up -d`
4. Check the top of the page: a red **LIVE ACCOUNT** banner replaces the blue **PAPER ACCOUNT** one.

To go back, set `ALPACA_ENV=paper`, put the paper keys back, and restart. Any value other
than exactly `live` is treated as paper, so a typo can't point you at real money.

---

## Preview with made-up data (no keys needed)

```bash
cd dashboard
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/make_sample_data.py
REPORTS_DIR=sample-data/reports STATE_DIR=sample-data/state flask --app 'app:create_app()' run
```

Open http://127.0.0.1:5000. Every number in `sample-data/` is invented.

## Tests

```bash
cd dashboard
pip install -r requirements-dev.txt
python -m pytest
```

## Troubleshooting

- **A tile says "stale":** that report is more than 30 hours old. Check `/var/log/trading-refresh.log` and run `docker compose run --rm refresh` by hand.
- **"Couldn't reach Alpaca":** check the keys and `ALPACA_ENV` in `.env`. Paper keys need `paper`, live keys need `live`.
- **Refresh fails with "Permission denied" on reports/:** run `chown -R 1000:1000 /opt/claude-trading-skills/reports`.
- **Theses missing:** the dashboard reads every `th_*.yaml` under `state/`. Files that fail to parse are listed on the Theses page.
