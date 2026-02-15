# Plugin Behavior Mapping Matrix

This matrix maps known SquadJS/SquadTS source plugins to SquadPy target plugins or equivalent migration strategies.

Category definitions:

- `safe`: direct target plugin exists with expected baseline behavior.
- `review`: target exists, but requires manual policy/threshold/permission review.
- `unsupported`: no built-in equivalent today; use fallback strategy or custom implementation.

## SquadJS Source Plugins

| Source plugin | SquadPy target/equivalent | Category | Migration strategy |
|---|---|---|---|
| `adminrequest` | `admin_request` | `safe` | Use `config/plugins/admin_request.toml` and validate Discord thread workflow in staging. |
| `autokickunassigned` | `auto_kick_unassigned` | `safe` | Use `config/plugins/auto_kick_unassigned.toml` defaults and verify warning/kick thresholds. |
| `discordchat` | `discord_chat_bridge` | `safe` | Migrate channel IDs and validate bidirectional relay behavior. |
| `public-commands` | `chat_commands` | `review` | Reconcile command names, role gates, and cooldown policy before production cutover. |
| `db-log` | `db_log` | `review` | Compare table retention and analytics requirements, then migrate with schema review. |

## SquadTS Source Plugins

| Source plugin | SquadPy target/equivalent | Category | Migration strategy |
|---|---|---|---|
| `@squadts/admin-request` | `admin_request` | `safe` | Map to `admin_request` and validate admin ticket workflow and notification routing. |
| `@squadts/discord-chat` | `discord_chat_bridge` | `safe` | Map Discord bridge settings and verify relay channels in staging. |
| `@squadts/chat-commands` | `chat_commands` | `review` | Review command alias behavior and moderator permission model before cutover. |
| `@squadts/db-log` | `db_log` | `review` | Review persisted fields, pruning policy, and query/report expectations. |

## Unsupported/Custom Source Plugins

| Source plugin | SquadPy target/equivalent | Category | Migration strategy |
|---|---|---|---|
| any unmapped plugin | custom plugin or external service | `unsupported` | Keep feature on legacy stack temporarily, or implement a SquadPy custom plugin and validate in staging prior to cutover. |
