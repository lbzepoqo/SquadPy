# Repository Guidelines

## Project Structure & Module Organization
- `squadpy/`: framework code (`rcon/`, `log_parser/`, `events/`, `discord/`, `database/`, `server.py`, `plugin.py`, `plugin_loader.py`).
- `plugins/`: built-in plugins (`plugins/<plugin_name>/plugin.py`).
- `config/`: `*.toml.example` templates for server, logging, database, and plugins.
- `tests/`: pytest suite and fixtures (`tests/fixtures/`).
- `docs/plans/`: architecture and phased implementation notes.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate`: create local environment.
- `pip install -e ".[dev]"`: install package plus dev dependencies.
- `python -m squadpy`: run the orchestrator with local TOML configs.
- `pytest -v`: run all tests.
- `pytest tests/test_plugin_loader.py -v`: run a focused module while iterating.

## Coding Style & Naming Conventions
- Python 3.12+, 4-space indentation, PEP 8.
- Use type hints for public APIs and async-heavy paths.
- Naming: `snake_case` for functions/modules/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- Keep plugin code in `plugins/<plugin_name>/plugin.py`, and align config filenames with plugin folder names.
- Keep imports grouped as stdlib, third-party, then local.

## Testing Guidelines
- Use `pytest` with `pytest-asyncio` (`asyncio_mode = "auto"` in `pyproject.toml`).
- Name files `test_<feature>.py`; use fixtures/mocks instead of live RCON/Discord/DB services.
- Add regression tests for bug fixes and log-pattern changes.
- Run targeted tests first; run full `pytest -v` for shared-module changes.

## Commit & Pull Request Guidelines
- Follow Conventional Commit prefixes seen in history: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
- Keep commit subjects imperative and specific.
- PRs should include intent, behavior changes, linked issues, and test commands/results.
- For Discord-facing or plugin UX changes, include a short output sample or screenshot.

## Agent-Focused Workflow
- Treat this file as the default instruction layer for coding agents.
- Before editing, read relevant `README.md` sections, target modules, and matching tests.
- Reuse existing repo patterns before introducing new abstractions.
- Keep diffs minimal and report changed files plus validation commands in handoff notes.

## Security & Configuration Tips
- Do not commit secrets or server identifiers; only example TOMLs should be tracked.
- Treat logs and raw sample data as sensitive; sanitize player IDs/IPs before sharing.
