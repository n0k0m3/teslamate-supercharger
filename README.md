# teslamate-supercharger

A daemon that runs alongside [TeslaMate](https://github.com/adriankumpf/teslamate) to automatically fetch Supercharger session costs from the Tesla Fleet API and write them back into TeslaMate's database.

When a Supercharger session ends, it fetches the cost and energy data and writes it to:
- A new `supercharger_sessions` table
- The `cost` column on TeslaMate's existing `charging_processes` table

## Prerequisites

- A running TeslaMate installation (Docker)
- A [Tesla Developer account](https://developer.tesla.com) with a Fleet API application

## 1. Tesla Fleet API setup

1. Register an application at [developer.tesla.com](https://developer.tesla.com)
2. Request the following scopes: `vehicle_device_data`, `vehicle_cmds`, `vehicle_charging_cmds`
3. Note your **Client ID** and **Client Secret**

Verify your credentials work:

```bash
curl -s --request POST \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=client_credentials' \
  --data-urlencode "client_id=YOUR_CLIENT_ID" \
  --data-urlencode "client_secret=YOUR_CLIENT_SECRET" \
  --data-urlencode 'scope=openid vehicle_device_data vehicle_cmds vehicle_charging_cmds' \
  --data-urlencode 'audience=https://fleet-api.prd.na.vn.cloud.tesla.com' \
  'https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token'
```

## 2. Deployment

Choose the option that matches your setup.

---

### Option A — Add to existing TeslaMate `docker-compose.yml`

This is the recommended approach. The service joins TeslaMate's existing Docker network and shares its database and MQTT broker.

**Step 1.** Add the following service block to your existing `docker-compose.yml`:

```yaml
services:
  supercharger:
    image: ghcr.io/n0k0m3/teslamate-supercharger:latest
    restart: unless-stopped
    depends_on:
      - database
      - mosquitto
      - teslamate
    environment:
      - DATABASE_HOST=database
      - DATABASE_PORT=5432
      - DATABASE_NAME=teslamate
      - DATABASE_USER=teslamate
      - DATABASE_PASS=${TESLAMATE_DB_PASSWORD}
      - TESLA_CLIENT_ID=${TESLA_CLIENT_ID}
      - TESLA_CLIENT_SECRET=${TESLA_CLIENT_SECRET}
      - TESLA_FLEET_REGION=na        # na, eu, or cn
      - MQTT_HOST=mosquitto
      - MQTT_PORT=1883
      # - MQTT_USERNAME=
      # - MQTT_PASSWORD=
      - API_FETCH_DELAY_SECONDS=30
      - SESSION_MATCH_WINDOW_MINUTES=15
    networks:
      - teslamate
```

> The `networks` section and `teslamate` network must already be defined in your file. If not, add:
> ```yaml
> networks:
>   teslamate:
>     external: true
> ```

**Step 2.** Add the new vars to your `.env` file:

```env
TESLA_CLIENT_ID=your-client-id
TESLA_CLIENT_SECRET=your-client-secret
```

**Step 3.** Start the service:

```bash
docker compose up -d supercharger
```

---

### Option B — Standalone with external network

Use this if you want to keep this service in its own `docker-compose.yml`, separate from TeslaMate's stack.

**Step 1.** Find TeslaMate's Docker network name:

```bash
docker network ls | grep teslamate
```

**Step 2.** Create a `docker-compose.yml`:

```yaml
services:
  supercharger:
    image: ghcr.io/n0k0m3/teslamate-supercharger:latest
    restart: unless-stopped
    env_file: .env
    networks:
      - teslamate

networks:
  teslamate:
    external: true
    name: YOUR_NETWORK_NAME   # e.g. teslamate_default or teslamate
```

**Step 3.** Create a `.env` file (copy from `.env.example`):

```env
DATABASE_HOST=database
DATABASE_PORT=5432
DATABASE_NAME=teslamate
DATABASE_USER=teslamate
DATABASE_PASS=your-teslamate-db-password

TESLA_CLIENT_ID=your-client-id
TESLA_CLIENT_SECRET=your-client-secret
TESLA_FLEET_REGION=na

MQTT_HOST=mosquitto
MQTT_PORT=1883
```

> Set `DATABASE_HOST` and `MQTT_HOST` to the container names as seen inside the Docker network (usually `database` and `mosquitto`).

**Step 4.** Start:

```bash
docker compose up -d
```

---

## 3. Initial backfill

On every startup the daemon automatically backfills any sessions from the **last 24 hours** that are missing cost data. For a full historical backfill of all sessions:

```bash
docker compose run --rm supercharger python -m teslamate_supercharger.backfill
```

This fetches every session from the Fleet API and upserts it into the database. Safe to re-run.

## 4. Verify it's working

```bash
docker compose logs -f supercharger
```

On a healthy start you should see:

```
INFO teslamate_supercharger.db: Database connection pool initialized
INFO teslamate_supercharger.db: Schema verified/migrated
INFO __main__: Fleet API access token acquired
INFO __main__: Cars loaded: {1: 'XXXXXXXX***'}
INFO __main__: Backfill: no uncosted recent sessions found
INFO teslamate_supercharger.mqtt_client: Connected to MQTT broker
```

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_HOST` | yes | — | PostgreSQL host (container name) |
| `DATABASE_PORT` | no | `5432` | PostgreSQL port |
| `DATABASE_NAME` | no | `teslamate` | Database name |
| `DATABASE_USER` | no | `teslamate` | Database user |
| `DATABASE_PASS` | yes | — | Database password |
| `TESLA_CLIENT_ID` | yes | — | Fleet API app client ID |
| `TESLA_CLIENT_SECRET` | yes | — | Fleet API app client secret |
| `TESLA_FLEET_REGION` | no | `na` | Fleet API region: `na`, `eu`, or `cn` |
| `MQTT_HOST` | no | `mosquitto` | MQTT broker host |
| `MQTT_PORT` | no | `1883` | MQTT broker port |
| `MQTT_USERNAME` | no | — | MQTT username (if broker requires auth) |
| `MQTT_PASSWORD` | no | — | MQTT password (if broker requires auth) |
| `API_FETCH_DELAY_SECONDS` | no | `30` | Wait after session ends before calling Tesla API |
| `SESSION_MATCH_WINDOW_MINUTES` | no | `15` | Time window for matching sessions to TeslaMate records |

## Docker images

| Registry | Image | Tags |
|---|---|---|
| GitHub Container Registry | `ghcr.io/n0k0m3/teslamate-supercharger` | `latest`, `x.y`, `x.y.z`, `experimental`, `sha-{hash}` |
| Docker Hub | `n0k0m3/teslamate-supercharger` | `latest`, `x.y`, `x.y.z` |

- `latest` — most recent release
- `experimental` — latest commit on `main` (may be unstable)
- `sha-{hash}` — specific commit build (GHCR only)
