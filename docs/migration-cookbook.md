# SquadPy Migration Cookbook

This guide is for communities migrating from SquadJS or SquadTS to SquadPy using report-first tooling.

## 1) Scope and Outcome

- Goal: move from legacy config to SquadPy with a staged cutover path.
- Constraint: analyzers default to dry-run and do not write files.
- Outcome: produce a reviewed plugin mapping inventory, staged configs, and a reversible production cutover.

## 2) Preconditions

- Existing SquadJS or SquadTS config JSON file.
- Current plugin list and environment secrets captured in an operator runbook.
- Access to a staging Squad server (or equivalent pre-production environment).
- Repo is set up with dev tooling:

```bash
make setup-dev
```

## 3) Pre-Migration Snapshot

Run these before any cutover:

1. Export and store current config files (server config, plugin config, secrets references).
2. Record current plugin behavior baseline:
   - join/leave handling
   - admin request flow
   - chat command behavior
   - moderation actions
3. Record current operational metrics and logs for a known-good window.

Keep this snapshot so rollback has a concrete baseline.

## 4) Generate Report-First Inventory

For SquadJS:

```bash
.venv/bin/python scripts/migrate_from_squadjs.py /path/to/squadjs.config.json
```

For SquadTS:

```bash
.venv/bin/python scripts/migrate_from_squadts.py /path/to/squadts.config.json
```

Expected behavior:

- JSON report is printed to stdout.
- `dry_run` is `true`.
- `writes` is an empty list.
- Inventory rows are categorized as `safe`, `review`, or `unsupported`.

## 5) Build and Lint Migrated Mapping File

Create a migration mapping TOML with one `[[mappings]]` block per source plugin:

```toml
[[mappings]]
source = "AdminRequest"
target = "admin_request"

[[mappings]]
source = "public-commands"
target = "chat_commands"
```

Lint the mapping file:

```bash
.venv/bin/python scripts/lint_migrated_toml.py /path/to/migrated_inventory.toml
```

Use linter output to drive action:

- `safe` + `info`: adopt default plugin mapping, then validate settings.
- `review` + `warning`: manual parameter and behavior review is required.
- `unsupported` + `error`: do not cut over this behavior without replacement strategy.

## 6) Create SquadPy Config Set

1. Start from example config templates:
   - `config/server.toml.example`
   - `config/logging.toml.example`
   - `config/plugins/*.toml.example`
2. Create only the plugin config files required by your reviewed mapping inventory.
3. Transfer secrets from secure source, not from committed plaintext.
4. Keep unsupported capabilities disabled and documented for follow-up.

## 7) Staging Validation

Run in staging first and verify behavior from the baseline snapshot:

```bash
make typecheck
.venv/bin/python -m pytest tests/contracts/migration -v
```

Operator validation checklist:

1. RCON connectivity and command execution.
2. Discord bot connectivity and channel permissions.
3. Core moderation workflows (warn/kick/admin request).
4. High-risk plugin behaviors flagged in `review` findings.
5. No blocker findings remain in migration lint report.

## 8) Production Cutover

Cutover sequence:

1. Announce maintenance window.
2. Stop SquadJS/SquadTS process.
3. Deploy SquadPy config set already validated in staging.
4. Start SquadPy and monitor startup logs for plugin load failures.
5. Run live smoke checks for the baseline capabilities.
6. Keep rollback package available during the entire window.

## 9) Rollback Plan

Immediate rollback trigger examples:

- Critical moderation workflow regression.
- Unrecoverable startup failure on required plugins.
- Repeated runtime failures that impact server operations.

Rollback steps:

1. Stop SquadPy.
2. Restore previous SquadJS/SquadTS config and runtime package from pre-migration snapshot.
3. Start previous stack.
4. Validate baseline workflows from the same smoke checklist.
5. Capture incident notes with failing SquadPy mapping categories (`review` or `unsupported`) for remediation.

## 10) Post-Cutover Stabilization

1. Keep elevated monitoring for at least one full active play cycle.
2. Log any plugin behavior deltas and map them to migration report rows.
3. Convert resolved `review` mappings into runbook defaults for future migrations.
