# SquadPy Weekly Parity Report Template

Use this template for a weekly parity status update tied to `docs/plans/parity-tracker.md`.

## Report Metadata

- Week of: `YYYY-MM-DD`
- Report date: `YYYY-MM-DD`
- Prepared by: `@owner`
- Tracker revision: `git commit / branch`

## 1) Executive Summary

- Overall status: `On track | At risk | Off track`
- Headline: `one-sentence summary`
- Context: `what materially changed this week`

## 2) Tracker Delta (This Week)

- Completed IDs: `P0-...`, `P1-...`
- In-progress IDs: `P0-...`, `P1-...`
- Newly blocked IDs: `P0-...`, `P1-...`
- Reopened IDs: `P0-...`, `P1-...`

## 3) Progress Snapshot

| Bucket | Done | In Progress | Blocked | Not Started |
|---|---:|---:|---:|---:|
| `P0` | `0` | `0` | `0` | `0` |
| `P1` | `0` | `0` | `0` | `0` |
| `P2` | `0` | `0` | `0` | `0` |
| `GATE-*` | `0` | `0` | `0` | `0` |

## 4) Capability/Parity Changes

List only capability rows that changed status this week.

| Capability | Previous | Current | Tracker IDs | Evidence |
|---|---|---|---|---|
| `<name>` | `Missing/Partial/Done` | `Missing/Partial/Done` | `P0-...` | `tests/...` or `docs/...` |

## 5) Validation Evidence

- Commands run:
  - ``pytest -m contract -v`` -> `pass/fail + short note`
  - ``pytest -m integration -v`` -> `pass/fail + short note`
  - `other checks` -> `pass/fail + short note`
- Not run (if any) and reason:
  - `<command>` -> `<reason>`

## 6) Risks and Mitigations

- Risk: `<risk statement>`
  - Mitigation: `<mitigation in place>`
  - Owner: `@owner`
  - Target date: `YYYY-MM-DD`

## 7) Decisions and Open Questions

- Decision made: `<summary>`
- Decision needed: `<summary + decision owner>`
- Escalation needed: `yes/no + why`

## 8) Next Week Plan

- Top 5 queued IDs: `P0-...`, `P1-...`
- Dependencies/prerequisites:
  - `<dependency>`
- Success criteria for next report:
  - `<measurable outcome>`

## 9) Copy Block for `parity-tracker.md`

Use this block in section `9) Weekly Update Block (Copy/Paste)` of `docs/plans/parity-tracker.md`.

```md
Week of: YYYY-MM-DD

- Completed IDs: `...`
- In-progress IDs: `...`
- Blocked IDs: `...`
- New risks: ...
- Mitigations applied: ...
- Next week top 5 IDs: `...`
```
