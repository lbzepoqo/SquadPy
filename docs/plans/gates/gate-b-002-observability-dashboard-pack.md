# GATE-B-002 Observability Baseline Dashboard Pack

Date: 2026-02-15  
Owner: SquadPy core maintainers  
Gate: `GATE-B-002` (observability baseline dashboard pack published)

## Goal

Provide a standard, no-custom-code dashboard pack for SquadPy runtime health using only `/metrics` signals exposed by `P2-BEYOND-003`.

## Baseline Panels (Prometheus)

| Panel | Query | Notes |
|---|---|---|
| Runtime Ready | `squadpy_runtime_ready` | `1` means all required dependencies are ready. |
| Core Runtime States | `squadpy_runtime_server_running` / `squadpy_runtime_rcon_connected` / `squadpy_runtime_database_initialized` | Should stay `1` during normal operation. |
| Dependency Required Matrix | `squadpy_dependency_required` | Confirms which dependencies are gate-critical per context. |
| Dependency Health Matrix | `squadpy_dependency_healthy` | Track per-dependency health transitions. |
| Plugin Totals by Status | `sum by (status) (squadpy_plugins_total)` | Baseline lifecycle distribution (enabled/failed/disabled). |
| Per-Plugin Lifecycle Status | `squadpy_plugin_status` | Drill-down for plugin-level incidents. |
| Runtime Workload | `squadpy_runtime_plugins_loaded` / `squadpy_runtime_periodic_tasks_active` | Track plugin/task cardinality drift. |
| API Uptime | `squadpy_api_uptime_seconds` | Monotonic growth between restarts. |

## Verification Notes from Current `/metrics` Signals

Evidence window: `tmp/pilot/gate-b-003/20260215-1909-manual-window/`  
Window label `20260215-1909` corresponds to `2026-02-16 03:09` to `03:14` UTC in `startup.log`.

Evidence files:

- `tmp/pilot/gate-b-003/20260215-1909-manual-window/server-a-metrics-start.txt`
- `tmp/pilot/gate-b-003/20260215-1909-manual-window/server-a-metrics-end.txt`
- `tmp/pilot/gate-b-003/20260215-1909-manual-window/server-b-metrics-start.txt`
- `tmp/pilot/gate-b-003/20260215-1909-manual-window/server-b-metrics-end.txt`

Observed stable baseline values across both contexts:

- `squadpy_runtime_ready = 1`
- `squadpy_runtime_server_running = 1`
- `squadpy_runtime_rcon_connected = 1`
- `squadpy_runtime_database_initialized = 1`
- `squadpy_runtime_plugins_loaded = 28`
- `squadpy_runtime_periodic_tasks_active = 12`
- `squadpy_plugins_total{status="enabled"} = 16`
- `squadpy_plugins_total{status="failed"} = 12`
- `squadpy_dependency_required{dependency="server|rcon|database"} = 1`
- `squadpy_dependency_required{dependency="discord|layers"} = 0`
- `squadpy_dependency_healthy{dependency="server|rcon|discord|database|layers"} = 1`

Observed progression checks:

- `server-a`: `squadpy_api_uptime_seconds` moved `53 -> 309`
- `server-b`: `squadpy_api_uptime_seconds` moved `40 -> 305`

Conclusion:

The baseline panel set is verified against a live multi-context window that included single-context RCON disruption/recovery, with no sustained degradation in required readiness/health signals.
