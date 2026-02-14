# SquadPy Event Contract Schema

Date: 2026-02-14
Owner: `@parser`
Tracker IDs: `P0-PROG-006`, `P0-EVT-*`

## Purpose

This document defines the canonical schema for parser/runtime events used by parity contract tests.
It is the source of truth for:

- event payload shape and field types
- minimum required fields for contract acceptance
- compatibility/versioning expectations for event consumers

Implementation source: `squadpy/events/types.py`

## Versioning

- Contract schema version: `1`
- Compatibility policy: additive-only within the same major version
- Breaking changes: require a schema version increment and updated contract fixtures/tests

## Contract Envelope

All emitted events must include this envelope:

```json
{
  "event_name": "string",
  "timestamp": "datetime"
}
```

Rules:

- `event_name` must match the dataclass default value.
- `timestamp` is runtime generated (`datetime`) and is excluded from strict fixture equality checks.
- Event-specific fields are validated by event-name contract tests.

## Shared Types

### `PlayerID`

```json
{
  "steam_id": "string",
  "eos_id": "string",
  "name": "string",
  "controller": "string"
}
```

Rules:

- Empty strings are allowed for unresolved IDs in parser edge paths.
- Known IDs should be preserved exactly as parsed (no format normalization in contracts).

## Event Catalog (Current)

The following event names and field contracts map to `squadpy/events/types.py`.

| Event Name | Required Fields | Optional/Nullable Notes |
|---|---|---|
| `player_connected` | `player`, `ip`, `chain_id`, `controller_name` | `player` is `PlayerID` |
| `join_succeeded` | `player`, `chain_id`, `player_suffix` | `player_suffix` may be empty |
| `player_disconnected` | `player`, `ip`, `controller_name` | |
| `player_damaged` | `victim_name`, `damage`, `attacker`, `weapon` | |
| `player_wounded` | `victim_name`, `damage`, `attacker`, `weapon` | |
| `player_died` | `victim_name`, `damage`, `attacker`, `weapon` | |
| `player_revived` | `reviver`, `victim` | both are `PlayerID` |
| `player_possess` | `player`, `possess_classname` | |
| `player_unpossess` | `player`, `health`, `exited_vehicle`, `vehicle_name`, `seat_number` | |
| `new_game` | `dlc`, `map_classname`, `layer_classname` | `winner` may be `null` |
| `round_ended` | none beyond envelope | `winner` and `loser` may be `null` |
| `round_tickets` | `team`, `subfaction`, `faction`, `action`, `tickets`, `layer`, `level` | stored in correlation state; not emitted directly |
| `server_tick_rate` | `tick_rate` | |
| `admin_broadcast` | `message`, `from_player` | |
| `player_warned` | `admin`, `player`, `reason`, `source` | `player` is `PlayerID` |
| `player_kicked` | `admin`, `player`, `reason`, `source` | `player` is `PlayerID` |
| `player_banned` | `admin`, `player`, `duration`, `reason`, `source` | `player` is `PlayerID` |
| `deployable_damaged` | `deployable`, `damage`, `damage_source`, `damage_type`, `direct_hit` | |
| `chat_message` | `player_name`, `steam_id`, `eos_id`, `channel`, `message` | |

## Parity P0 Event Extensions (Planned)

These contracts are reserved for upcoming parity items and should be implemented with matching event names unless a tracker update changes them.

| Tracker ID | Planned Event Name | Minimum Fields |
|---|---|---|
| `P0-EVT-004` | `admin_cam_possess` | `admin`, `target`, `context` |
| `P0-EVT-005` | `admin_cam_unpossess` | `admin`, `target`, `context` |
| `P0-EVT-006` | `squad_created` | `team_id`, `squad_id`, `squad_name`, `creator` |
| `P0-EVT-007` | `teamkill` | `attacker`, `victim`, `weapon` |

If field names must differ during implementation, update this document and tracker acceptance notes in the same change.

## Contract Test Expectations

- Contract tests live under `tests/contracts/`.
- Parser contract tests should validate:
  - required fields are present
  - field types are correct for parsed payloads
  - `event_name` is exact (case and spelling)
- Contract tests must not assert exact `timestamp` values.

## Fixture Schema (Event Packs)

Real-log fixture pack manifests use `tests/contracts/fixtures/manifest.toml` with this top-level shape:

```toml
schema_version = 1
created_on = "YYYY-MM-DD"

[[packs]]
id = "string"
kind = "log"
source = "path/to/file.log"
sha256 = "hex"
line_count = 1
size_bytes = 1
notes = "string"
```

## Change Control

When changing event payload contracts:

1. Update dataclasses in `squadpy/events/types.py`.
2. Update this document.
3. Update/add contract tests under `tests/contracts/`.
4. Update tracker acceptance notes in `docs/plans/parity-tracker.md`.
