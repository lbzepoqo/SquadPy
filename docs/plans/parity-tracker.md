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

## Current Sprint Focus (2026-02-14)

- Active in-progress IDs: none.
- Rationale: completed second seeding wave, DBLog foundation/migrations, and authenticated websocket/REST control with audit baseline (`P0-SEED-002`, `P0-SEED-003`, `P0-SEED-004`, `P0-SEED-005`, `P0-SEED-006`, `P0-DATA-001`, `P0-DATA-002`, `P0-API-001`, `P0-API-002`, `P0-API-003`) after finishing the moderation+seeding kickoff wave; next execution focus is making layer metadata a shared SquadPy subsystem instead of plugin-local fetch logic.
- Next queued IDs: `P1-DATA-003`, `P1-DATA-004`, `P1-API-004`.

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
- [x] `P0-PROG-008` Create weekly parity report template (`@qa-release`, `P1`)
  - Acceptance: report template exists at `docs/plans/parity-weekly-template.md`.
  - Acceptance note (2026-02-14): Added `docs/plans/parity-weekly-template.md` with reusable weekly parity-report sections for tracker deltas, capability changes, validation evidence, risks, and next-week planning.

## 1) Phase 1 - RCON + Event Foundation Parity

### 1.1 RCON command surface

- [x] `P0-RCON-001` Add `ban(player_id, duration, reason)` helper (`@core-runtime`, `P0`)
  - Acceptance: contract test verifies exact command string and response handling.
  - Acceptance note (2026-02-14): Added `RconClient.ban(...)` in `squadpy/rcon/client.py`, unit helper coverage in `tests/test_rcon_helpers.py`, and contract test `tests/contracts/core_runtime/test_rcon_ban_contract.py` validating exact command template + response passthrough.
  - Verification note (2026-02-14): Updated command template to match `ListCommands` details fixture (`AdminBan "<NameOrEOSId>" "<BanLength>" <BanReason>`).
- [x] `P0-RCON-002` Add `switch_team(player_id)` helper (`@core-runtime`, `P0`)
  - Acceptance: helper present and covered by command contract test.
  - Acceptance note (2026-02-14): Added `RconClient.switch_team(...)` in `squadpy/rcon/client.py`, unit helper test in `tests/test_rcon_helpers.py`, and contract test `tests/contracts/core_runtime/test_rcon_switch_team_contract.py` for exact command-template and response passthrough validation.
  - Verification note (2026-02-14): Corrected command to `AdminForceTeamChange <NameOrSteamId>` per `tests/contracts/fixtures/rcon/commands/commands_with_details.txt`.
- [x] `P0-RCON-003` Add force team change helper (`@core-runtime`, `P0`)
  - Acceptance: command is exposed and tested with valid/invalid ids.
  - Acceptance note (2026-02-14): Added `RconClient.force_team_change(...)` in `squadpy/rcon/client.py` using `AdminForceTeamChangeById`, unit tests in `tests/test_rcon_helpers.py` for valid and invalid ids, and contract tests in `tests/contracts/core_runtime/test_rcon_force_team_change_contract.py` for command template + invalid-id response passthrough.
- [x] `P0-RCON-004` Add `set_fog_of_war(mode)` helper (`@core-runtime`, `P0`)
  - Acceptance: mode validation and command dispatch tests pass.
  - Acceptance note (2026-02-14): Added `RconClient.set_fog_of_war(...)` in `squadpy/rcon/client.py` with `0|1` mode validation, unit tests in `tests/test_rcon_helpers.py`, and contract test `tests/contracts/core_runtime/test_rcon_set_fog_of_war_contract.py` for exact command-template + response passthrough.
- [x] `P0-RCON-005` Add `set_next_layer(layer)` helper (`@core-runtime`, `P0`)
  - Acceptance: contract test confirms layer string safety and command dispatch.
  - Acceptance note (2026-02-14): Added `RconClient.set_next_layer(...)` in `squadpy/rcon/client.py` with safe layer-string validation, unit tests in `tests/test_rcon_helpers.py`, and contract tests in `tests/contracts/core_runtime/test_rcon_set_next_layer_contract.py` for exact command template + unsafe-input rejection.
- [x] `P1-RCON-006` Add `demote_commander(player_id)` helper (`@core-runtime`, `P1`)
  - Acceptance: helper implemented with tests.
  - Acceptance note (2026-02-14): Added `RconClient.demote_commander(...)` in `squadpy/rcon/client.py`, unit helper coverage in `tests/test_rcon_helpers.py`, and contract coverage in `tests/contracts/core_runtime/test_rcon_demote_commander_contract.py` validating exact command-template dispatch and response passthrough.
- [x] `P1-RCON-007` Add explicit `set_team(player_id, team)` helper (`@core-runtime`, `P1`)
  - Acceptance: team enum validation and command test coverage.
  - Acceptance note (2026-02-14): Added `RconClient.set_team(...)` in `squadpy/rcon/client.py` with explicit team enum validation (`1`, `2`, `team1`, `team2`) and deterministic target-team behavior, plus unit tests in `tests/test_rcon_helpers.py` and contract tests in `tests/contracts/core_runtime/test_rcon_set_team_contract.py` for command-template dispatch and enum rejection.
- [x] `P1-RCON-008` Add `end_match` helper (`@core-runtime`, `P1`)
  - Acceptance: command helper and safety guard tests.
  - Acceptance note (2026-02-14): Added `RconClient.end_match(...)` in `squadpy/rcon/client.py` with explicit confirmation guard (`confirm=True`) before dispatching `AdminEndMatch`, plus unit tests in `tests/test_rcon_helpers.py` and contract tests in `tests/contracts/core_runtime/test_rcon_end_match_contract.py` for dispatch and guard behavior.
- [x] `P1-RCON-009` Add privileged passthrough wrapper with policy checks (`@core-runtime`, `P1`)
  - Acceptance: unauthorized commands are rejected and audited.
  - Acceptance note (2026-02-14): Added `RconClient.execute_privileged(...)` in `squadpy/rcon/client.py` with explicit policy callback checks, unauthorized-command rejection (`PermissionError`), and in-client privileged audit records via `recent_privileged_audit_records()`, with unit coverage in `tests/test_rcon_helpers.py` and contract coverage in `tests/contracts/core_runtime/test_rcon_privileged_passthrough_contract.py`.

### 1.2 Event types and parser parity

- [x] `P0-EVT-001` Add `PlayerWarned` event (`@parser`, `P0`)
  - Acceptance: event dataclass + parser contract fixture.
  - Acceptance note (2026-02-14): Added `PlayerWarned` dataclass in `squadpy/events/types.py`, log parser rule/handler in `squadpy/log_parser/patterns.py`, and parser contract fixture/test at `tests/contracts/fixtures/parser/player_warned_line.txt` + `tests/contracts/parser/test_player_warned_contract.py`.
- [x] `P0-EVT-002` Add `PlayerKicked` event (`@parser`, `P0`)
  - Acceptance: event dataclass + parser contract fixture.
  - Acceptance note (2026-02-14): Added `PlayerKicked` dataclass in `squadpy/events/types.py`, log parser rule/handler in `squadpy/log_parser/patterns.py`, and parser contract fixture/test at `tests/contracts/fixtures/parser/player_kicked_line.txt` + `tests/contracts/parser/test_player_kicked_contract.py`.
- [x] `P0-EVT-003` Add `PlayerBanned` event (`@parser`, `P0`)
  - Acceptance: event dataclass + parser contract fixture.
  - Acceptance note (2026-02-14): Added `PlayerBanned` dataclass in `squadpy/events/types.py`, parser correlation for real ban logs (`LogOnlineGame` ban/kick reason lines + `LogSquad` admin ban command line) in `squadpy/log_parser/patterns.py`, and contract fixture/test at `tests/contracts/fixtures/parser/player_banned_line.txt` + `tests/contracts/parser/test_player_banned_contract.py`.
- [x] `P0-EVT-004` Add `AdminCamPossess` event (`@parser`, `P0`)
  - Acceptance: parser extracts actor identity and target context.
  - Acceptance note (2026-02-14): Added `AdminCamPossess` dataclass in `squadpy/events/types.py`, parser correlation in `squadpy/log_parser/patterns.py` for `OnPossess` admin-cam lines + `LogSquad: Warning: Admin Camera possessed.` marker, and contract fixture/test at `tests/contracts/fixtures/parser/admin_cam_possess_lines.txt` + `tests/contracts/parser/test_admin_cam_possess_contract.py`.
- [x] `P0-EVT-005` Add `AdminCamUnpossess` event (`@parser`, `P0`)
  - Acceptance: parser contract verifies open/close pairing data.
  - Acceptance note (2026-02-14): Added `AdminCamUnpossess` dataclass in `squadpy/events/types.py`, parser correlation in `squadpy/log_parser/patterns.py` for bare `OnUnPossess` admin-cam exit lines paired against prior admin-cam possess sessions, and contract fixture/test at `tests/contracts/fixtures/parser/admin_cam_unpossess_lines.txt` + `tests/contracts/parser/test_admin_cam_unpossess_contract.py`.
- [x] `P0-EVT-006` Add `SquadCreated` event (`@parser`, `P0`)
  - Acceptance: squad id/name/creator fields parsed reliably.
  - Acceptance note (2026-02-14): Added `SquadCreated` dataclass in `squadpy/events/types.py`, parser rule/handler in `squadpy/log_parser/patterns.py` for `LogSquad ... has created Squad ...` lines, team-id resolution from RCON `ListPlayers` cache with `ListSquads` team-name cache fallback, and contract fixture/test at `tests/contracts/fixtures/parser/squad_created_line.txt` + `tests/contracts/parser/test_squad_created_contract.py`.
- [x] `P0-EVT-007` Add explicit `Teamkill` event (`@parser`, `P0`)
  - Acceptance: teamkill detection path has dedicated contracts.
  - Acceptance note (2026-02-14): Added `Teamkill` dataclass in `squadpy/events/types.py`, parser correlation in `squadpy/log_parser/patterns.py` from native combat logs with RCON `ListPlayers` cache preference and team-assignment log fallback, plus `Die()` fallback detection for teamkills that skip `Wound()` while deduping normal `Wound() -> Die()` chains; contract fixture/test remains `tests/contracts/fixtures/parser/teamkill_lines.txt` + `tests/contracts/parser/test_teamkill_contract.py`.
- [x] `P1-EVT-008` Add `PlayerSwitchedTeam` event (`@parser`, `P1`)
  - Acceptance: parser and event contracts pass.
  - Acceptance note (2026-02-14): Added `PlayerSwitchedTeam` dataclass in `squadpy/events/types.py`, parser transition emission in `squadpy/log_parser/patterns.py` when a cached player team assignment changes, unit coverage in `tests/test_patterns.py` and `tests/test_log_parser.py`, plus parser contract fixture/test at `tests/contracts/fixtures/parser/player_switched_team_lines.txt` and `tests/contracts/parser/test_player_switched_team_contract.py`.
- [x] `P1-EVT-009` Add `NextLayerSet` event (`@parser`, `P1`)
  - Acceptance: layer mutation is emitted as structured event.
  - Acceptance note (2026-02-14): Added `NextLayerSet` dataclass in `squadpy/events/types.py`, parser rule/handler in `squadpy/log_parser/patterns.py` for `ADMIN COMMAND: Set next layer to ...` lines with normalized source metadata (`RCON` vs `IN_GAME`), plus unit/integration coverage in `tests/test_patterns.py` and `tests/test_log_parser.py` and parser contract fixture/test at `tests/contracts/fixtures/parser/next_layer_set_lines.txt` + `tests/contracts/parser/test_next_layer_set_contract.py`.
- [x] `P1-EVT-010` Add seeding threshold transition events (`@parser`, `P1`)
  - Acceptance: threshold up/down events tested in plugin integration.
  - Acceptance note (2026-02-14): Added `SeedingThresholdUp`/`SeedingThresholdDown` dataclasses in `squadpy/events/types.py`, parser transition detection in `squadpy/log_parser/patterns.py` for `Set SeedTargetPlayerCount` command deltas, and parser state support in `squadpy/log_parser/event_store.py`; integrated `plugins/seeding_mode/plugin.py` handlers for both events with runtime threshold updates and coverage in `tests/test_plugin_seeding_mode.py`, plus parser tests/contracts at `tests/test_patterns.py`, `tests/test_log_parser.py`, and `tests/contracts/parser/test_seeding_threshold_transition_contract.py`.
- [x] `P1-EVT-011` Add admin command event normalization (`@parser`, `P1`)
  - Acceptance: command-origin metadata emitted consistently.
  - Acceptance note (2026-02-14): Normalized admin-command origin metadata across parser events in `squadpy/log_parser/patterns.py` with consistent `source` (`RCON`/`IN_GAME`) plus raw `source_detail`; extended `AdminBroadcast`, `PlayerWarned`, `PlayerKicked`, and `PlayerBanned` models in `squadpy/events/types.py`; added normalization coverage in `tests/test_patterns.py`, `tests/test_log_parser.py`, parser contracts in `tests/contracts/parser/test_player_warned_contract.py`, `tests/contracts/parser/test_player_kicked_contract.py`, `tests/contracts/parser/test_player_banned_contract.py`, and cross-event normalization contract `tests/contracts/parser/test_admin_command_normalization_contract.py`.

### 1.3 Runtime reliability contracts

- [x] `P0-RT-001` Add reconnect replay contract tests (`@core-runtime`, `P0`)
  - Acceptance: queued commands flush correctly after reconnect.
  - Acceptance note (2026-02-14): Updated `RconClient.execute()` reconnect gating in `squadpy/rcon/client.py` to wait for in-progress reconnect windows before dispatch, and added runtime regression coverage in `tests/test_rcon_client.py` plus contract test `tests/contracts/core_runtime/test_rcon_reconnect_replay_contract.py` validating queued command flush after reconnect.
- [x] `P0-RT-002` Add out-of-order response stress tests (`@core-runtime`, `P0`)
  - Acceptance: request correlation remains deterministic under concurrency.
  - Acceptance note (2026-02-14): Added high-concurrency out-of-order response tests in `tests/test_rcon_client.py` and contract stress test `tests/contracts/core_runtime/test_rcon_out_of_order_responses_contract.py` using real `ListPlayers`/`ListSquads` fixtures to validate deterministic request-id correlation under reverse-order completion.
- [x] `P1-RT-003` Add typed error taxonomy for RCON failures (`@core-runtime`, `P1`)
  - Acceptance: callers can branch on error classes in tests.
  - Acceptance note (2026-02-14): Added typed RCON runtime exceptions in `squadpy/rcon/client.py` (`RconConnectionError`, `RconDisconnectedError`, `RconAuthenticationError`, `RconCommandError`, `RconCommandTimeoutError`) with backward-compatible `RconAuthError` aliasing, updated runtime raise sites (`connect`, `execute`, auth handling, disconnect propagation) to emit typed subclasses, and added branching coverage in `tests/test_rcon_client.py` plus contract test `tests/contracts/core_runtime/test_rcon_error_taxonomy_contract.py`.

## 2) Phase 2 - Moderation Plugin Parity

### 2.1 New moderation/Discord plugins

- [x] `P0-PLUG-MOD-001` Implement `plugins/chat_commands` (`@plugins-moderation`, `P0`)
  - Acceptance: role-based command permissions and cooldown tests pass.
  - Acceptance note (2026-02-14): Added `plugins/chat_commands/plugin.py` with role-gated `!broadcast`/`!warn`/`!kick` commands, per-user per-command cooldown enforcement, configurable role hierarchy/mappings, and usage/denied/cooldown responses; added example config at `config/plugins/chat_commands.toml.example` and coverage in `tests/test_plugin_chat_commands.py`.
- [x] `P0-PLUG-MOD-002` Implement `plugins/discord_admin_broadcast` (`@plugins-moderation`, `P0`)
  - Acceptance: Discord-triggered broadcast reaches server and logs action.
  - Acceptance note (2026-02-14): Added `plugins/discord_admin_broadcast/plugin.py` with privileged `/broadcast` slash command, optional role gating, and optional audit-channel logging; added example config at `config/plugins/discord_admin_broadcast.toml.example` and coverage in `tests/test_plugin_discord_admin_broadcast.py`.
- [x] `P0-PLUG-MOD-003` Implement `plugins/discord_admin_cam_logs` (`@plugins-moderation`, `P0`)
  - Acceptance: admin cam possess/unpossess events post to Discord.
  - Acceptance note (2026-02-14): Added `plugins/discord_admin_cam_logs/plugin.py` handling `admin_cam_possess`/`admin_cam_unpossess` events with configurable context inclusion; added example config at `config/plugins/discord_admin_cam_logs.toml.example` and coverage in `tests/test_plugin_discord_admin_cam_logs.py`.
- [x] `P0-PLUG-MOD-004` Implement `plugins/discord_killfeed` (`@plugins-moderation`, `P0`)
  - Acceptance: kill events produce correct formatted feed entries.
  - Acceptance note (2026-02-14): Added `plugins/discord_killfeed/plugin.py` for `player_died` event relays with configurable weapon metadata, example config at `config/plugins/discord_killfeed.toml.example`, and tests in `tests/test_plugin_discord_killfeed.py`.
- [x] `P0-PLUG-MOD-005` Implement `plugins/discord_teamkill` (`@plugins-moderation`, `P0`)
  - Acceptance: teamkill-only feed messages with attacker/victim details.
  - Acceptance note (2026-02-14): Added `plugins/discord_teamkill/plugin.py` to post structured teamkill events with configurable weapon metadata, example config at `config/plugins/discord_teamkill.toml.example`, and tests in `tests/test_plugin_discord_teamkill.py`.
- [x] `P0-PLUG-MOD-006` Implement `plugins/discord_round_events` (`@plugins-moderation`, `P0`)
  - Acceptance: round start/end/winner payloads are posted reliably.
  - Acceptance note (2026-02-14): Added `plugins/discord_round_events/plugin.py` for `new_game` and `round_ended` lifecycle notifications with configurable winner/loser payload verbosity, example config at `config/plugins/discord_round_events.toml.example`, and tests in `tests/test_plugin_discord_round_events.py`.
- [x] `P1-PLUG-MOD-007` Implement `plugins/discord_squad_created` (`@plugins-moderation`, `P1`)
  - Acceptance: squad creation alerts include team and creator metadata.
  - Acceptance note (2026-02-14): Added `plugins/discord_squad_created/plugin.py` to publish `squad_created` events to Discord with team metadata (`team_id`, `team_name`) and creator metadata (`creator.name`, optional Steam/EOS IDs), added config template `config/plugins/discord_squad_created.toml.example`, and added coverage in `tests/test_plugin_discord_squad_created.py` for dispatch, disabled channel behavior, creator-id toggling, and handler registration.
- [x] `P1-PLUG-MOD-008` Implement `plugins/discord_fob_hab_damage` (`@plugins-moderation`, `P1`)
  - Acceptance: deployable damage events are summarized with thresholds.
  - Acceptance note (2026-02-14): Added `plugins/discord_fob_hab_damage/plugin.py` to aggregate `deployable_damaged` events by FOB/HAB deployable classification and emit Discord summaries only when cumulative damage crosses configured thresholds, with optional damage metadata and new-round reset support; added config template `config/plugins/discord_fob_hab_damage.toml.example` and coverage in `tests/test_plugin_discord_fob_hab_damage.py` for threshold crossings, multi-threshold progression, reset behavior, non-FOB/HAB filtering, and handler registration.
- [x] `P1-PLUG-MOD-009` Implement `plugins/discord_rcon_console` (`@plugins-moderation`, `P1`)
  - Acceptance: privileged console command execution is audited and gated.
  - Acceptance note (2026-02-14): Added `plugins/discord_rcon_console/plugin.py` with gated `/rcon` slash-command execution using role checks and configurable command allow-list policy wired through `RconClient.execute_privileged(...)`, plus optional Discord audit-channel posting for success/rejection/error outcomes and bounded response previews; added config template `config/plugins/discord_rcon_console.toml.example` and coverage in `tests/test_plugin_discord_rcon_console.py` for role gating, policy rejection, success dispatch, error handling, optional audit behavior, and slash-command registration.

### 2.2 Upgrade existing plugins to parity depth

- [x] `P0-PLUG-UPG-001` Upgrade `tk_warn` config flexibility and edge cases (`@plugins-moderation`, `P0`)
  - Acceptance: parity behavior matrix tests pass.
  - Acceptance note (2026-02-14): Upgraded `plugins/tk_warn/plugin.py` with configurable `event_source` (`teamkill`/`player_wounded`/`auto`), warning cooldown support, reset toggle, safe threshold parsing, safe message formatting, and single-kick guard per offender; updated example config at `config/plugins/tk_warn.toml.example` and expanded parity behavior matrix coverage in `tests/test_plugin_tk_warn.py`.
- [x] `P0-PLUG-UPG-002` Upgrade `admin_request` ticket lifecycle depth (`@plugins-moderation`, `P0`)
  - Acceptance: claim, relay, close, and timeout behaviors are tested.
  - Acceptance note (2026-02-14): Expanded `plugins/admin_request/plugin.py` with ticket close button handling, thread `!close` command flow, periodic timeout expiry (`ticket_timeout_minutes`), and configurable relay/timeout messaging; updated config template at `config/plugins/admin_request.toml.example` and added lifecycle tests in `tests/test_plugin_admin_request.py` for claim, relay, close, and timeout behavior.
- [x] `P1-PLUG-UPG-003` Upgrade `server_status` to richer parity fields (`@plugins-moderation`, `P1`)
  - Acceptance: map/layer/factions/tick/player/squad values validated.
  - Acceptance note (2026-02-14): Upgraded `plugins/server_status/plugin.py` to validate and render richer parity fields in the status embed (`Map`, `Layer`, `Factions`, `Players`, `Squads`, `Tick Rate`, `Next Map`) and added a rolling Players trend graph image with URL-safe chart encoding, point sampling (`graph_max_points`), and restart-safe embed reuse to avoid channel flooding; updated example config at `config/plugins/server_status.toml.example` and expanded validation coverage in `tests/test_plugin_server_status.py` for field values, graph rendering, graph disable toggle, trend window pruning, and startup message reuse behavior.

## 3) Phase 3 - Seeding, Team Balance, Match Control

- [x] `P0-SEED-001` Implement `plugins/seeding_mode` (`@plugins-seeding`, `P0`)
  - Acceptance: seed/live mode transition contracts pass.
  - Acceptance note (2026-02-14): Added `plugins/seeding_mode/plugin.py` with threshold-based seed/live transitions, optional transition broadcasts, optional fog-of-war transition hooks, and `new_game` reset behavior; added example config at `config/plugins/seeding_mode.toml.example` and transition coverage in `tests/test_plugin_seeding_mode.py`.
- [x] `P0-SEED-002` Implement `plugins/auto_seed_low_players` (`@plugins-seeding`, `P0`)
  - Acceptance: low-population automation actions validated by tests.
  - Acceptance note (2026-02-14): Added `plugins/auto_seed_low_players/plugin.py` with low-population entry/exit transitions, reminder cadence, optional unassigned warnings, and optional fog-of-war transition hooks; added example config at `config/plugins/auto_seed_low_players.toml.example` and tests in `tests/test_plugin_auto_seed_low_players.py`.
- [x] `P0-SEED-003` Implement `plugins/auto_rejoin_team` (`@plugins-seeding`, `P0`)
  - Acceptance: team assignment persistence behavior tested.
  - Acceptance note (2026-02-14): Added `plugins/auto_rejoin_team/plugin.py` with reconnect tracking, prior-team memory, bounded retry enforcement, and population guardrails for seeding windows; added example config at `config/plugins/auto_rejoin_team.toml.example` and tests in `tests/test_plugin_auto_rejoin_team.py`.
- [x] `P0-SEED-004` Implement `plugins/team_randomizer` (`@plugins-seeding`, `P0`)
  - Acceptance: randomization rules and fairness constraints tested.
  - Acceptance note (2026-02-14): Added `plugins/team_randomizer/plugin.py` with imbalance detection, bounded random moves, cooldown gating, leader/exemption filtering, and transition announcements; added example config at `config/plugins/team_randomizer.toml.example` and tests in `tests/test_plugin_team_randomizer.py`.
- [x] `P0-SEED-005` Implement `plugins/switch_command` (`@plugins-seeding`, `P0`)
  - Acceptance: user-triggered switch flow with cooldown checks tested.
  - Acceptance note (2026-02-14): Added `plugins/switch_command/plugin.py` with chat-triggered switch requests, configurable channel filtering, and per-player cooldown enforcement plus success/cooldown messaging; added example config at `config/plugins/switch_command.toml.example` and coverage in `tests/test_plugin_switch_command.py`.
- [x] `P0-SEED-006` Implement `plugins/end_match_vote` (`@plugins-seeding`, `P0`)
  - Acceptance: vote quorum and action thresholds tested.
  - Acceptance note (2026-02-14): Added `plugins/end_match_vote/plugin.py` with chat-triggered vote sessions, configurable quorum thresholds, vote-window expiry, and success cooldown enforcement that issues `AdminEndMatch` on pass; added example config at `config/plugins/end_match_vote.toml.example` and coverage in `tests/test_plugin_end_match_vote.py`.
- [x] `P1-SEED-007` Implement `plugins/max_player_in_squad` (`@plugins-seeding`, `P1`)
  - Acceptance: enforcement, exemptions, and warning paths tested.
  - Acceptance note (2026-02-14): Added `plugins/max_player_in_squad/plugin.py` with periodic squad-size enforcement, configurable warning-to-kick escalation, and exemption controls for leader role, player IDs, and squad IDs; added config template `config/plugins/max_player_in_squad.toml.example` and coverage in `tests/test_plugin_max_player_in_squad.py` for direct enforcement, warning escalation, exemption behavior, recovery reset, new-game reset, and handler/task registration.
- [x] `P1-SEED-008` Implement `plugins/squad_name_validator` (`@plugins-seeding`, `P1`)
  - Acceptance: invalid names trigger warnings/actions per config.
  - Acceptance note (2026-02-14): Added `plugins/squad_name_validator/plugin.py` with configurable squad-name policy checks (length bounds, blocked exact names/terms, invalid regex patterns, optional required pattern) and configurable enforcement actions (`warn`, `warn_then_kick`, `kick`) plus exemptions for player and squad IDs; added config template `config/plugins/squad_name_validator.toml.example` and coverage in `tests/test_plugin_squad_name_validator.py` for warning escalation, alternate action modes, exemptions, immediate validation on squad creation, valid-name recovery, and new-game reset behavior.
- [x] `P1-SEED-009` Implement `plugins/intervalled_broadcasts` (`@plugins-seeding`, `P1`)
  - Acceptance: schedule and dedupe behavior covered by tests.
  - Acceptance note (2026-02-14): Added `plugins/intervalled_broadcasts/plugin.py` with interval-based broadcast scheduling, sequential/random message rotation, optional consecutive-message dedupe, optional population gating, and optional new-game reset behavior; added config template `config/plugins/intervalled_broadcasts.toml.example` and coverage in `tests/test_plugin_intervalled_broadcasts.py` for schedule timing, dedupe on/off behavior, min-player gating, reset handling, and handler/task registration.
- [x] `P1-SEED-010` Implement `plugins/fog_of_war` (`@plugins-seeding`, `P1`)
  - Acceptance: fog mode changes are safe, audited, and reversible.
  - Acceptance note (2026-02-14): Added `plugins/fog_of_war/plugin.py` with threshold+hysteresis fog-mode automation, change-cooldown safety guard, dynamic threshold updates from seeding transition events, in-plugin audit records for all mode-change outcomes, and explicit disable-time reversion support; added config template `config/plugins/fog_of_war.toml.example` and coverage in `tests/test_plugin_fog_of_war.py` for safe invalid-config handling, cooldown behavior, audit emission, and reversible disable flow.

### 3.1 Layer catalog subsystem (phase 1/2/3 delivery)

Reference: `docs/plans/layer-catalog-source-reference.md` (upstream `layers.json` structure + reuse notes).

- [x] `P1-LAYER-001` Build `squadpy/layers` core catalog service and normalizer (`@core-runtime`, `P1`)
  - Acceptance: service loads and normalizes SquadLayerList `layers.json` payloads into a typed catalog/query interface with unit coverage for parsing and lookup behavior.
  - Acceptance note (2026-02-14): Added shared layer catalog package (`squadpy/layers/__init__.py`, `squadpy/layers/catalog.py`) with remote fetch support, payload normalization into typed catalog queries (`layers`, `factions`, `vehicles_by_class`), and helper lookups (`has_layer`, `has_faction`, `vehicle_names`, `helicopter_names`, `helicopter_tokens`); added targeted coverage in `tests/test_layers_catalog.py`.
- [x] `P1-LAYER-002` Integrate catalog metadata into `plugins/heli_crash_broadcast` (`@plugins-seeding`, `P1`)
  - Acceptance: heli crash detection consumes shared catalog helicopter metadata first, then deterministic fallback tokens; targeted plugin tests validate both paths.
  - Acceptance note (2026-02-14): Integrated `plugins/heli_crash_broadcast/plugin.py` with `LayerCatalogService` for shared helicopter metadata loading, retained deterministic token/static-name fallback behavior, and added targeted integration coverage in `tests/test_plugin_heli_crash_broadcast.py` for catalog-backed detection.
- [x] `P2-LAYER-003` Add scheduled sync, conditional fetch, and stale-data health signaling (`@data-platform`, `P2`)
  - Acceptance: scheduler supports timeout/backoff + ETag/Last-Modified behavior and exposes stale/fetch-failure state in tests.
  - Acceptance note (2026-02-15): Extended `squadpy/layers/catalog.py` with `LayerCatalogService.sync_once()` conditional HTTP fetch support (`If-None-Match`/`If-Modified-Since` + `304` handling), scheduled sync loop support with retry backoff/jitter (`run_scheduled_sync`, `next_sync_delay_seconds`), and explicit stale/fetch-failure health signaling (`LayerCatalogHealth`); added targeted coverage in `tests/test_layers_catalog.py` for conditional header behavior, stale/failure health transitions, and scheduler backoff behavior.
- [x] `P2-LAYER-004` Add persisted last-known-good catalog snapshot (`@data-platform`, `P2`)
  - Acceptance: startup restores snapshot when remote source is unavailable; persistence and recovery tests pass.
  - Acceptance note (2026-02-15): Added persisted snapshot support to `LayerCatalogService` in `squadpy/layers/catalog.py` via configurable `snapshot_path`, automatic snapshot writes after successful fetch/sync, and startup recovery through `initialize()` + `load_snapshot()` when the remote source is unavailable; added targeted persistence/recovery coverage in `tests/test_layers_catalog.py`.
- [ ] `P2-LAYER-005` Expose shared layer query surfaces (plugin APIs + authenticated control APIs) (`@api-security`, `P2`)
  - Acceptance: plugin consumers and authenticated API callers can query layer/faction/vehicle metadata with integration tests for allowed/denied access.

- [x] `P1-SEED-011` Implement `plugins/heli_crash_broadcast` (`@plugins-seeding`, `P1`)
  - Acceptance: relevant event detection and broadcast tests pass using shared layer catalog metadata from `P1-LAYER-001`/`P1-LAYER-002`, with fallback-only mode covered by tests.
  - Acceptance note (2026-02-14): Added `plugins/heli_crash_broadcast/plugin.py` for death-cluster detection with incident-window thresholding, cooldown dedupe, configurable broadcast formatting, and optional new-game reset; added config template `config/plugins/heli_crash_broadcast.toml.example` and targeted coverage in `tests/test_plugin_heli_crash_broadcast.py` for threshold behavior, cooldown, reset, fallback classification, and catalog-backed helicopter detection.
- [x] `P1-SEED-012` Implement `plugins/knife_broadcast` (`@plugins-seeding`, `P1`)
  - Acceptance: knife kill detection and formatting tests pass.
  - Acceptance note (2026-02-14): Added `plugins/knife_broadcast/plugin.py` with knife/melee kill detection from configurable tokens plus shared layer-catalog `MeleeWeapons` metadata (`LayerCatalogService`) and optional static melee-name fallback; added config template `config/plugins/knife_broadcast.toml.example` and targeted coverage in `tests/test_plugin_knife_broadcast.py` for token detection, cooldown behavior, new-game reset, formatting toggles, and catalog-backed melee detection.

## 4) Phase 4 - Data, API, Integration Parity

### 4.1 Data and DBLog parity

- [x] `P0-DATA-001` Implement `plugins/db_log` core schema (`@data-platform`, `P0`)
  - Acceptance: migration creates expected tables/indexes.
  - Acceptance note (2026-02-14): Added `plugins/db_log/plugin.py` with DBLog core schema models for matches/players/sessions/events/admin actions/chat messages and explicit index definitions, plus plugin bootstrap that ensures schema creation on enable; added example config at `config/plugins/db_log.toml.example` and schema/bootstrap coverage in `tests/test_plugin_db_log.py`.
- [x] `P0-DATA-002` Add versioned migrations for db log (`@data-platform`, `P0`)
  - Acceptance: forward migration and clean bootstrap tests pass.
  - Acceptance note (2026-02-14): Added versioned sqlite migration runner at `plugins/db_log/migrations.py` with schema version tracking (`db_log_schema_migrations`), ordered migrations, and target-version support; integrated migration application into `plugins/db_log/plugin.py` and added forward/bootstrap coverage in `tests/test_plugin_db_log_migrations.py`.
- [x] `P1-DATA-003` Add retention and pruning jobs (`@data-platform`, `P1`)
  - Acceptance: pruning policy tests validate retention windows.
  - Acceptance note (2026-02-14): Added db_log retention/pruning scheduling in `plugins/db_log/plugin.py` with per-table retention windows (`matches`, `sessions`, `events`, `admin_actions`, `chat_messages`), configurable prune interval/toggle, and periodic prune execution; updated `config/plugins/db_log.toml.example` with retention/prune settings and added targeted policy coverage in `tests/test_plugin_db_log.py` validating retention-window cutoffs, disabled-window behavior, and prune disable toggle.
- [x] `P1-DATA-004` Add materialized views/query helpers for analytics (`@data-platform`, `P1`)
  - Acceptance: dashboard query smoke tests pass.
  - Acceptance note (2026-02-14): Added sqlite analytics-view migration `v3` in `plugins/db_log/migrations.py` (`db_log_mv_population_daily`, `db_log_mv_event_volume_daily`, `db_log_mv_moderation_daily`, `db_log_mv_chat_volume_daily`), implemented dashboard query helpers in `plugins/db_log/analytics.py`, and exposed plugin-level snapshot access via `DbLog.dashboard_snapshot()` in `plugins/db_log/plugin.py`; added smoke coverage in `tests/test_plugin_db_log_analytics.py` plus migration/view assertions in `tests/test_plugin_db_log_migrations.py`.

### 4.2 API and remote control

- [x] `P0-API-001` Add authenticated websocket control service (`@api-security`, `P0`)
  - Acceptance: command dispatch + auth rejection contracts pass.
  - Acceptance note (2026-02-14): Added websocket control service at `squadpy/api/websocket_control.py` with token auth, default-deny action routing, and `rcon.execute` dispatch support; wired optional API config/startup into `squadpy/config.py` + `squadpy/server.py` and added contract coverage in `tests/contracts/api_security/test_websocket_control_contract.py` for authorized dispatch and unauthorized rejection.
- [x] `P0-API-002` Add authenticated REST control endpoints (`@api-security`, `P0`)
  - Acceptance: health, status, and command endpoints tested.
  - Acceptance note (2026-02-14): Extended `squadpy/api/websocket_control.py` with token-gated REST handlers (`/api/health`, `/api/status`, `/api/command`) and shared auth/dispatch logic; added endpoint behavior coverage in `tests/test_api_rest_control.py` and contract checks in `tests/contracts/api_security/test_rest_control_contract.py`.
- [x] `P0-API-003` Add audit logging for all privileged actions (`@api-security`, `P0`)
  - Acceptance: audit records include actor, origin, target, outcome.
  - Acceptance note (2026-02-14): Added control API audit records in `squadpy/api/websocket_control.py` for privileged command attempts (authorized and rejected) with actor/origin/target/outcome fields, exposed via `recent_audit_records()`, and added coverage in `tests/test_api_audit.py` plus contract checks in `tests/contracts/api_security/test_api_audit_contract.py`.
- [x] `P1-API-004` Add role-based access control model (`@api-security`, `P1`)
  - Acceptance: RBAC integration tests pass for allowed/denied actions.
  - Acceptance note (2026-02-14): Extended `squadpy/api/websocket_control.py` with configurable RBAC policy (`rbac_enabled`, default role, per-role permissions, wildcard support) across websocket and REST control flows, including forbidden responses and privileged-action audit entries for role-denied attempts; wired RBAC config through `squadpy/config.py`, `config/server.toml.example`, and `squadpy/server.py`, and added targeted coverage in `tests/test_api_websocket_control.py`, `tests/test_api_rest_control.py`, `tests/test_api_audit.py`, `tests/test_server_api.py`, plus contract coverage in `tests/contracts/api_security/test_rbac_contract.py`.
- [x] `P1-API-005` Add signed webhook policy support (`@api-security`, `P1`)
  - Acceptance: valid signatures accepted, invalid rejected.
  - Acceptance note (2026-02-14): Added signed webhook command policy in `squadpy/api/websocket_control.py` with HMAC-SHA256 verification over `{timestamp}.{raw_body}`, configurable signature/timestamp headers and max-age window, and dedicated `/api/webhook/command` handling that rejects invalid/stale signatures before dispatch; wired webhook signing config through `squadpy/config.py`, `config/server.toml.example`, and `squadpy/server.py`, and added targeted coverage in `tests/test_api_webhook_signature.py`, `tests/test_api_audit.py`, `tests/test_config.py`, `tests/test_server_api.py` plus contract coverage in `tests/contracts/api_security/test_webhook_signature_contract.py`.

### 4.3 Connector parity

- [x] `P0-CONN-001` Add connector abstraction under `squadpy/connectors/` (`@api-security`, `P0`)
  - Acceptance: connector interface and lifecycle tests pass.
  - Acceptance note (2026-02-14): Added connector abstraction package in `squadpy/connectors/` with base `Connector` lifecycle/state interface and `ConnectorManager` orchestration, wired `DiscordConnector` to the shared connector interface lifecycle, and added targeted coverage in `tests/test_connectors.py` plus contract coverage in `tests/contracts/api_security/test_connector_lifecycle_contract.py`.
- [x] `P1-CONN-002` Add external moderation API connector #1 (`@api-security`, `P1`)
  - Acceptance: integration tests use mocked API and pass.
  - Acceptance note (2026-02-14): Added `BattleMetricsConnector` in `squadpy/connectors/battlemetrics.py` with token-authenticated HTTP lifecycle, started/stopped session management, and normalized player lookup via `lookup_player`; exported connector types via `squadpy/connectors/__init__.py`; added mocked API integration coverage in `tests/test_battlemetrics_connector.py` and contract coverage in `tests/contracts/api_security/test_battlemetrics_connector_contract.py`.
- [x] `P1-CONN-003` Add external moderation API connector #2 (`@api-security`, `P1`)
  - Acceptance: integration tests use mocked API and pass.
  - Acceptance note (2026-02-14): Added `CommunityBanListConnector` in `squadpy/connectors/community_ban_list.py` with token-authenticated HTTP lifecycle, started/stopped session management, and normalized player + active-ban lookup via `lookup_player`; exported connector types via `squadpy/connectors/__init__.py`; added mocked API integration coverage in `tests/test_community_ban_list_connector.py` and contract coverage in `tests/contracts/api_security/test_community_ban_list_connector_contract.py`.
- [x] `P1-CONN-004` Add admin list sync engine (local + remote + sftp) (`@api-security`, `P1`)
  - Acceptance: merge precedence and conflict behavior covered by tests.
  - Acceptance note (2026-02-14): Added admin list sync subsystem under `squadpy/admin_lists/` with source adapters (`LocalAdminListSource`, `RemoteAdminListSource`, `SftpAdminListSource`) and `AdminListSyncEngine` precedence-based merge/conflict handling in `squadpy/admin_lists/sync.py`; added targeted coverage in `tests/test_admin_list_sync.py` for local/remote/sftp ingestion and merge precedence/conflicts, plus contract coverage in `tests/contracts/api_security/test_admin_list_sync_contract.py`.

## 5) Phase 5 - Migration and Compatibility

- [ ] `P0-MIG-001` Build report-first `scripts/migrate_from_squadjs.py` analyzer (`@migration`, `P0`)
  - Acceptance: sample SquadJS config generates migration inventory/report output in default dry-run mode (no writes).
- [ ] `P0-MIG-002` Build report-first `scripts/migrate_from_squadts.py` analyzer (`@migration`, `P0`)
  - Acceptance: sample SquadTS config generates migration inventory/report output in default dry-run mode (no writes).
- [ ] `P0-MIG-003` Build migrated TOML linter/report tool (`@migration`, `P0`)
  - Acceptance: linter emits actionable fixups, severity levels, and explicit safe/review/unsupported mapping categories.
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
| TK warn | Yes | Done | `P0-PLUG-UPG-001` |
| Admin request workflow | Yes | Done | `P0-PLUG-UPG-002` |
| Discord chat bridge | Yes | Done | Existing |
| Server status embed | Yes | Done | `P1-PLUG-UPG-003` |
| Chat commands | Yes | Done | `P0-PLUG-MOD-001` |
| Discord admin broadcast | Yes | Done | `P0-PLUG-MOD-002` |
| Discord admin cam logs | Yes | Done | `P0-PLUG-MOD-003` |
| Discord killfeed | Yes | Done | `P0-PLUG-MOD-004` |
| Discord teamkill feed | Yes | Done | `P0-PLUG-MOD-005` |
| Discord round events | Yes | Done | `P0-PLUG-MOD-006` |
| Discord squad created | Yes | Done | `P1-PLUG-MOD-007` |
| Discord FOB/HAB damage | Yes | Done | `P1-PLUG-MOD-008` |
| Discord RCON console | Yes | Done | `P1-PLUG-MOD-009` |
| Seeding mode | Yes | Done | `P0-SEED-001` |
| Auto seed low players | Yes | Done | `P0-SEED-002` |
| Auto rejoin team | Yes | Done | `P0-SEED-003` |
| Team randomizer | Yes | Done | `P0-SEED-004` |
| Switch command | Yes | Done | `P0-SEED-005` |
| End match vote | Yes | Done | `P0-SEED-006` |
| Max players in squad | Yes | Done | `P1-SEED-007` |
| Squad name validator | Yes | Done | `P1-SEED-008` |
| Intervalled broadcasts | Yes | Done | `P1-SEED-009` |
| Fog of war automation | Yes | Done | `P1-SEED-010` |
| Heli crash broadcast | Yes | Done | `P1-LAYER-001`, `P1-LAYER-002`, `P1-SEED-011` |
| Knife broadcast | Yes | Done | `P1-SEED-012` |
| DB event logging plugin | Yes | Done | `P0-DATA-001` |
| Websocket API plugin/service | Yes | Done | `P0-API-001` |

## 8) Release Gates

### Parity claim gates (all required)

- [ ] `GATE-001` All `P0-*` items completed.
- [ ] `GATE-002` Contract suite green in CI for 14 consecutive days.
- [ ] `GATE-003` Integration suite green in CI for 14 consecutive days.
- [ ] `GATE-004` Soak test pass for 30 days, no Sev-1 incidents.
- [ ] `GATE-005` Migration analyzers/scripts validated on at least 3 real community configs.
- [ ] `GATE-006` Operator sign-off from pilot servers.

### Beyond release gates

- [ ] `GATE-B-001` At least 3 `P2-BEYOND-*` features released and documented.
- [ ] `GATE-B-002` Observability baseline dashboard pack published.
- [ ] `GATE-B-003` Multi-server or broker mode validated in pilot environment.

## 9) Weekly Update Block (Copy/Paste)

Week of: 2026-02-14

- Completed IDs: `P0-PLUG-UPG-001`, `P0-PLUG-MOD-001`, `P0-SEED-001`, `P0-SEED-002`, `P0-SEED-003`, `P0-SEED-004`, `P0-SEED-005`, `P0-SEED-006`, `P0-DATA-001`, `P0-DATA-002`, `P0-API-001`, `P0-API-002`, `P0-API-003`
- In-progress IDs: none
- Blocked IDs: none
- New risks: remote layer source availability and schema drift can still impact metadata freshness until Phase 2 sync/caching hardening (`P2-LAYER-003`, `P2-LAYER-004`) lands.
- Mitigations applied: centralized layer metadata usage and normalization in shared `squadpy/layers` service for both heli and melee detection paths.
- Next week top 5 IDs: `P1-DATA-003`, `P1-DATA-004`, `P1-API-004`, `P1-API-005`, `P0-CONN-001`
