"""Plugin scaffolder helpers for generating typed plugin skeletons."""

from __future__ import annotations

import keyword
import re
from dataclasses import dataclass
from pathlib import Path

_NON_SLUG_CHARS_RE = re.compile(r"[^a-z0-9_]+")
_MULTI_UNDERSCORE_RE = re.compile(r"_+")


@dataclass(frozen=True)
class PluginScaffoldResult:
    plugin_slug: str
    class_name: str
    display_name: str
    writes: list[Path]

    def as_dict(self) -> dict[str, object]:
        return {
            "plugin_slug": self.plugin_slug,
            "class_name": self.class_name,
            "display_name": self.display_name,
            "writes": [str(path) for path in self.writes],
        }


def normalize_plugin_slug(raw_name: str) -> str:
    normalized = str(raw_name).strip().lower().replace("-", "_").replace(" ", "_")
    normalized = _NON_SLUG_CHARS_RE.sub("_", normalized)
    normalized = _MULTI_UNDERSCORE_RE.sub("_", normalized).strip("_")

    if not normalized:
        raise ValueError("plugin_name must include at least one letter or number")
    if normalized[0].isdigit():
        raise ValueError("plugin_name must start with a letter")
    if keyword.iskeyword(normalized):
        raise ValueError("plugin_name must not be a Python keyword")
    return normalized


def plugin_class_name(plugin_slug: str) -> str:
    base_name = "".join(part.capitalize() for part in plugin_slug.split("_"))
    if base_name.endswith("Plugin"):
        return base_name
    return base_name + "Plugin"


def display_name_from_slug(plugin_slug: str) -> str:
    return " ".join(part.capitalize() for part in plugin_slug.split("_"))


def scaffold_plugin(
    plugin_name: str,
    *,
    base_dir: Path,
    display_name: str | None = None,
    force: bool = False,
) -> PluginScaffoldResult:
    plugin_slug = normalize_plugin_slug(plugin_name)
    class_name = plugin_class_name(plugin_slug)
    resolved_display_name = (
        str(display_name).strip() if display_name and str(display_name).strip()
        else display_name_from_slug(plugin_slug)
    )

    plugin_path = base_dir / "plugins" / plugin_slug / "plugin.py"
    test_path = base_dir / "tests" / f"test_plugin_{plugin_slug}.py"
    config_path = base_dir / "config" / "plugins" / f"{plugin_slug}.toml.example"

    outputs: list[tuple[Path, str]] = [
        (
            plugin_path,
            _plugin_template(
                plugin_slug=plugin_slug,
                class_name=class_name,
                display_name=resolved_display_name,
            ),
        ),
        (
            test_path,
            _test_template(
                plugin_slug=plugin_slug,
                class_name=class_name,
                display_name=resolved_display_name,
            ),
        ),
        (
            config_path,
            _config_template(plugin_slug=plugin_slug),
        ),
    ]

    existing = [path for path, _ in outputs if path.exists()]
    if existing and not force:
        existing_list = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite existing files: {existing_list}")

    writes: list[Path] = []
    for path, content in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        writes.append(path)

    return PluginScaffoldResult(
        plugin_slug=plugin_slug,
        class_name=class_name,
        display_name=resolved_display_name,
        writes=writes,
    )


def _plugin_template(*, plugin_slug: str, class_name: str, display_name: str) -> str:
    return (
        '"""Generated plugin skeleton."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "from squadpy.events.types import ChatMessage, PlayerConnected\n"
        "from squadpy.plugin import Plugin, on_event, periodic\n"
        "\n"
        "\n"
        f"class {class_name}(Plugin):\n"
        f'    name = "{display_name}"\n'
        '    description = "TODO: describe plugin behavior"\n'
        '    requires = ["rcon"]\n'
        "\n"
        "    async def on_enable(self) -> None:\n"
        '        self.logger.info("Enabled %s", self.name)\n'
        "\n"
        "    async def on_disable(self) -> None:\n"
        '        self.logger.info("Disabled %s", self.name)\n'
        "\n"
        '    @on_event("player_connected")\n'
        "    async def handle_player_connected(self, event: PlayerConnected) -> None:\n"
        '        self.logger.debug("Player connected: %s", event.player.name)\n'
        "\n"
        '    @on_event("chat_message")\n'
        "    async def handle_chat_message(self, event: ChatMessage) -> None:\n"
        f'        if event.message.startswith("!{plugin_slug}"):\n'
        '            await self.rcon.warn(event.eos_id, "TODO: implement command handling.")\n'
        "\n"
        "    @periodic(seconds=60)\n"
        "    async def periodic_healthcheck(self) -> None:\n"
        "        players = await self.rcon.list_players()\n"
        '        self.logger.debug("%s online players", len(players))\n'
    )


def _test_template(*, plugin_slug: str, class_name: str, display_name: str) -> str:
    return (
        '"""Generated tests for plugin skeleton."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        f"from plugins.{plugin_slug}.plugin import {class_name}\n"
        "from squadpy.events.types import ChatMessage, PlayerConnected\n"
        "\n"
        "\n"
        "def test_plugin_metadata() -> None:\n"
        f'    assert {class_name}.name == "{display_name}"\n'
        f"    assert {class_name}.description == \"TODO: describe plugin behavior\"\n"
        f"    assert {class_name}.requires == [\"rcon\"]\n"
        "\n"
        "\n"
        "def test_plugin_hooks_are_registered_and_typed() -> None:\n"
        f"    handlers = dict({class_name}.get_event_handlers())\n"
        '    assert handlers["player_connected"] == "handle_player_connected"\n'
        '    assert handlers["chat_message"] == "handle_chat_message"\n'
        "\n"
        f"    periodic_tasks = dict({class_name}.get_periodic_tasks())\n"
        '    assert periodic_tasks["periodic_healthcheck"] == 60\n'
        "\n"
        f"    assert {class_name}.handle_player_connected.__annotations__[\"event\"] is PlayerConnected\n"
        f"    assert {class_name}.handle_chat_message.__annotations__[\"event\"] is ChatMessage\n"
    )


def _config_template(*, plugin_slug: str) -> str:
    return (
        "enabled = true\n"
        "\n"
        "[settings]\n"
        f'name = "{plugin_slug}"\n'
        "enabled = true\n"
    )
