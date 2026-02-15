# SquadPy

Python framework for [Squad](https://joinsquad.com/) server operations, inspired by SquadJS and SquadTS, with typed Python APIs and async-first runtime behavior.

## Highlights

- Async RCON client with reconnect and command correlation.
- Parser-backed event bus with typed events for plugin workflows.
- Broad built-in plugin coverage for moderation, seeding, Discord, and data logging.
- Control API with token auth, optional RBAC, signed webhook policy, and audit records.
- Observability endpoints: `/metrics`, `/api/health`, `/api/readiness`, `/api/traces`.
- One-process multi-server orchestration (`config/servers/*` discovery).
- RCON broker primitive (`RconBroker`) for one upstream socket and many authenticated clients.
- Plugin watchdog failure budgets for controlled degradation.
- Dev tooling for migration analysis, plugin scaffolding, and local replay simulation.

## Requirements

- Python 3.12+
- Squad dedicated server with RCON enabled

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Runtime Modes

### Single Server (Default)

1. Copy config examples:

```bash
cp config/server.toml.example config/server.toml
cp config/logging.toml.example config/logging.toml
```

2. Minimum `config/server.toml`:

```toml
[rcon]
host = "127.0.0.1"
port = 21114
password = "your_rcon_password"
```

3. Run:

```bash
python -m squadpy
```

### Mode Selection (`auto`, `single`, `multi`)

SquadPy runtime mode precedence:

1. CLI flag: `python -m squadpy --mode <auto|single|multi>`
2. Environment variable: `SQUADPY_RUNTIME_MODE`
3. Config file: `config/runtime.toml`
4. Default: `auto`

For DB isolation policy in multi-server mode:

1. Environment variable: `SQUADPY_REQUIRE_PER_SERVER_DATABASE`
2. Config file: `config/runtime.toml`
3. Default: `false`

Examples:

```bash
python -m squadpy --mode single
python -m squadpy --mode multi
SQUADPY_RUNTIME_MODE=single python -m squadpy
SQUADPY_REQUIRE_PER_SERVER_DATABASE=true python -m squadpy --mode multi
```

`config/runtime.toml` example:

```toml
mode = "auto" # auto | single | multi
require_per_server_database = false
```

Behavior summary:

- `auto`: run multi-server only when valid `config/servers/*/server.toml` definitions are present; otherwise run single-server.
- `single`: always run `config/server.toml` path and ignore multi-server definitions.
- `multi`: require at least one `config/servers/*/server.toml` definition; exits with clear error if none found.
- `require_per_server_database=true`: in multi mode, each discovered server must have `config/servers/<name>/database.toml`; shared fallback is disallowed.

### Multi-Server (One Process, N Server Contexts)

In `auto` mode, multi-server activates when at least one `config/servers/<name>/server.toml` exists.

Recommended layout:

```text
config/
  logging.toml                  # optional shared fallback
  database.toml                 # optional shared fallback
  plugins/                      # canonical plugin examples/defaults
    *.toml.example
  servers/
    _template/
      server.toml.example
      database.toml.example
    ph-server-1/
      server.toml               # required
      database.toml             # recommended unique DB per server
      logging.toml              # optional per-server override
      plugins/                  # optional per-server overrides only
        admin_request.toml
    ph-server-2/
      server.toml
      database.toml
```

Bootstrap example:

```bash
mkdir -p config/servers/ph-server-1 config/servers/ph-server-2
cp config/servers/_template/server.toml.example config/servers/ph-server-1/server.toml
cp config/servers/_template/server.toml.example config/servers/ph-server-2/server.toml
cp config/servers/_template/database.toml.example config/servers/ph-server-1/database.toml
cp config/servers/_template/database.toml.example config/servers/ph-server-2/database.toml
```

Canonical server template (`config/servers/_template/server.toml.example`):

```toml
[rcon]
host = "10.0.1.21"
port = 21114
password = "replace_with_rcon_password"

[log]
enabled = true
mode = "local"
path = "/srv/squad/SquadGame.log"

[api]
enabled = true
host = "127.0.0.1"
port = 18091
websocket_path = "/ws/control"
auth_token = "replace_with_api_token"
```

Canonical database template (`config/servers/_template/database.toml.example`):

```toml
enabled = true
driver = "sqlite"
path = "data/server-1.db" # use a unique path per server
```

Operational rules:

- Use distinct RCON endpoints per server context.
- Use distinct log sources/paths per server context.
- Use distinct API ports per server context.
- Prefer distinct per-server DB configs/paths (`config/servers/<name>/database.toml`) to avoid data mixing.
- If per-server DB config is missing and shared `config/database.toml` exists, SquadPy warns and falls back to shared DB.
- Keep canonical plugin examples in `config/plugins/*.toml.example`.
- Use `config/servers/<name>/plugins/*.toml` only when a server needs overrides that differ from shared defaults.
- By default, plugins without `config/plugins/<plugin>.toml` are disabled; set `[plugins].auto_enable_missing_configs = true` in `server.toml` to opt into legacy auto-enable behavior.

### RCON Broker Mode (Library Primitive)

`RconBroker` is available for embedding into local control services:

```python
from squadpy.rcon.client import RconClient
from squadpy.rcon.broker import RconBroker

upstream = RconClient(host="127.0.0.1", port=21114, password="secret")
await upstream.connect()

broker = RconBroker(
    upstream,
    clients={"tool-a": "token-a", "tool-b": "token-b"},
)

response = await broker.execute(token="token-a", command="ListPlayers")
```

## Configuration Overview

Core files:

| File | Purpose |
|---|---|
| `config/runtime.toml` | Optional runtime mode and DB isolation selection |
| `config/server.toml` | Single-server runtime config |
| `config/logging.toml` | Logging setup |
| `config/database.toml` | Optional DB setup |
| `config/plugins/*.toml` | Canonical per-plugin settings/examples |
| `config/servers/_template/*.example` | Copy-ready multi-server starter templates |
| `config/servers/<name>/server.toml` | Multi-server per-context config |
| `config/servers/<name>/database.toml` | Multi-server per-context DB config |
| `config/servers/<name>/plugins/*.toml` | Optional per-server plugin overrides |

`server.toml` sections:

- `[rcon]` required.
- `[log]` optional local/SFTP log tail.
- `[discord]` optional Discord bot connector.
- `[api]` optional REST + websocket control API.
- `[plugins]` optional plugin activation policy (`auto_enable_missing_configs`).
- `[plugin_watchdog]` optional failure-budget controls (`enabled`, `failure_threshold`, `failure_window_seconds`).

## Control API, Security, and Observability

If `[api].enabled = true`, SquadPy serves:

- `GET /api/health`
- `GET /api/readiness`
- `GET /api/status`
- `GET /api/traces`
- `GET /metrics` (Prometheus format)
- `POST /api/command`
- `POST /api/layers/query`
- `POST /api/webhook/command`
- `WS /ws/control` (path configurable)

Auth and policy:

- API token via `Authorization: Bearer <token>` (or `?token=` query fallback).
- Optional RBAC via `[api].rbac_*` settings.
- Optional signed webhook policy via `[api].webhook_signing_*` settings.

## Built-In Plugins

Directory: `plugins/<plugin_name>/plugin.py`.

Moderation and admin:

- `auto_kick_unassigned`
- `tk_warn`
- `admin_request`
- `chat_commands`
- `switch_command`
- `max_player_in_squad`
- `squad_name_validator`
- `end_match_vote`

Seeding and gameplay automation:

- `seeding_mode`
- `auto_seed_low_players`
- `auto_rejoin_team`
- `team_randomizer`
- `intervalled_broadcasts`
- `fog_of_war`
- `knife_broadcast`
- `heli_crash_broadcast`

Discord integrations:

- `discord_chat_bridge`
- `discord_admin_broadcast`
- `discord_admin_cam_logs`
- `discord_killfeed`
- `discord_teamkill`
- `discord_round_events`
- `discord_squad_created`
- `discord_fob_hab_damage`
- `discord_rcon_console`
- `server_status`
- `plugin_manager`

Data:

- `db_log`

## Tooling Scripts

| Script | Purpose |
|---|---|
| `scripts/migrate_from_squadjs.py` | Report-first SquadJS config analyzer |
| `scripts/migrate_from_squadts.py` | Report-first SquadTS config analyzer |
| `scripts/lint_migrated_toml.py` | Lint migrated TOML and emit fixups/severity |
| `scripts/record_gate_windows.py` | Record daily gate-window evidence for `GATE-002`/`GATE-003`/`GATE-004` |
| `scripts/scaffold_plugin.py` | Generate typed plugin skeleton + starter tests/config |
| `scripts/simulate_local_replay.py` | Replay logs/RCON fixtures through plugins locally |

## Plugin Development

### Scaffolder

Create a typed plugin skeleton:

```bash
.venv/bin/python scripts/scaffold_plugin.py my_new_plugin
```

This generates:

- `plugins/my_new_plugin/plugin.py`
- `tests/test_plugin_my_new_plugin.py`
- `config/plugins/my_new_plugin.toml.example`

### Manual Plugin Example

```python
from squadpy.events.types import ChatMessage, PlayerConnected
from squadpy.plugin import Plugin, on_event, periodic


class MyPlugin(Plugin):
    name = "My Plugin"
    description = "Does something useful"
    requires = ["rcon"]

    @on_event("player_connected")
    async def handle_player_connected(self, event: PlayerConnected) -> None:
        await self.rcon.warn(event.eos_id, "Welcome")

    @on_event("chat_message")
    async def handle_chat(self, event: ChatMessage) -> None:
        if event.message == "!ping":
            await self.rcon.warn(event.eos_id, "pong")

    @periodic(seconds=60)
    async def periodic_task(self) -> None:
        players = await self.rcon.list_players()
        self.logger.info("Players online: %d", len(players))
```

## Local Simulation Harness

Replay fixtures through plugins for fast local loops:

```bash
.venv/bin/python scripts/simulate_local_replay.py \
  tests/fixtures/simulation/logs/basic_replay.log \
  --rcon-fixture tests/fixtures/simulation/rcon/replay.json \
  --plugin sim_demo_plugin \
  --plugins-dir tests/fixtures/simulation/plugins \
  --plugin-config-dir tests/fixtures/simulation/config/plugins
```

## Testing and Typechecking

```bash
make setup-dev
make test
make test-unit
make test-contract
make test-integration
make test-integration-discord
make test-integration-rcon
make typecheck
```

Focused test run example:

```bash
.venv/bin/python -m pytest tests/test_server.py -v
```

## Gate Tracking Automation

Record daily parity-gate windows (`GATE-002`/`GATE-003`/`GATE-004`):

```bash
.venv/bin/python scripts/record_gate_windows.py --sev1 none --notes "daily check"
```

If running from CI/manual status source without local test execution:

```bash
.venv/bin/python scripts/record_gate_windows.py \
  --skip-test-runs \
  --contract-status pass \
  --integration-status pass \
  --sev1 none \
  --notes "GitHub Actions run #1234"
```

## Project Layout

```text
squadpy/
  api/                 Control API service and HTTP/WS endpoints
  rcon/                RCON client, protocol, and broker
  log_parser/          Log readers, parser, and pattern matching
  events/              Event bus and typed dataclasses
  discord/             Discord connector
  database/            SQLAlchemy async integration
  layers/              Layer catalog services
  connectors/          External moderation connector primitives
  admin_lists/         Admin list sync engine
  simulation/          Local replay harness
  multi_server.py      Multi-server runtime orchestration
  plugin_loader.py     Plugin discovery and lifecycle
  server.py            Main orchestrator
plugins/               Built-in plugins
config/                Runtime and plugin TOML configs
scripts/               Migration/scaffolding/simulation utilities
tests/                 Unit and contract coverage
docs/                  Plans, runbooks, and parity tracker (`docs/plans/README.md`)
```

## License

GNU GPL v3.0. See `LICENSE`.
