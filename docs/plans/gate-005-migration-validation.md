# GATE-005 Migration Validation Notes

Date: 2026-02-16 (UTC)  
Gate: `GATE-005`  
Scope: validate migration analyzers on at least 3 real community configs.

## Inputs

- `tmp/gate-005/inputs/community-a-config.json`
- `tmp/gate-005/inputs/community-b-config.json`
- `tmp/gate-005/inputs/community-c-config.json`

## Commands Run

```bash
.venv/bin/python scripts/migrate_from_squadjs.py tmp/gate-005/inputs/community-a-config.json --output tmp/gate-005/reports/community-a-config.squadjs.report.json
.venv/bin/python scripts/migrate_from_squadjs.py tmp/gate-005/inputs/community-b-config.json --output tmp/gate-005/reports/community-b-config.squadjs.report.json
.venv/bin/python scripts/migrate_from_squadjs.py tmp/gate-005/inputs/community-c-config.json --output tmp/gate-005/reports/community-c-config.squadjs.report.json

.venv/bin/python scripts/migrate_from_squadts.py tmp/gate-005/inputs/community-a-config.json --output tmp/gate-005/reports/community-a-config.squadts.report.json
.venv/bin/python scripts/migrate_from_squadts.py tmp/gate-005/inputs/community-b-config.json --output tmp/gate-005/reports/community-b-config.squadts.report.json
.venv/bin/python scripts/migrate_from_squadts.py tmp/gate-005/inputs/community-c-config.json --output tmp/gate-005/reports/community-c-config.squadts.report.json
```

## Sanitized Result Summary

SquadJS analyzer results:

- `community-a-config`: `total=64`, `safe=2`, `review=0`, `unsupported=62`, `warnings=0`
- `community-b-config`: `total=25`, `safe=2`, `review=0`, `unsupported=23`, `warnings=0`
- `community-c-config`: `total=31`, `safe=1`, `review=0`, `unsupported=30`, `warnings=0`

SquadTS analyzer cross-check results:

- `community-a-config`: `total=64`, `safe=0`, `review=0`, `unsupported=64`, `warnings=0`
- `community-b-config`: `total=25`, `safe=0`, `review=0`, `unsupported=25`, `warnings=0`
- `community-c-config`: `total=31`, `safe=0`, `review=0`, `unsupported=31`, `warnings=0`

Interpretation:

- All 3 real community configs were successfully processed by migration analyzers.
- Safe mappings appeared only in SquadJS reports, indicating these inputs are SquadJS-shaped configs.
- Reports were written under `tmp/gate-005/reports/` and kept local-only (not tracked).
