"""Report-first SquadTS migration analyzer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from squadpy.migration.reporting import InventoryItem, MappingCategory, build_inventory_report, load_json_config

_PluginMapping = tuple[str | None, MappingCategory, str]

SQUADTS_PLUGIN_MAPPINGS: dict[str, _PluginMapping] = {
    "@squadts/admin-request": ("admin_request", "safe", "Direct SquadPy plugin equivalent is available."),
    "@squadts/discord-chat": ("discord_chat_bridge", "safe", "Use SquadPy Discord chat bridge configuration."),
    "@squadts/chat-commands": (
        "chat_commands",
        "review",
        "Command aliases and permission scopes should be reviewed before cutover.",
    ),
    "@squadts/db-log": ("db_log", "review", "Validate schema and retention policy differences before enabling."),
}


def analyze_squadts_file(config_path: Path) -> dict[str, Any]:
    """Analyze a SquadTS JSON config and return inventory report data."""
    config = load_json_config(config_path)
    inventory: list[InventoryItem] = []
    warnings: list[str] = []

    _collect_server_inventory(config, inventory)
    _collect_discord_inventory(config, inventory)
    _collect_plugin_inventory(config, inventory, warnings)

    return build_inventory_report(
        source="squadts",
        input_path=config_path,
        inventory=inventory,
        warnings=warnings,
        dry_run=True,
    )


def _collect_server_inventory(config: dict[str, Any], inventory: list[InventoryItem]) -> None:
    core = config.get("core")
    if not isinstance(core, dict):
        return

    rcon = core.get("rcon")
    if not isinstance(rcon, dict):
        return

    for source_field, target_field in (
        ("host", "rcon.host"),
        ("port", "rcon.port"),
        ("password", "rcon.password"),
    ):
        value = rcon.get(source_field)
        if value is None:
            continue
        inventory.append({
            "source_key": f"core.rcon.{source_field}",
            "source_value": str(value),
            "target": f"config/server.toml:[{target_field}]",
            "category": "safe",
            "note": "Direct server configuration mapping.",
        })


def _collect_discord_inventory(config: dict[str, Any], inventory: list[InventoryItem]) -> None:
    discord = config.get("discord")
    if not isinstance(discord, dict):
        return

    for source_field, target_field in (
        ("token", "discord.token"),
        ("guildId", "discord.guild_id"),
    ):
        value = discord.get(source_field)
        if value is None:
            continue
        inventory.append({
            "source_key": f"discord.{source_field}",
            "source_value": str(value),
            "target": f"config/server.toml:[{target_field}]",
            "category": "safe",
            "note": "Direct Discord configuration mapping.",
        })


def _collect_plugin_inventory(
    config: dict[str, Any],
    inventory: list[InventoryItem],
    warnings: list[str],
) -> None:
    raw_plugins = config.get("plugins")
    if not isinstance(raw_plugins, list):
        warnings.append("No plugins list found at config.plugins.")
        return

    for index, raw_plugin in enumerate(raw_plugins):
        plugin_name = _extract_plugin_name(raw_plugin)
        if plugin_name is None:
            warnings.append(f"Could not resolve plugin name at plugins[{index}].")
            continue

        mapping = SQUADTS_PLUGIN_MAPPINGS.get(plugin_name.strip().lower())
        if mapping is None:
            inventory.append({
                "source_key": f"plugins[{index}]",
                "source_value": plugin_name,
                "target": None,
                "category": "unsupported",
                "note": "No SquadPy equivalent is currently mapped.",
            })
            continue

        target, category, note = mapping
        inventory.append({
            "source_key": f"plugins[{index}]",
            "source_value": plugin_name,
            "target": target,
            "category": category,
            "note": note,
        })


def _extract_plugin_name(plugin_entry: Any) -> str | None:
    if isinstance(plugin_entry, str):
        trimmed = plugin_entry.strip()
        return trimmed if trimmed else None

    if not isinstance(plugin_entry, dict):
        return None

    for key in ("name", "plugin", "package", "id"):
        candidate = plugin_entry.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None
