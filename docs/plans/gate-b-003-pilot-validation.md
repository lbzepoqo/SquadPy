# GATE-B-003 Pilot Validation Runbook

Date: 2026-02-15  
Owner: SquadPy core maintainers  
Gate: `GATE-B-003` (multi-server or broker mode validated in pilot environment)

## Goal

Validate one production-like pilot path end-to-end:

- Option A: multi-server runtime (`squadpy.multi_server.MultiServerRuntime`)
- Option B: broker mode (`squadpy.rcon.broker.RconBroker`)

Gate `GATE-B-003` can be marked complete after one option passes with operator sign-off and captured evidence.

## Required Inputs

- Deployed commit SHA.
- Pilot environment details (host(s), server count, expected player load window).
- Selected validation option: `multi-server` or `broker`.
- Operator on-call and rollback owner.

## Pre-Flight Checklist

- [ ] Deployment SHA recorded.
- [ ] Rollback command/path documented.
- [ ] Baseline health captured (`/api/health`, `/api/readiness`, `/metrics`).
- [ ] API auth and RBAC verified for operators.
- [ ] Monitoring/alert channel open for pilot window.
- [ ] Evidence directory created under `tmp/pilot/gate-b-003/<YYYYMMDD-HHMM>/`.

## Option A: Multi-Server Runtime Validation

### Acceptance Criteria

- [ ] One process runs at least 2 server contexts concurrently.
- [ ] No event or command cross-talk between contexts.
- [ ] One context can be restarted/degraded without cascading the other.

### Pilot Procedure

1. Configure at least two server definitions under `config/servers/<name>/server.toml`.
2. Start SquadPy from repo root: `python -m squadpy`.
3. Confirm both contexts are online and healthy.
4. Trigger server-specific actions on context A and verify only context A plugins react.
5. Trigger server-specific actions on context B and verify only context B plugins react.
6. Intentionally disrupt one context (for example temporary RCON disconnect) and confirm the other context remains healthy.
7. Capture final health/readiness snapshots for all contexts.

### Evidence to Capture

- Startup logs showing both contexts initialized.
- Per-context health/readiness snapshots at start/end.
- Action window logs proving no cross-talk.
- Incident/recovery notes for single-context disruption.

## Option B: Broker Mode Validation

### Acceptance Criteria

- [ ] One upstream RCON socket serves at least 3 authenticated clients.
- [ ] Unauthorized token and unauthorized command are rejected.
- [ ] Concurrent valid client traffic succeeds without response mix-up.

### Pilot Procedure

1. Deploy with one upstream RCON connection and broker client token mapping.
2. Connect at least 3 test clients with distinct tokens.
3. Execute baseline allowed commands from each client (for example `ListPlayers`, `ListSquads`).
4. Attempt one invalid token request and one policy-denied command.
5. Run concurrent command bursts from all valid clients.
6. Verify broker audit records and upstream command execution consistency.

### Evidence to Capture

- Token-auth success/failure records.
- Command allow/deny outcomes with timestamps.
- Upstream command trace/audit excerpts.
- Concurrency run summary (requests, errors, latency observations).

## Exit Checklist

- [ ] Acceptance criteria for selected option satisfied.
- [ ] Evidence package completed.
- [ ] No Sev-1 issues opened by pilot.
- [ ] Operator sign-off recorded.
- [ ] `docs/plans/parity-tracker.md` updated (gate status + acceptance note).

## Evidence File

Use: `docs/plans/gate-b-003-pilot-evidence-template.json`
