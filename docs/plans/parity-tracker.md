# SquadPy Parity Tracker (SquadJS + SquadTS)

Last updated: 2026-02-14
Primary roadmap: `docs/plans/2026-02-13-parity-and-beyond-roadmap.md`

## Purpose

This is the execution tracker for parity and beyond work.

- `P0`: required before we can claim practical parity.
- `P1`: important parity depth and migration quality.
- `P2`: surpass features and polish.

Status legend:

- `[ ]` Not started
- `[~]` In progress
- `[x]` Done
- `[!]` Blocked

## Owner Map (Replace with actual handles)

- `@core-runtime`: RCON client, command model, reconnect behavior
- `@parser`: log patterns, event correlation, parser contracts
- `@plugins-moderation`: moderation and Discord workflow plugins
- `@plugins-seeding`: seeding/team balance/match control plugins
- `@data-platform`: DBLog, data models, retention, analytics outputs
- `@api-security`: websocket/REST APIs, authn/authz, audit
- `@migration`: config translators and migration tooling
- `@qa-release`: CI gates, soak tests, release readiness

## 0) Phase 0 - Program Setup and Acceptance Harness

- [x] `P0-PROG-001` Create `tests/contracts/` structure and test markers (`@core-runtime`, `P0`)
  - Acceptance: `pytest -m contract` runs and reports discovered tests.
  - Acceptance note (2026-02-14): Added `tests/contracts/core_runtime/test_contract_harness.py` with `contract`, `core_runtime`, and `p0` markers; registered markers in `pyproject.toml`.
- [x] `P0-PROG-002` Create parity fixture packs from real logs (`@parser`, `P0`)
  - Acceptance: fixture manifest exists at `tests/contracts/fixtures/manifest.toml`.
  - Acceptance note (2026-02-14): Added log pack manifest at `tests/contracts/fixtures/manifest.toml` and parser contract test `tests/contracts/parser/test_fixture_manifest.py` for manifest/reference validation.
- [x] `P0-PROG-003` Create RCON golden response fixtures (`@core-runtime`, `P0`)
  - Acceptance: fixtures for all parity commands exist under `tests/contracts/fixtures/rcon/`.
  - Acceptance note (2026-02-14): Added `tests/contracts/fixtures/rcon/manifest.toml` with fixtures for 15 parity command IDs, request/response fixture files under `tests/contracts/fixtures/rcon/`, and contract coverage in `tests/contracts/core_runtime/test_rcon_fixture_manifest.py`.
- [x] `P0-PROG-004` Add contract CI job (`@qa-release`, `P0`)
  - Acceptance: CI runs `unit + contract` and fails on contract regressions.
  - Acceptance note (2026-02-14): Added GitHub Actions workflow `.github/workflows/ci.yml` with separate `unit` (`pytest -m "not contract"`) and `contract` (`pytest -m contract`) jobs.
- [x] `P0-PROG-005` Add integration CI job with mocked Discord/RCON (`@qa-release`, `P0`)
  - Acceptance: CI workflow includes integration matrix stage.
  - Acceptance note (2026-02-14): Added `integration` matrix job (`discord`, `rcon`) in `.github/workflows/ci.yml` running mocked Discord/RCON integration suites.
- [x] `P0-PROG-006` Define event contract schema docs (`@parser`, `P0`)
  - Acceptance: schema document exists at `docs/plans/event-contracts.md`.
  - Acceptance note (2026-02-14): Added `docs/plans/event-contracts.md` defining event envelope, shared types, current event catalog, planned P0 event extensions, and fixture schema rules.
- [x] `P0-PROG-007` Define command contract schema docs (`@core-runtime`, `P0`)
  - Acceptance: schema document exists at `docs/plans/command-contracts.md`.
  - Acceptance note (2026-02-14): Added `docs/plans/command-contracts.md` defining helper-to-command mappings, request/response contract model, and command test acceptance rules.
- [ ] `P0-PROG-008` Create weekly parity report template (`@qa-release`, `P1`)
  - Acceptance: report template exists at `docs/plans/parity-weekly-template.md`.

## 1) Phase 1 - RCON + Event Foundation Parity

### 1.1 RCON command surface

- [x] `P0-RCON-001` Add `ban(player_id, duration, reason)` helper (`@core-runtime`, `P0`)
  - Acceptance: contract test verifies exact command string and response handling.
  - Acceptance note (2026-02-14): Added `RconClient.ban(...)` in `squadpy/rcon/client.py`, unit helper coverage in `tests/test_rcon_helpers.py`, and contract test `tests/contracts/core_runtime/test_rcon_ban_contract.py` validating exact command template + response passthrough.
- [ ] `P0-RCON-002` Add `switch_team(player_id)` helper (`@core-runtime`, `P0`)
  - Acceptance: helper present and covered by command contract test.
- [ ] `P0-RCON-003` Add force team change helper (`@core-runtime`, `P0`)
  - Acceptance: command is exposed and tested with valid/invalid ids.
- [ ] `P0-RCON-004` Add `set_fog_of_war(mode)` helper (`@core-runtime`, `P0`)
  - Acceptance: mode validation and command dispatch tests pass.
- [ ] `P0-RCON-005` Add `set_next_layer(layer)` helper (`@core-runtime`, `P0`)
  - Acceptance: contract test confirms layer string safety and command dispatch.
- [ ] `P1-RCON-006` Add `demote_commander(player_id)` helper (`@core-runtime`, `P1`)
  - Acceptance: helper implemented with tests.
- [ ] `P1-RCON-007` Add explicit `set_team(player_id, team)` helper (`@core-runtime`, `P1`)
  - Acceptance: team enum validation and command test coverage.
- [ ] `P1-RCON-008` Add `end_match` helper (`@core-runtime`, `P1`)
  - Acceptance: command helper and safety guard tests.
- [ ] `P1-RCON-009` Add privileged passthrough wrapper with policy checks (`@core-runtime`, `P1`)
  - Acceptance: unauthorized commands are rejected and audited.

### 1.2 Event types and parser parity

- [ ] `P0-EVT-001` Add `PlayerWarned` event (`@parser`, `P0`)
  - Acceptance: event dataclass + parser contract fixture.
- [ ] `P0-EVT-002` Add `PlayerKicked` event (`@parser`, `P0`)
  - Acceptance: event dataclass + parser contract fixture.
- [ ] `P0-EVT-003` Add `PlayerBanned` event (`@parser`, `P0`)
  - Acceptance: event dataclass + parser contract fixture.
- [ ] `P0-EVT-004` Add `AdminCamPossess` event (`@parser`, `P0`)
  - Acceptance: parser extracts actor identity and target context.
- [ ] `P0-EVT-005` Add `AdminCamUnpossess` event (`@parser`, `P0`)
  - Acceptance: parser contract verifies open/close pairing data.
- [ ] `P0-EVT-006` Add `SquadCreated` event (`@parser`, `P0`)
  - Acceptance: squad id/name/creator fields parsed reliably.
- [ ] `P0-EVT-007` Add explicit `Teamkill` event (`@parser`, `P0`)
  - Acceptance: teamkill detection path has dedicated contracts.
- [ ] `P1-EVT-008` Add `PlayerSwitchedTeam` event (`@parser`, `P1`)
  - Acceptance: parser and event contracts pass.
- [ ] `P1-EVT-009` Add `NextLayerSet` event (`@parser`, `P1`)
  - Acceptance: layer mutation is emitted as structured event.
- [ ] `P1-EVT-010` Add seeding threshold transition events (`@parser`, `P1`)
  - Acceptance: threshold up/down events tested in plugin integration.
- [ ] `P1-EVT-011` Add admin command event normalization (`@parser`, `P1`)
  - Acceptance: command-origin metadata emitted consistently.

### 1.3 Runtime reliability contracts

- [ ] `P0-RT-001` Add reconnect replay contract tests (`@core-runtime`, `P0`)
  - Acceptance: queued commands flush correctly after reconnect.
- [ ] `P0-RT-002` Add out-of-order response stress tests (`@core-runtime`, `P0`)
  - Acceptance: request correlation remains deterministic under concurrency.
- [ ] `P1-RT-003` Add typed error taxonomy for RCON failures (`@core-runtime`, `P1`)
  - Acceptance: callers can branch on error classes in tests.

## 2) Phase 2 - Moderation Plugin Parity

### 2.1 New moderation/Discord plugins

- [ ] `P0-PLUG-MOD-001` Implement `plugins/chat_commands` (`@plugins-moderation`, `P0`)
  - Acceptance: role-based command permissions and cooldown tests pass.
- [ ] `P0-PLUG-MOD-002` Implement `plugins/discord_admin_broadcast` (`@plugins-moderation`, `P0`)
  - Acceptance: Discord-triggered broadcast reaches server and logs action.
- [ ] `P0-PLUG-MOD-003` Implement `plugins/discord_admin_cam_logs` (`@plugins-moderation`, `P0`)
  - Acceptance: admin cam possess/unpossess events post to Discord.
- [ ] `P0-PLUG-MOD-004` Implement `plugins/discord_killfeed` (`@plugins-moderation`, `P0`)
  - Acceptance: kill events produce correct formatted feed entries.
- [ ] `P0-PLUG-MOD-005` Implement `plugins/discord_teamkill` (`@plugins-moderation`, `P0`)
  - Acceptance: teamkill-only feed messages with attacker/victim details.
- [ ] `P0-PLUG-MOD-006` Implement `plugins/discord_round_events` (`@plugins-moderation`, `P0`)
  - Acceptance: round start/end/winner payloads are posted reliably.
- [ ] `P1-PLUG-MOD-007` Implement `plugins/discord_squad_created` (`@plugins-moderation`, `P1`)
  - Acceptance: squad creation alerts include team and creator metadata.
- [ ] `P1-PLUG-MOD-008` Implement `plugins/discord_fob_hab_damage` (`@plugins-moderation`, `P1`)
  - Acceptance: deployable damage events are summarized with thresholds.
- [ ] `P1-PLUG-MOD-009` Implement `plugins/discord_rcon_console` (`@plugins-moderation`, `P1`)
  - Acceptance: privileged console command execution is audited and gated.

### 2.2 Upgrade existing plugins to parity depth

- [ ] `P0-PLUG-UPG-001` Upgrade `tk_warn` config flexibility and edge cases (`@plugins-moderation`, `P0`)
  - Acceptance: parity behavior matrix tests pass.
- [ ] `P0-PLUG-UPG-002` Upgrade `admin_request` ticket lifecycle depth (`@plugins-moderation`, `P0`)
  - Acceptance: claim, relay, close, and timeout behaviors are tested.
- [ ] `P1-PLUG-UPG-003` Upgrade `server_status` to richer parity fields (`@plugins-moderation`, `P1`)
  - Acceptance: map/layer/factions/tick/player/squad values validated.

## 3) Phase 3 - Seeding, Team Balance, Match Control

- [ ] `P0-SEED-001` Implement `plugins/seeding_mode` (`@plugins-seeding`, `P0`)
  - Acceptance: seed/live mode transition contracts pass.
- [ ] `P0-SEED-002` Implement `plugins/auto_seed_low_players` (`@plugins-seeding`, `P0`)
  - Acceptance: low-population automation actions validated by tests.
- [ ] `P0-SEED-003` Implement `plugins/auto_rejoin_team` (`@plugins-seeding`, `P0`)
  - Acceptance: team assignment persistence behavior tested.
- [ ] `P0-SEED-004` Implement `plugins/team_randomizer` (`@plugins-seeding`, `P0`)
  - Acceptance: randomization rules and fairness constraints tested.
- [ ] `P0-SEED-005` Implement `plugins/switch_command` (`@plugins-seeding`, `P0`)
  - Acceptance: user-triggered switch flow with cooldown checks tested.
- [ ] `P0-SEED-006` Implement `plugins/end_match_vote` (`@plugins-seeding`, `P0`)
  - Acceptance: vote quorum and action thresholds tested.
- [ ] `P1-SEED-007` Implement `plugins/max_player_in_squad` (`@plugins-seeding`, `P1`)
  - Acceptance: enforcement, exemptions, and warning paths tested.
- [ ] `P1-SEED-008` Implement `plugins/squad_name_validator` (`@plugins-seeding`, `P1`)
  - Acceptance: invalid names trigger warnings/actions per config.
- [ ] `P1-SEED-009` Implement `plugins/intervalled_broadcasts` (`@plugins-seeding`, `P1`)
  - Acceptance: schedule and dedupe behavior covered by tests.
- [ ] `P1-SEED-010` Implement `plugins/fog_of_war` (`@plugins-seeding`, `P1`)
  - Acceptance: fog mode changes are safe, audited, and reversible.
- [ ] `P1-SEED-011` Implement `plugins/heli_crash_broadcast` (`@plugins-seeding`, `P1`)
  - Acceptance: relevant event detection and broadcast tests pass.
- [ ] `P1-SEED-012` Implement `plugins/knife_broadcast` (`@plugins-seeding`, `P1`)
  - Acceptance: knife kill detection and formatting tests pass.

## 4) Phase 4 - Data, API, Integration Parity

### 4.1 Data and DBLog parity

- [ ] `P0-DATA-001` Implement `plugins/db_log` core schema (`@data-platform`, `P0`)
  - Acceptance: migration creates expected tables/indexes.
- [ ] `P0-DATA-002` Add versioned migrations for db log (`@data-platform`, `P0`)
  - Acceptance: forward migration and clean bootstrap tests pass.
- [ ] `P1-DATA-003` Add retention and pruning jobs (`@data-platform`, `P1`)
  - Acceptance: pruning policy tests validate retention windows.
- [ ] `P1-DATA-004` Add materialized views/query helpers for analytics (`@data-platform`, `P1`)
  - Acceptance: dashboard query smoke tests pass.

### 4.2 API and remote control

- [ ] `P0-API-001` Add authenticated websocket control service (`@api-security`, `P0`)
  - Acceptance: command dispatch + auth rejection contracts pass.
- [ ] `P0-API-002` Add authenticated REST control endpoints (`@api-security`, `P0`)
  - Acceptance: health, status, and command endpoints tested.
- [ ] `P0-API-003` Add audit logging for all privileged actions (`@api-security`, `P0`)
  - Acceptance: audit records include actor, origin, target, outcome.
- [ ] `P1-API-004` Add role-based access control model (`@api-security`, `P1`)
  - Acceptance: RBAC integration tests pass for allowed/denied actions.
- [ ] `P1-API-005` Add signed webhook policy support (`@api-security`, `P1`)
  - Acceptance: valid signatures accepted, invalid rejected.

### 4.3 Connector parity

- [ ] `P0-CONN-001` Add connector abstraction under `squadpy/connectors/` (`@api-security`, `P0`)
  - Acceptance: connector interface and lifecycle tests pass.
- [ ] `P1-CONN-002` Add external moderation API connector #1 (`@api-security`, `P1`)
  - Acceptance: integration tests use mocked API and pass.
- [ ] `P1-CONN-003` Add external moderation API connector #2 (`@api-security`, `P1`)
  - Acceptance: integration tests use mocked API and pass.
- [ ] `P1-CONN-004` Add admin list sync engine (local + remote + sftp) (`@api-security`, `P1`)
  - Acceptance: merge precedence and conflict behavior covered by tests.

## 5) Phase 5 - Migration and Compatibility

- [ ] `P0-MIG-001` Build `scripts/migrate_from_squadjs.py` (`@migration`, `P0`)
  - Acceptance: sample SquadJS config migrates with report output.
- [ ] `P0-MIG-002` Build `scripts/migrate_from_squadts.py` (`@migration`, `P0`)
  - Acceptance: sample SquadTS config migrates with report output.
- [ ] `P0-MIG-003` Build config linter/fixer for migrated TOML (`@migration`, `P0`)
  - Acceptance: linter emits actionable fixups and severity levels.
- [ ] `P1-MIG-004` Publish migration cookbook (`@migration`, `P1`)
  - Acceptance: docs include end-to-end cutover steps and rollback.
- [ ] `P1-MIG-005` Build plugin behavior mapping matrix (`@migration`, `P1`)
  - Acceptance: every source plugin has mapped target/equivalent strategy.

## 6) Phase 6 - Surpass Features

- [ ] `P2-BEYOND-001` Multi-server orchestration in one process (`@core-runtime`, `P2`)
  - Acceptance: isolated contexts run N servers without cross-talk.
- [ ] `P2-BEYOND-002` RCON broker mode (`@core-runtime`, `P2`)
  - Acceptance: one upstream RCON socket, many authenticated clients.
- [ ] `P2-BEYOND-003` Prometheus metrics exporter (`@qa-release`, `P2`)
  - Acceptance: standard runtime and plugin metrics are exposed.
- [ ] `P2-BEYOND-004` Trace instrumentation for critical paths (`@qa-release`, `P2`)
  - Acceptance: traces show RCON command latency and parser timing.
- [ ] `P2-BEYOND-005` Health/readiness endpoints (`@qa-release`, `P2`)
  - Acceptance: probes reflect dependency state accurately.
- [ ] `P2-BEYOND-006` Plugin watchdog/failure budgets (`@core-runtime`, `P2`)
  - Acceptance: repeated plugin failures trigger controlled degradation.
- [ ] `P2-BEYOND-007` Plugin scaffolder CLI (`@plugins-moderation`, `P2`)
  - Acceptance: CLI creates tested plugin skeleton with typed hooks.
- [ ] `P2-BEYOND-008` Local simulation harness (`@qa-release`, `P2`)
  - Acceptance: local replay of logs/RCON fixtures supports plugin dev loops.

## 7) Plugin Parity Matrix (Tracking View)

Use this matrix for quick parity reporting. Update `Status` each sprint.

| Capability | SquadJS/SquadTS | SquadPy status | Tracker IDs |
|---|---|---|---|
| Auto kick unassigned | Yes | Done | Existing |
| TK warn | Yes | Partial | `P0-PLUG-UPG-001` |
| Admin request workflow | Yes | Partial | `P0-PLUG-UPG-002` |
| Discord chat bridge | Yes | Done | Existing |
| Server status embed | Yes | Partial | `P1-PLUG-UPG-003` |
| Chat commands | Yes | Missing | `P0-PLUG-MOD-001` |
| Discord admin broadcast | Yes | Missing | `P0-PLUG-MOD-002` |
| Discord admin cam logs | Yes | Missing | `P0-PLUG-MOD-003` |
| Discord killfeed | Yes | Missing | `P0-PLUG-MOD-004` |
| Discord teamkill feed | Yes | Missing | `P0-PLUG-MOD-005` |
| Discord round events | Yes | Missing | `P0-PLUG-MOD-006` |
| Discord squad created | Yes | Missing | `P1-PLUG-MOD-007` |
| Discord FOB/HAB damage | Yes | Missing | `P1-PLUG-MOD-008` |
| Discord RCON console | Yes | Missing | `P1-PLUG-MOD-009` |
| Seeding mode | Yes | Missing | `P0-SEED-001` |
| Auto seed low players | Yes | Missing | `P0-SEED-002` |
| Team randomizer | Yes | Missing | `P0-SEED-004` |
| Switch command | Yes | Missing | `P0-SEED-005` |
| End match vote | Yes | Missing | `P0-SEED-006` |
| Max players in squad | Yes | Missing | `P1-SEED-007` |
| Squad name validator | Yes | Missing | `P1-SEED-008` |
| Fog of war automation | Yes | Missing | `P1-SEED-010` |
| DB event logging plugin | Yes | Missing | `P0-DATA-001` |
| Websocket API plugin/service | Yes | Missing | `P0-API-001` |

## 8) Release Gates

### Parity claim gates (all required)

- [ ] `GATE-001` All `P0-*` items completed.
- [ ] `GATE-002` Contract suite green in CI for 14 consecutive days.
- [ ] `GATE-003` Integration suite green in CI for 14 consecutive days.
- [ ] `GATE-004` Soak test pass for 30 days, no Sev-1 incidents.
- [ ] `GATE-005` Migration scripts validated on at least 3 real community configs.
- [ ] `GATE-006` Operator sign-off from pilot servers.

### Beyond release gates

- [ ] `GATE-B-001` At least 3 `P2-BEYOND-*` features released and documented.
- [ ] `GATE-B-002` Observability baseline dashboard pack published.
- [ ] `GATE-B-003` Multi-server or broker mode validated in pilot environment.

## 9) Weekly Update Block (Copy/Paste)

Week of:

- Completed IDs:
- In-progress IDs:
- Blocked IDs:
- New risks:
- Mitigations applied:
- Next week top 5 IDs:
