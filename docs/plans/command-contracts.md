# SquadPy Command Contract Schema

Date: 2026-02-14
Owner: `@core-runtime`
Tracker IDs: `P0-PROG-007`, `P0-RCON-*`

## Purpose

This document defines command contract rules for SquadPy RCON helpers.
It is the source of truth for:

- helper-to-command mapping
- request template schema
- response handling expectations
- contract test requirements

Implementation source: `squadpy/rcon/client.py`
Fixture source: `tests/contracts/fixtures/rcon/manifest.toml`

## Versioning

- Contract schema version: `1`
- Compatibility policy: additive-only helper changes within the same major version
- Breaking command shape changes require fixture and contract updates in the same change

## Command Contract Model

Each command contract entry must define:

```toml
[[commands]]
id = "string"
helper = "string"
priority = "p0|p1|p2"
request_fixture = "tests/contracts/fixtures/rcon/requests/<name>.txt"
response_fixture = "tests/contracts/fixtures/rcon/responses/<name>.txt"
notes = "string"
```

Request fixture may be:

- an exact command string (no placeholders), or
- a format template with placeholders (for example `{player_id}`)

## Runtime Rules

- Helper methods must build request strings exactly as contract templates specify.
- Quoted player identifiers remain quoted in admin commands where the template defines quotes.
- Response handling defaults to passthrough raw RCON response `str`, unless helper contract explicitly defines parser behavior.
- Parser helpers (`list_players`, `list_squads`, `show_current_map`, `show_next_map`) must map response text into typed dataclasses (`RconPlayer`, `RconSquad`, `MapInfo`).

## Current Helper Contract Matrix

| Helper | Contract ID | Request Template | Response Contract |
|---|---|---|---|
| `list_players()` | `list_players` | `ListPlayers` | parse to `list[RconPlayer]` |
| `list_squads()` | `list_squads` | `ListSquads` | parse to `list[RconSquad]` |
| `broadcast(message)` | `broadcast` | `AdminBroadcast {message}` | passthrough `str` |
| `warn(player_id, message)` | `warn` | `AdminWarn "{player_id}" {message}` | passthrough `str` |
| `kick(player_id, reason)` | `kick` | `AdminKick "{player_id}" {reason}` | passthrough `str` |
| `ban(player_id, duration, reason)` | `ban` | `AdminBan "{player_id}" {duration} {reason}` | passthrough `str` |
| `switch_team(player_id)` | `switch_team` | `AdminSwitchTeam "{player_id}"` | passthrough `str` |
| `show_current_map()` | `show_current_map` | `ShowCurrentMap` | parse to `MapInfo \| None` |
| `show_next_map()` | `show_next_map` | `ShowNextMap` | parse to `MapInfo \| None`; returns `None` when response contains `not defined` |

## Planned Parity Helper Contracts

These command IDs already exist in fixtures and are reserved for upcoming helper implementation:

| Tracker ID | Contract ID | Planned Helper |
|---|---|---|
| `P0-RCON-003` | `force_team_change` | force team change helper |
| `P0-RCON-004` | `set_fog_of_war` | `set_fog_of_war(mode)` |
| `P0-RCON-005` | `set_next_layer` | `set_next_layer(layer)` |
| `P1-RCON-006` | `demote_commander` | `demote_commander(player_id)` |
| `P1-RCON-007` | `set_team` | `set_team(player_id, team)` |
| `P1-RCON-008` | `end_match` | `end_match()` |

## Contract Test Expectations

Command contract tests under `tests/contracts/` should validate:

- exact request command generation for representative inputs
- correct response handling path (passthrough or parsed result)
- error-path behavior where explicitly defined by fixture response (for example invalid ID cases)

Minimum acceptance for each new helper:

1. one helper-focused unit test in `tests/test_rcon_helpers.py`
2. one contract test under `tests/contracts/core_runtime/`
3. fixture manifest entry in `tests/contracts/fixtures/rcon/manifest.toml`

## Example Contract Assertion

```python
expected = 'AdminBan "76561198000000000" 24h Cheating'
client.execute.assert_awaited_once_with(expected)
```

## Change Control

When changing command contracts:

1. Update helper implementation in `squadpy/rcon/client.py`.
2. Update request/response fixtures and `tests/contracts/fixtures/rcon/manifest.toml`.
3. Update/add unit and contract tests.
4. Update this document and tracker acceptance notes.
