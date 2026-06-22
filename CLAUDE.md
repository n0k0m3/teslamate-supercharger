# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

`teslamate-supercharger` is a Python daemon that runs alongside [TeslaMate](https://github.com/adriankumpf/teslamate). When a Supercharger session ends, it fetches the cost and energy data from the Tesla charging history API and writes it back into TeslaMate's PostgreSQL database — both into a new `supercharger_sessions` table and into the `cost` column it adds to TeslaMate's existing `charging_processes` table.

## Running the daemon

```bash
# Install dependencies
uv sync

# Copy and fill in env vars
cp .env.example .env

# Run directly
uv run python -m teslamate_supercharger.main
```

Required env vars: `DATABASE_HOST`, `DATABASE_PASS`, `TESLA_CLIENT_ID`, `TESLA_CLIENT_SECRET`.  
All others have defaults (see `config.py`).

## Docker

The service is meant to be added to an existing TeslaMate `docker-compose.yml`. `docker-compose.yml` in this repo is a snippet, not a standalone stack — it references an external network named `teslamate` and depends on `database`, `mosquitto`, and `teslamate` services already running.

```bash
docker build -t teslamate-supercharger .
```

## Architecture

The data flow on each Supercharger session:

```
MQTT (TeslaMate publishes car state)
  → MQTTClient detects charging_state: Charging/Starting → Complete while fast_charger_present=true
  → Daemon._on_supercharge_complete(car_id) [dispatched to ThreadPoolExecutor after API_FETCH_DELAY_SECONDS]
  → tesla_api.fetch_charging_history() [Fleet API, page 1, filters by VIN client-side]
  → session_matcher.find_matching_session() [matches by stop time within SESSION_MATCH_WINDOW_MINUTES]
  → session_matcher.extract_session_fields()
  → db.upsert_supercharger_session() + db.update_charging_process_cost()
```

On startup, the daemon also backfills any `charging_processes` rows from the last 24 hours that still have `cost IS NULL`.

For a full historical backfill (all 220+ sessions), run the standalone script:

```bash
uv run python -m teslamate_supercharger.backfill
# or via Docker:
docker compose run --rm supercharger python -m teslamate_supercharger.backfill
```

### Module responsibilities

- **`main.py`** — `Daemon` class orchestrates startup and the MQTT→API→DB pipeline. `main()` is the entry point.
- **`backfill.py`** — Standalone one-shot script (`python -m teslamate_supercharger.backfill`). Fetches all pages of Fleet API history and upserts every session. Safe to re-run.
- **`config.py`** — All configuration comes from environment variables. `Config.from_env()` raises `ConfigError` on missing required vars.
- **`mqtt_client.py`** — Subscribes to `teslamate/cars/+/{charging_state,fast_charger_present,charger_power}`. Maintains per-car state dict to detect the `Charging → Complete` transition. Fires callback only when `fast_charger_present=true`.
- **`tesla_api.py`** — Acquires a Fleet API token via `client_credentials` grant from `fleet-auth.prd.vn.cloud.tesla.com` using `TESLA_CLIENT_ID`/`TESLA_CLIENT_SECRET`. Token lifetime is 8h; re-acquired on 401. `fetch_charging_history()` fetches one page; `fetch_all_charging_history()` paginates all results. See `charging_fleet.json` for a sample response.
- **`session_matcher.py`** — Maps Fleet API response fields to DB columns. Field name constants (`_FIELD_*`) are defined at the top; update if the API schema changes. Cost is summed from `fees[]` entries where `feeType` is `CHARGING` or `PARKING`. Energy is derived from `usageBase` where `uom=kwh`.
- **`db.py`** — PostgreSQL via `psycopg2` thread-safe connection pool. `ensure_schema()` runs `CREATE TABLE IF NOT EXISTS supercharger_sessions` and `ALTER TABLE charging_processes ADD COLUMN IF NOT EXISTS cost` on every startup — safe to re-run.
- **`crypto.py`** — Unused since switching to Fleet API auth. Can be deleted.

### Key coupling points with TeslaMate

- Reads `cars` table for VINs
- Reads and writes `charging_processes` table (adds `cost` column, links sessions by `end_date`)
- Creates its own `supercharger_sessions` table with a FK to `charging_processes`

## Backlog

**Reliability**
- `crypto.py` is dead code — delete it
- Startup backfill window is hardcoded to 24h — if daemon is down longer, sessions are silently missed; make `BACKFILL_LOOKBACK_HOURS` a config var
- Verify multi-car behaviour: `seen_car_ids` in `_backfill()` deduplicates by car, which is correct, but worth an end-to-end test

**Observability**
- No Dockerfile `HEALTHCHECK` — Docker/compose can't detect a stuck daemon
- No log line when a session is skipped because cost is already set (useful for debugging re-runs)

**Nice to have**
- ~~Multi-arch image builds (arm64 for Raspberry Pi / NAS)~~ done

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
