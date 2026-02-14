# SquadPy Parity and Beyond Roadmap (SquadJS + SquadTS)

Date: 2026-02-13
Owner: SquadPy core maintainers
Status: Draft for execution

## 0) Current Progress Snapshot (From Parity Tracker)

As of 2026-02-14, from `docs/plans/parity-tracker.md`:

- Total tracked checklist items: `90`
- Done: `21`
- In progress: `0`
- Blocked: `0`
- Not started: `69`
- `P0` completion: `21/45` (47%)
- `P1` completion: `0/28`
- `P2` completion: `0/8`
- Release gates completion: `0/9` (`GATE-*` and `GATE-B-*`)

Area breakdown (done/total):

- Program setup (`P0-PROG`): `7/8`
- RCON surface (`P0-RCON`): `5/5`
- Event parity (`P0-EVT`): `7/7`
- Runtime reliability (`P0-RT`): `2/2`
- Moderation plugins (`P0-PLUG` + `P1-PLUG`): `0/12`
- Seeding plugins (`P0-SEED` + `P1-SEED`): `0/12`
- Data/API/Connectors (`P0/P1-DATA`, `P0/P1-API`, `P0/P1-CONN`): `0/14`
- Migration tooling (`P0/P1-MIG`): `0/5`
- Beyond features (`P2-BEYOND`): `0/8`

## 1) Goal and Success Criteria

Build SquadPy to:

1. Reach full practical parity with the combined feature set used in production from SquadJS and SquadTS.
2. Preserve SquadPy strengths (typed Python APIs, async architecture, testability).
3. Surpass both with reliability, operability, multi-server support, and developer experience.

Success criteria:

- Parity: every high-value plugin category from SquadJS + SquadTS has a native SquadPy equivalent.
- Compatibility: top existing server workflows can migrate without losing moderation capability.
- Quality: >= 90% test coverage on core protocol/parser code paths and contract tests for all built-in plugins.
- Reliability: 30-day soak test with no critical crash, no event-loop deadlocks, and controlled auto-recovery from RCON/log interruptions.

## 2) Scope Definition (What "Full Parity" Means)

Parity is defined as the union of:

- SquadJS default plugin and connector capabilities (from its `config.json` and README).
- SquadTS built-in plugin capabilities and its documented operational features.

Full parity does not require 1:1 line-by-line clone behavior, but does require equivalent outcomes for admins, moderation staff, and players.

## 3) Baseline Snapshot (Current SquadPy)

Current strengths:

- Async RCON client with packet reassembly and reconnect support.
- Log parser with core event extraction and typed event dataclasses.
- Plugin system with decorators, periodic tasks, Discord slash/interaction handlers.
- Discord connector, async SQLAlchemy database service.
- Hot reload via `/reload`.
- 6 built-in plugins: auto-kick-unassigned, tk-warn, server-status, admin-request, discord-chat-bridge, plugin-manager.

Main gaps:

- Limited RCON command surface vs SquadJS/SquadTS operational usage.
- Missing many moderation/admin/log lifecycle events.
- Missing most production plugins used in JS/TS ecosystems.
- No external APIs/connectors for typical ops stacks (websocket API, third-party moderation systems).
- DB service exists, but no equivalent to mature structured event logging plugin flow.

## 4) Comprehensive Gap Matrix

## 4.1 Core RCON Surface

Current SquadPy methods:

- `list_players`, `list_squads`, `broadcast`, `warn`, `kick`, `show_current_map`, `show_next_map`

Required parity additions:

- `ban(player_id, duration, reason)`
- `switch_team(player_id)` / force team change helper
- `set_fog_of_war(mode)`
- `set_next_layer(layer)` and helpers for map voting/rotation plugins
- optional helpers used by admin tooling: `demote_commander`, `set_team`, `end_match`, command passthrough with permission guards

## 4.2 Event Model and Parsing

Current SquadPy has core combat/session/chat events but lacks many production events used by JS/TS plugins.

Required parity event families:

- Administrative lifecycle:
  - player warned / kicked / banned
  - admin camera possessed / unpossessed
  - squad created
- Team and balance flow:
  - teamkill explicit event
  - team switched / forced switch
  - seeding/live threshold transitions
- Layer/match control:
  - next layer set / changed
  - voting-related transitions
- Moderation utility:
  - structured command events from admin chat/discord bridge

## 4.3 Plugin Parity Backlog (Union of SquadJS + SquadTS)

Already covered in SquadPy:

- Auto kick unassigned
- Auto tk warn
- Discord admin request
- Discord chat bridge (equivalent)
- Discord server status (partial to full)

Missing or partial priorities:

- Discord admin broadcast
- Discord admin cam logs
- Discord FOB/HAB explosion damage
- Discord killfeed
- Discord round ended / round winner
- Discord squad created
- Discord teamkill feed
- Discord RCON console
- Chat command framework
- Seeding mode / auto seed low players
- Team randomizer / switch command / auto rejoin team
- End match vote
- Max player in squad
- Squad name validator
- Heli crash broadcast
- Knife broadcast
- Intervalled broadcasts
- Fog of war automation plugin
- SocketIO / websocket API plugin
- Persistent DB event logging (DBLog equivalent)
- Placeholder/debug/subsystem-restarter equivalents where useful

## 4.4 Connectors and Integrations

Current SquadPy connectors/services:

- Discord
- Database (sqlite/mysql/postgres)

Parity connectors to add:

- Websocket/API service for remote controls and dashboards
- External moderation/community APIs (priority integration targets based on server usage)
- Admin list sync sources (local + remote + ftp/sftp merge behavior)

## 4.5 Ops and Platform Gaps

- No first-class migration tooling from SquadJS/SquadTS config formats.
- No compatibility adapter for common JS/TS plugin semantics.
- Limited runtime observability (metrics/tracing/health endpoint).
- No dedicated multi-server orchestration model.

## 4.6 Layer Catalog and Metadata Parity

Current SquadPy gaps:

- No first-class layer metadata catalog service.
- Plugins that need layer/faction/vehicle intelligence currently require ad-hoc token lists or plugin-local parsing/fetching.

Required parity additions:

- First-class layer catalog service that can ingest SquadLayerList `layers.json`.
- Normalized query API for layers, factions, and vehicle classes (including helicopter identifiers).
- Shared usage across plugins (starting with `heli_crash_broadcast`) to avoid duplicate fetch/parser logic.

## 5) Execution Strategy

Use a two-track program:

1. Parity Track: close all high-value functional gaps.
2. Beyond Track: ship features that make SquadPy objectively better for operators.

Both tracks run in parallel once foundation milestones complete.

## 6) Phased Roadmap (24 Weeks)

## Phase 0 (Weeks 1-2): Program Setup and Acceptance Harness

Deliverables:

- Parity tracker document with checkboxes per plugin/event/command.
- Golden fixtures from real logs and RCON outputs.
- Contract test harness for event and command behavior.

Implementation tasks:

- Create `tests/contracts/` for parity acceptance tests.
- Create `docs/plans/parity-tracker.md` to track status.
- Add CI matrix for unit + contract + integration tags.

Exit criteria:

- Every parity item has an owner, priority, and acceptance test stub.

## Phase 1 (Weeks 3-6): RCON + Event Foundation Parity

Deliverables:

- Expanded RCON API surface.
- Expanded event dataclasses and parser rules.
- Event correlation improvements (attacker/victim/admin identity quality).

Implementation tasks:

- Extend `squadpy/rcon/client.py` with missing admin commands.
- Expand `squadpy/events/types.py` for parity event families.
- Expand `squadpy/log_parser/patterns.py` and parser state correlation.
- Add parser regression tests for each new event class.

Exit criteria:

- Contract tests pass for all P0 event and command scenarios.

## Phase 2 (Weeks 7-10): Moderation Plugin Parity

Deliverables:

- Native plugins for moderation-critical workflows.

Implementation tasks:

- Add plugins:
  - `chat_commands`
  - `discord_admin_broadcast`
  - `discord_admin_cam_logs`
  - `discord_killfeed`
  - `discord_teamkill`
  - `discord_round_events`
  - `discord_squad_created`
- Upgrade `tk_warn` and `admin_request` behavior to parity-level configuration depth.

Exit criteria:

- Moderation teams can run full daily operations without JS/TS fallback.

## Phase 3 (Weeks 11-14): Seeding, Team Balance, and Match Control

Deliverables:

- Seeding and balance plugins matching current ecosystem expectations.

Implementation tasks:

- Add plugins:
  - `seeding_mode`
  - `auto_seed_low_players`
  - `auto_rejoin_team`
  - `team_randomizer`
  - `switch_command`
  - `end_match_vote`
  - `max_player_in_squad`
  - `squad_name_validator`
  - `intervalled_broadcasts`
  - `fog_of_war`

Exit criteria:

- Server owners can replace common seeding/team-control setups fully with SquadPy.

### Layer Catalog Subsystem Delivery (Phase 1/2/3)

This subsystem is intentionally cross-cutting. It starts with seeding/plugin needs, then hardens into a platform service.

Layer Phase 1 (implement now):

- Deliverables:
  - Add `squadpy/layers/` core module with normalized catalog model and query helpers.
  - Add remote provider support for SquadLayerList `layers.json` with safe timeout/fallback behavior.
  - Integrate `plugins/heli_crash_broadcast` to use catalog-derived helicopter metadata instead of plugin-local layer intelligence.
- Exit criteria:
  - Heli crash detection works from shared catalog metadata with deterministic fallback behavior and targeted tests.

Layer Phase 2 (hardening):

- Deliverables:
  - Scheduled catalog sync with conditional HTTP fetch (ETag/Last-Modified), retry backoff, and jitter.
  - Stale-data health signaling and operator-visible diagnostics.
  - Persisted last-known-good catalog snapshot for startup resiliency.
- Exit criteria:
  - Service continues operating with known-good metadata during remote source outages and exposes stale-state health signals.

Layer Phase 3 (platform exposure):

- Deliverables:
  - Shared query surfaces for other plugins and authenticated control APIs.
  - Catalog-backed inputs for map rotation/voting and analytics pipelines.
  - Operational documentation for source overrides and refresh policy.
- Exit criteria:
  - Layer metadata becomes a reusable SquadPy platform capability, not a single-plugin implementation detail.

## Phase 4 (Weeks 15-18): Data, APIs, and Integrations

Deliverables:

- DBLog-equivalent structured persistence.
- Websocket/API remote control service.
- Admin list synchronization parity.

Implementation tasks:

- Add `plugins/db_log` with schema/versioned migrations.
- Add `squadpy/api/` for authenticated websocket + REST endpoints.
- Add `squadpy/admin_lists/` for local/remote/ftp/sftp merge support.
- Add connector abstraction layer in `squadpy/connectors/`.

Exit criteria:

- Data export and remote control capabilities match or exceed SquadJS/SquadTS usage patterns.

## Phase 5 (Weeks 19-20): Migration and Compatibility Layer

Deliverables:

- Report-first migration analyzers for SquadJS/SquadTS configs.
- Compatibility documentation and recipe pack.

Implementation tasks:

- Build `scripts/migrate_from_squadjs.py` and `scripts/migrate_from_squadts.py` in dry-run/report-first mode.
- Add mapping inventories with safe/review/unsupported categories plus validation reports.
- Publish migration playbooks in `docs/`.

Exit criteria:

- Pilot community can migrate with no critical blockers using report-guided workflows.

## Phase 6 (Weeks 21-24): Surpass Features

Deliverables:

- Capabilities not natively provided as a cohesive package by either upstream ecosystem.

Implementation tasks:

- Multi-server orchestration:
  - one process managing N servers with isolated plugin contexts.
- RCON broker mode:
  - single TCP owner with authenticated local API clients.
- First-class observability:
  - Prometheus metrics, structured traces, health and readiness endpoints.
- Reliability hardening:
  - plugin watchdogs, failure budgets, circuit-breakers for external services.
- Developer platform:
  - plugin scaffolder CLI, typed plugin contracts, richer local simulation harness.

Exit criteria:

- SquadPy has at least 3 clear operator-facing differentiators over SquadJS/SquadTS.

## 7) Detailed Workstreams

## Workstream A: Core Protocol and Runtime

Targets:

- Deterministic command queueing and replay after reconnect.
- Better request correlation under high load.
- Typed command/result layer with explicit error taxonomy.

Definition of done:

- Stress tests with concurrent commands and reconnect chaos pass consistently.

## Workstream B: Parser Accuracy and Drift Resistance

Targets:

- Regex/version strategy per Squad release.
- Fixture packs tagged by game build.
- Low-noise parser warning channel for unknown lines.

Definition of done:

- Unknown-line rate below agreed threshold in live pilot logs.

## Workstream C: Plugin Platform

Targets:

- Plugin capability declarations (`requires`, permissions, intents).
- Shared helper modules for moderation logic, cooldowns, dedupe, identity mapping.
- Optional plugin state persistence helpers.

Definition of done:

- New plugin development time reduced and consistency improved across built-ins.

## Workstream D: API, Security, and Permissions

Targets:

- RBAC for privileged actions.
- Signed webhook/auth token policy.
- Audit logs for all admin-impacting actions.

Definition of done:

- Security review checklist passes before stable parity release.

## Workstream E: Data and Analytics

Targets:

- Event warehouse schema with retention policy.
- Dashboard-ready views for moderation, seeding, and performance.
- Backfill and replay support from historical logs.

Definition of done:

- Standard dashboard pack can be built without custom SQL per community.

## 8) Testing and Validation Plan

Test layers:

- Unit tests for parser, RCON protocol, plugin internals.
- Contract tests for event/command/plugin parity assertions.
- Integration tests with mocked Discord/RCON/log sources.
- Soak tests with long-running scenarios and failure injection.

Required gates for each milestone:

- All new code paths covered by tests.
- No regression in existing `pytest -v` suite.
- Plugin acceptance tests for each newly added parity plugin.

## 9) Release and Rollout Plan

Release channels:

- `alpha`: feature-complete but unstable parity candidates.
- `beta`: migration pilots with selected communities.
- `stable`: production recommendation after soak period.

Rollout model:

1. Dogfood in one internal/partner server.
2. Expand to 3-5 mixed community sizes.
3. Declare parity-complete release.
4. Release beyond features in incremental minor versions.

## 10) Risks and Mitigations

Risk: Squad log format changes break parser.
Mitigation: build-versioned fixtures, drift alerts, fast patch workflow.

Risk: External API instability (Discord/third-party).
Mitigation: retries with jitter, circuit-breaker, queue durability.

Risk: Migration friction from JSON/JSON5 configs.
Mitigation: automated migrators + compatibility checks + lint/fix output.

Risk: Single RCON per IP constraints in mixed ecosystems.
Mitigation: ship RCON broker mode early and document cutover architecture.

Risk: Scope overrun from plugin count.
Mitigation: strict P0/P1/P2 prioritization and milestone freeze discipline.

## 11) Prioritization (P0 / P1 / P2)

P0 (must-have for parity claim):

- RCON command parity core (`ban`, switch, fog, next-layer/set).
- Critical moderation events.
- Core moderation + Discord logging plugins.
- Seeding/team-balance essentials.
- DBLog-equivalent + websocket API.

P1 (high-value parity and migration quality):

- Admin list sync parity.
- Full config migration tooling.
- Additional utility plugins (intervalled broadcasts, placeholder/debug).

P2 (beyond and polish):

- Multi-server orchestration.
- Advanced observability pack.
- Extended SDK ergonomics and simulation tooling.

## 12) Suggested Team Allocation

If 2 engineers:

- Engineer A: core runtime/parser/RCON/contracts.
- Engineer B: plugins/Discord/connectors/migration tools.

If 3+ engineers:

- Add dedicated owner for data/API/observability.

## 13) Immediate Next 10 Tasks

1. Create `docs/plans/parity-tracker.md` with full checklist and owners.
2. Define canonical event contract schemas in `tests/contracts/`.
3. Implement missing RCON methods with tests.
4. Add event dataclasses for admin camera/warn/kick/ban/squad-created/teamkill.
5. Extend parser rules for those events.
6. Build `discord_admin_broadcast` and `discord_admin_cam_logs` plugins.
7. Build `discord_killfeed` + `discord_teamkill` plugins.
8. Build `chat_commands` plugin and shared command parsing helpers.
9. Implement `db_log` plugin and initial schema migrations.
10. Stand up minimal authenticated websocket API plugin/service.

## 14) References Used for Scope Baseline

- SquadJS repository and default config plugin list:
  - https://github.com/Team-Silver-Sphere/SquadJS
  - https://raw.githubusercontent.com/Team-Silver-Sphere/SquadJS/master/config.json
- SquadTS repository and README plugin/features list:
  - https://github.com/ambroiseRabier/SquadTS
  - https://raw.githubusercontent.com/ambroiseRabier/SquadTS/main/README.md
- Current SquadPy implementation baseline:
  - `README.md`
  - `squadpy/rcon/client.py`
  - `squadpy/log_parser/patterns.py`
  - `squadpy/events/types.py`
  - `plugins/`
