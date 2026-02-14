# RCON Parity Fixtures

This directory stores golden request/response fixtures used by contract tests.

- `manifest.toml` is the canonical inventory for parity command fixtures.
- `requests/` contains command strings or templates used by helpers.
- `responses/` contains representative RCON responses used by contract tests.

These fixtures are designed for deterministic command contract validation and should
be updated in lockstep with parity tracker command surface changes.
