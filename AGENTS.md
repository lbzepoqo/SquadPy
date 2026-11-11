# Repository Guidelines

## Project Structure & Module Organization
- `squadpy/`: framework code (`rcon/`, `log_parser/`, `events/`, `discord/`, `database/`, `server.py`, `plugin.py`, `plugin_loader.py`).
- `plugins/`: built-in plugins (`plugins/<plugin_name>/plugin.py`).
- `config/`: `*.toml.example` templates for server, logging, database, and plugins.
- `tests/`: pytest suite and fixtures (`tests/fixtures/`).
- `docs/plans/`: execution tracker and shared plan docs.
- `docs/plans/architecture/`: dated architecture/design/phase implementation docs.
- `docs/plans/gates/`: gate evidence, runbooks, and tracking ledgers.

## Quick Reference
- Design reference: `docs/plans/architecture/2026-02-08-squadpy-design.md`.
- Strategic roadmap: `docs/plans/architecture/2026-02-13-parity-and-beyond-roadmap.md`.
- Runtime entrypoint: `python -m squadpy`.
- Python runtime: 3.12+.
- Local venv: `.venv/` (activate with `. .venv/bin/activate`).

## Runtime Architecture Snapshot
- Runtime flow: Log Reader (local/SFTP) -> Log Parser (regex + state) -> Event Bus -> Plugins.
- RCON client integrates with parser/plugin workflows and enforces command/response correlation.
- Core service model: RCON is required; log reader, Discord, and database are optional by config.
- Plugin service requirements are declared via `requires = [...]`; missing required services fail plugin load without crashing the whole runtime.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate`: create local environment.
- `pip install -e ".[dev]"`: install package plus dev dependencies.
- `python -m squadpy`: run the orchestrator with local TOML configs.
- `make setup-dev`: install/update dev dependencies in `.venv`.
- `make test`: run all tests through the project virtualenv.
- `make test-unit`: run non-contract tests through the project virtualenv.
- `make test-contract`: run contract tests through the project virtualenv.
- `make test-integration`: run integration matrix modules through the project virtualenv.
- `make test-integration-discord`: run Discord integration module set.
- `make test-integration-rcon`: run RCON/runtime integration module set.
- `.venv/bin/python -m pytest -v`: direct test invocation using the project virtualenv interpreter.
- `.venv/bin/python -m pytest tests/test_plugin_loader.py -v`: run a focused module while iterating.

## Coding Style & Naming Conventions
- Python 3.12+, 4-space indentation, PEP 8.
- Use type hints for public APIs and async-heavy paths.
- Naming: `snake_case` for functions/modules/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- Keep plugin code in `plugins/<plugin_name>/plugin.py`, and align config filenames with plugin folder names.
- Keep imports grouped as stdlib, third-party, then local.

## Core Patterns
- Events: typed dataclasses inherit `BaseEvent` and expose `event_name` for bus dispatch.
- Plugins: use `@on_event("<event_name>")` for event hooks and `@periodic(seconds=<n>)` for periodic tasks.
- Config: use Pydantic models loaded from TOML for runtime/plugin configuration validation.

## Testing Guidelines
- Use `pytest` with `pytest-asyncio` (`asyncio_mode = "auto"` in `pyproject.toml`).
- Name files `test_<feature>.py`; use fixtures/mocks instead of live RCON/Discord/DB services.
- Add regression tests for bug fixes and log-pattern changes.
- Run targeted tests first; run full `pytest -v` for shared-module changes.

## Commit & Pull Request Guidelines
- Follow Conventional Commit prefixes seen in history: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
- Keep commit subjects imperative and specific.
- Keep commits logically scoped: separate feature changes, refactors, and test/chore updates into different commits.
- PRs should include intent, behavior changes, linked issues, and test commands/results.
- For Discord-facing or plugin UX changes, include a short output sample or screenshot.

## Agent-Focused Workflow
- Treat this file as the default instruction layer for coding agents.
- Scrutinize requirements, acceptance criteria, and likely edge cases before implementing changes.
- If scope or intent is unclear, ask clarifying questions first instead of guessing.
- If a requirement or task does not make sense, be explicit and honest about the concern, then request clarification before proceeding.
- Before editing, read relevant `README.md` sections, target modules, and matching tests.
- Reuse existing repo patterns before introducing new abstractions.
- Keep each commit to one purpose, and report changed files plus validation commands in handoff notes.
- For test execution, always use the project virtualenv (`make test*` or `.venv/bin/python -m pytest ...`), not system `python3`/`pytest`.
- Run `make typecheck` before every commit/handoff and include the result in validation notes.

## Parity Program Workflow
- For SquadJS/SquadTS parity work, treat `docs/plans/architecture/2026-02-13-parity-and-beyond-roadmap.md` as the strategic source of truth.
- Treat `docs/plans/parity-tracker.md` as the execution source of truth for task status and acceptance criteria.
- When implementing parity tasks, reference the tracker ID (for example `P0-RCON-001`) in commit messages, PR notes, and handoff summaries.
- Update checkbox status and acceptance notes in `docs/plans/parity-tracker.md` in the same change whenever practical.
- If scope changes, update both roadmap and tracker to keep strategy and execution aligned.
- For active `GATE-002`/`GATE-003`/`GATE-004` windows, update `docs/plans/gates/gate-window-tracking.md` via `scripts/record_gate_windows.py` and include the generated evidence path (`tmp/gate-windows/<YYYY-MM-DD>.json`) in handoff notes.

## Security & Configuration Tips
- Do not commit secrets or server identifiers; only example TOMLs should be tracked.
- Treat logs and raw sample data as sensitive; sanitize player IDs/IPs before sharing.
- Keep `*.toml.example` tracked; keep real runtime TOMLs (`config/*.toml`, `config/plugins/*.toml`, per-server configs) untracked.

## Runtime Conventions
- Use stdlib asyncio primitives in runtime paths.
- Use logger namespace `squadpy.<component>` for service/plugin logging.
- File log rotation uses timestamped backups; default `max_files = 10` unless config overrides it.

## Live Capture Workflow (Logs + RCON)
- For live parity validation, prefer a windowed capture approach instead of long-running noisy tails.
- `start capture`: record baseline log offset/time and snapshot `ListPlayers` + `ListSquads`.
- During the action window, monitor both sources:
  - appended log lines from baseline offset
  - RCON state deltas (players/squads) via polling
- `stop capture`: collect only appended log bytes and post-action `ListPlayers`/`ListSquads`.
- Store sanitized excerpts as fixtures and reference the scenario window in handoff notes.
