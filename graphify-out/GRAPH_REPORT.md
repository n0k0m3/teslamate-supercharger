# Graph Report - .  (2026-06-22)

## Corpus Check
- Corpus is ~4,621 words - fits in a single context window. You may not need a graph.

## Summary
- 126 nodes · 192 edges · 17 communities (9 shown, 8 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 24 edges (avg confidence: 0.67)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_DB Schema & Architecture|DB Schema & Architecture]]
- [[_COMMUNITY_Daemon Orchestration|Daemon Orchestration]]
- [[_COMMUNITY_Database Layer|Database Layer]]
- [[_COMMUNITY_API & Module Entry|API & Module Entry]]
- [[_COMMUNITY_Session Matching|Session Matching]]
- [[_COMMUNITY_Configuration Module|Configuration Module]]
- [[_COMMUNITY_Token Decryption|Token Decryption]]
- [[_COMMUNITY_Config Helpers|Config Helpers]]
- [[_COMMUNITY_Crypto Helpers|Crypto Helpers]]
- [[_COMMUNITY_MCP Server Config|MCP Server Config]]
- [[_COMMUNITY_Docker Deployment|Docker Deployment]]
- [[_COMMUNITY_MQTT Connect Handler|MQTT Connect Handler]]
- [[_COMMUNITY_MQTT Disconnect Handler|MQTT Disconnect Handler]]
- [[_COMMUNITY_Debug Skill|Debug Skill]]
- [[_COMMUNITY_Explore Skill|Explore Skill]]
- [[_COMMUNITY_Refactor Skill|Refactor Skill]]
- [[_COMMUNITY_Review Skill|Review Skill]]

## God Nodes (most connected - your core abstractions)
1. `Daemon` - 13 edges
2. `MQTTClient` - 11 edges
3. `get_conn` - 11 edges
4. `Config` - 9 edges
5. `Daemon._fetch_and_store` - 9 edges
6. `ConfigError` - 8 edges
7. `TeslaAPIError` - 8 edges
8. `Daemon.run` - 8 edges
9. `decrypt_token()` - 7 edges
10. `fetch_charging_history_with_refresh()` - 6 edges

## Surprising Connections (you probably didn't know these)
- `supercharger Docker Service` --references--> `Config`  [INFERRED]
  docker-compose.yml → teslamate_supercharger/config.py
- `teslamate-supercharger Architecture Overview` --references--> `decrypt_token`  [EXTRACTED]
  CLAUDE.md → teslamate_supercharger/crypto.py
- `teslamate-supercharger Architecture Overview` --references--> `Daemon`  [EXTRACTED]
  CLAUDE.md → teslamate_supercharger/main.py
- `teslamate-supercharger Architecture Overview` --references--> `upsert_supercharger_session`  [EXTRACTED]
  CLAUDE.md → teslamate_supercharger/db.py
- `teslamate-supercharger Architecture Overview` --references--> `MQTTClient`  [EXTRACTED]
  CLAUDE.md → teslamate_supercharger/mqtt_client.py

## Import Cycles
- 1-file cycle: `teslamate_supercharger/main.py -> teslamate_supercharger/main.py`
- 1-file cycle: `teslamate_supercharger/db.py -> teslamate_supercharger/db.py`
- 1-file cycle: `teslamate_supercharger/session_matcher.py -> teslamate_supercharger/session_matcher.py`

## Hyperedges (group relationships)
- **Supercharger Session Write Pipeline** — main_daemon__fetch_and_store, session_matcher_find_matching_session, session_matcher_extract_session_fields, db_upsert_supercharger_session, db_update_charging_process_cost [EXTRACTED 1.00]
- **Daemon Startup Sequence** — main_daemon_run, db_init_pool, db_ensure_schema, main_daemon__load_tokens, main_daemon__load_car_vins, main_daemon__backfill [EXTRACTED 1.00]
- **TeslaMate Token Decryption Flow** — main_daemon__load_tokens, db_get_encrypted_tokens, crypto_decrypt_token, crypto__derive_key_utf8, crypto__derive_key_b64 [EXTRACTED 1.00]

## Communities (17 total, 8 thin omitted)

### Community 0 - "DB Schema & Architecture"
Cohesion: 0.10
Nodes (31): Tesla Charging History API Response Schema, teslamate-supercharger Architecture Overview, ensure_schema, find_charging_process, get_car_vins, get_conn, get_encrypted_tokens, get_uncosted_supercharger_processes (+23 more)

### Community 1 - "Daemon Orchestration"
Cohesion: 0.15
Nodes (7): Daemon, main(), datetime, Fetch history for any recent Supercharger sessions still missing cost., MQTTClient, MQTT subscriber with per-car state machine.  Subscribes to TeslaMate's MQTT topi, Connect and block forever (call from the main thread).

### Community 2 - "Database Layer"
Cohesion: 0.17
Nodes (12): ensure_schema(), find_charging_process(), get_car_vins(), get_conn(), get_uncosted_supercharger_processes(), init_pool(), Config, datetime (+4 more)

### Community 3 - "API & Module Entry"
Cohesion: 0.23
Nodes (11): Exception, teslamate-supercharger daemon entry point.  Startup sequence: 1. Load config fro, fetch_charging_history(), fetch_charging_history_with_refresh(), Tesla charging history API client with token refresh support., Return (new_access_token, new_refresh_token)., Fetch the most recent charging sessions for the given VIN.      Returns a list o, Fetch charging history, transparently refreshing the access token on 401.      R (+3 more)

### Community 4 - "Session Matching"
Cohesion: 0.31
Nodes (9): extract_cost(), extract_session_fields(), find_matching_session(), _parse_dt(), datetime, Match Tesla API charging sessions to TeslaMate charging_processes rows., Return the session whose stop time falls within window_minutes of trigger_time., Return (total_cost, currency_code) summing CHARGING + PARKING fees. (+1 more)

### Community 5 - "Configuration Module"
Cohesion: 0.39
Nodes (6): Config, ConfigError, _int(), _optional(), _require(), Config

### Community 6 - "Token Decryption"
Cohesion: 0.43
Nodes (6): _decrypt(), decrypt_token(), _derive_key_b64(), _derive_key_utf8(), Decrypt tokens stored by TeslaMate using cloak_ecto AES.GCM.256.  Binary layout, Decrypt a single token bytea value from TeslaMate's private.tokens table.

### Community 7 - "Config Helpers"
Cohesion: 0.50
Nodes (5): _int, _optional, _require, Config.from_env, ConfigError

### Community 8 - "Crypto Helpers"
Cohesion: 0.40
Nodes (5): _decrypt, _derive_key_b64, _derive_key_utf8, cloak_ecto AES-GCM-256 Token Encryption, decrypt_token

## Knowledge Gaps
- **19 isolated node(s):** `uvx`, `Config`, `_optional`, `_decrypt`, `_derive_key_utf8` (+14 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MQTTClient` connect `Daemon Orchestration` to `API & Module Entry`, `Configuration Module`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **Why does `Daemon` connect `Daemon Orchestration` to `API & Module Entry`, `Configuration Module`?**
  _High betweenness centrality (0.054) - this node is a cross-community bridge._
- **Why does `Config` connect `Configuration Module` to `Daemon Orchestration`, `Database Layer`, `API & Module Entry`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `Daemon` (e.g. with `Config` and `ConfigError`) actually correct?**
  _`Daemon` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `MQTTClient` (e.g. with `Daemon` and `Config`) actually correct?**
  _`MQTTClient` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `get_conn` (e.g. with `find_charging_process` and `get_encrypted_tokens`) actually correct?**
  _`get_conn` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `Config` (e.g. with `Config` and `datetime`) actually correct?**
  _`Config` has 5 INFERRED edges - model-reasoned connections that need verification._