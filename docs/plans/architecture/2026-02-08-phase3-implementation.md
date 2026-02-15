# Phase 3 — Discord Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Discord as a core service to SquadPy with connector, decorators, and a built-in PluginManager plugin.

**Architecture:** `DiscordConnector` wraps discord.py `commands.Bot`, runs as an asyncio task in the main loop. Plugins interact via convenience methods and `@slash_command`/`@on_discord` decorators. Interaction routing uses auto-namespaced `custom_id` to prevent plugin collisions.

**Tech Stack:** discord.py, Pydantic (config), asyncio, pytest + unittest.mock

---

### Task 1: Add discord.py Dependency

**Files:**
- Modify: `pyproject.toml:6-8`

**Step 1: Add discord.py to dependencies**

In `pyproject.toml`, add `discord.py` to the dependencies list:

```toml
dependencies = [
    "pydantic>=2.0",
    "discord.py>=2.3",
]
```

**Step 2: Install**

Run: `pip install -e ".[dev]"`
Expected: discord.py installs successfully

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add discord.py dependency"
```

---

### Task 2: DiscordConfig Pydantic Model

**Files:**
- Modify: `squadpy/config.py:68-70` (add DiscordConfig, update ServerConfig)
- Modify: `config/server.toml.example` (add [discord] section)
- Modify: `tests/test_config.py` (add DiscordConfig tests)

**Step 1: Write failing tests**

Add to `tests/test_config.py`:

```python
from squadpy.config import DiscordConfig

class TestDiscordConfig:
    def test_defaults(self):
        config = DiscordConfig()
        assert config.enabled is False
        assert config.token == ""
        assert config.guild_id == 0
        assert config.command_prefix == "!"

    def test_valid_config(self):
        config = DiscordConfig(
            enabled=True,
            token="Bot_Token_Here",
            guild_id=123456789012345678,
        )
        assert config.enabled is True
        assert config.guild_id == 123456789012345678

    def test_enabled_without_token_raises(self):
        """When enabled=True, token must be non-empty."""
        with pytest.raises(Exception):
            DiscordConfig(enabled=True, guild_id=123456789012345678)

    def test_enabled_without_guild_id_raises(self):
        """When enabled=True, guild_id must be non-zero."""
        with pytest.raises(Exception):
            DiscordConfig(enabled=True, token="some_token")

class TestServerConfigWithDiscord:
    def test_discord_is_optional(self):
        config = ServerConfig(rcon={"host": "127.0.0.1", "password": "pass"})
        assert config.discord.enabled is False

    def test_discord_section_parsed(self):
        config = ServerConfig(
            rcon={"host": "127.0.0.1", "password": "pass"},
            discord={"enabled": True, "token": "tok", "guild_id": 123456789012345678},
        )
        assert config.discord.enabled is True
        assert config.discord.token == "tok"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py::TestDiscordConfig -v`
Expected: FAIL (DiscordConfig not defined)

**Step 3: Implement DiscordConfig**

Add to `squadpy/config.py` before `ServerConfig`:

```python
class DiscordConfig(BaseModel):
    enabled: bool = False
    token: str = ""
    guild_id: int = 0
    command_prefix: str = "!"

    @model_validator(mode="after")
    def validate_enabled_fields(self) -> "DiscordConfig":
        if self.enabled:
            if not self.token:
                raise ValueError("Discord token is required when enabled")
            if not self.guild_id:
                raise ValueError("Discord guild_id is required when enabled")
        return self
```

Add `model_validator` to the import: `from pydantic import BaseModel, field_validator, model_validator`

Update `ServerConfig`:

```python
class ServerConfig(BaseModel):
    rcon: RconConfig
    log: LogConfig = LogConfig()
    discord: DiscordConfig = DiscordConfig()
```

**Step 4: Update server.toml.example**

Append to `config/server.toml.example`:

```toml
# [discord]
# enabled = true
# token = "your_bot_token_here"
# guild_id = 123456789012345678
# command_prefix = "!"
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: All pass

**Step 6: Commit**

```bash
git add squadpy/config.py config/server.toml.example tests/test_config.py
git commit -m "feat: add DiscordConfig with validation"
```

---

### Task 3: Discord Decorators (@slash_command, @on_discord)

**Files:**
- Modify: `squadpy/plugin.py` (add decorators + class methods)
- Create: `tests/test_discord_decorators.py`

**Step 1: Write failing tests**

Create `tests/test_discord_decorators.py`:

```python
"""Tests for Discord decorators (@slash_command, @on_discord)."""

import pytest

from squadpy.plugin import Plugin, on_event, slash_command, on_discord


class DiscordPlugin(Plugin):
    name = "Discord Test"
    requires = ["discord"]

    @slash_command(name="status", description="Show server status")
    async def show_status(self, interaction):
        pass

    @slash_command(name="reload", description="Reload a plugin")
    async def reload_cmd(self, interaction):
        pass

    @on_discord("button_click", custom_id="claim")
    async def handle_claim(self, interaction):
        pass

    @on_discord("select_menu", custom_id="team_select")
    async def handle_select(self, interaction):
        pass

    @on_discord("modal_submit", custom_id="report_form")
    async def handle_modal(self, interaction):
        pass

    @on_discord("thread_message")
    async def handle_thread(self, message):
        pass


class TestSlashCommandDecorator:
    def test_marks_method_with_metadata(self):
        method = DiscordPlugin.show_status
        assert hasattr(method, "_squadpy_slash_command")
        meta = method._squadpy_slash_command
        assert meta["name"] == "status"
        assert meta["description"] == "Show server status"

    def test_collects_all_slash_commands(self):
        commands = DiscordPlugin.get_slash_commands()
        names = {meta["name"] for meta, _ in commands}
        assert names == {"status", "reload"}

    def test_slash_command_returns(self):
        """Decorator returns list of (meta_dict, method_name) tuples."""
        commands = DiscordPlugin.get_slash_commands()
        for meta, method_name in commands:
            assert isinstance(meta, dict)
            assert isinstance(method_name, str)


class TestOnDiscordDecorator:
    def test_marks_button_click_handler(self):
        method = DiscordPlugin.handle_claim
        assert hasattr(method, "_squadpy_on_discord")
        meta = method._squadpy_on_discord
        assert meta["event_type"] == "button_click"
        assert meta["custom_id"] == "claim"

    def test_marks_select_menu_handler(self):
        meta = DiscordPlugin.handle_select._squadpy_on_discord
        assert meta["event_type"] == "select_menu"
        assert meta["custom_id"] == "team_select"

    def test_marks_modal_submit_handler(self):
        meta = DiscordPlugin.handle_modal._squadpy_on_discord
        assert meta["event_type"] == "modal_submit"
        assert meta["custom_id"] == "report_form"

    def test_marks_thread_message_handler(self):
        meta = DiscordPlugin.handle_thread._squadpy_on_discord
        assert meta["event_type"] == "thread_message"
        assert meta["custom_id"] is None

    def test_collects_all_discord_handlers(self):
        handlers = DiscordPlugin.get_discord_handlers()
        event_types = {meta["event_type"] for meta, _ in handlers}
        assert event_types == {"button_click", "select_menu", "modal_submit", "thread_message"}

    def test_invalid_event_type_raises(self):
        with pytest.raises(ValueError, match="Unknown discord event type"):
            @on_discord("invalid_type", custom_id="x")
            async def bad_handler(self, interaction):
                pass
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_discord_decorators.py -v`
Expected: FAIL (slash_command, on_discord not importable)

**Step 3: Implement decorators**

Add to `squadpy/plugin.py` after the `periodic` decorator:

```python
VALID_DISCORD_EVENT_TYPES = {"button_click", "select_menu", "modal_submit", "thread_message"}


def slash_command(name: str, description: str = ""):
    """Decorator to register a plugin method as a Discord slash command."""
    def decorator(func):
        func._squadpy_slash_command = {"name": name, "description": description}
        return func
    return decorator


def on_discord(event_type: str, custom_id: str | None = None):
    """Decorator to register a plugin method as a Discord interaction handler."""
    if event_type not in VALID_DISCORD_EVENT_TYPES:
        raise ValueError(
            f"Unknown discord event type: {event_type}. "
            f"Valid types: {VALID_DISCORD_EVENT_TYPES}"
        )
    def decorator(func):
        func._squadpy_on_discord = {"event_type": event_type, "custom_id": custom_id}
        return func
    return decorator
```

Add class methods to `Plugin`:

```python
@classmethod
def get_slash_commands(cls) -> list[tuple[dict, str]]:
    """Return list of (meta_dict, method_name) for all @slash_command methods."""
    commands = []
    for attr_name in dir(cls):
        attr = getattr(cls, attr_name, None)
        if callable(attr) and hasattr(attr, "_squadpy_slash_command"):
            commands.append((attr._squadpy_slash_command, attr_name))
    return commands

@classmethod
def get_discord_handlers(cls) -> list[tuple[dict, str]]:
    """Return list of (meta_dict, method_name) for all @on_discord methods."""
    handlers = []
    for attr_name in dir(cls):
        attr = getattr(cls, attr_name, None)
        if callable(attr) and hasattr(attr, "_squadpy_on_discord"):
            handlers.append((attr._squadpy_on_discord, attr_name))
    return handlers
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_discord_decorators.py -v`
Expected: All pass

**Step 5: Update exports**

In `squadpy/__init__.py`, add exports:

```python
from squadpy.plugin import Plugin, on_event, periodic, slash_command, on_discord
__all__ = ["Plugin", "on_event", "periodic", "slash_command", "on_discord", "BaseEvent", "__version__"]
```

**Step 6: Commit**

```bash
git add squadpy/plugin.py squadpy/__init__.py tests/test_discord_decorators.py
git commit -m "feat: add @slash_command and @on_discord decorators"
```

---

### Task 4: DiscordConnector Core

**Files:**
- Create: `squadpy/discord/connector.py`
- Modify: `squadpy/discord/__init__.py`
- Create: `tests/test_discord_connector.py`

**Step 1: Write failing tests**

Create `tests/test_discord_connector.py`:

```python
"""Tests for DiscordConnector."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squadpy.config import DiscordConfig
from squadpy.discord.connector import DiscordConnector


@pytest.fixture
def discord_config():
    return DiscordConfig(enabled=True, token="test_token", guild_id=123456789)


class TestConnectorInit:
    def test_creates_connector(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_commands.Bot.return_value = MagicMock()
            connector = DiscordConnector(discord_config)
            assert connector.guild_id == 123456789
            assert connector.bot is not None

    def test_stores_config(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_commands.Bot.return_value = MagicMock()
            connector = DiscordConnector(discord_config)
            assert connector._config == discord_config


class TestConnectorLifecycle:
    async def test_start_creates_task(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = AsyncMock()
            mock_commands.Bot.return_value = mock_bot
            connector = DiscordConnector(discord_config)
            # Don't actually start the bot — just verify start is callable
            assert callable(connector.start)

    async def test_close_calls_bot_close(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = AsyncMock()
            mock_commands.Bot.return_value = mock_bot
            connector = DiscordConnector(discord_config)
            connector._bot_task = MagicMock()
            connector._bot_task.cancel = MagicMock()
            await connector.close()
            mock_bot.close.assert_awaited_once()


class TestConnectorSend:
    async def test_send_to_channel(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_channel = AsyncMock()
            mock_bot.get_channel.return_value = mock_channel
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(discord_config)
            await connector.send(999, content="Hello")
            mock_bot.get_channel.assert_called_once_with(999)
            mock_channel.send.assert_awaited_once_with(content="Hello", embed=None, view=None)

    async def test_send_returns_none_if_channel_not_found(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_bot.get_channel.return_value = None
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(discord_config)
            result = await connector.send(999, content="Hello")
            assert result is None

    async def test_get_channel(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_channel = MagicMock()
            mock_bot.get_channel.return_value = mock_channel
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(discord_config)
            result = connector.get_channel(999)
            assert result is mock_channel


class TestConnectorInteractionRouting:
    async def test_register_slash_command(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            with patch("squadpy.discord.connector.app_commands") as mock_app:
                mock_bot = MagicMock()
                mock_bot.tree = MagicMock()
                mock_commands.Bot.return_value = mock_bot

                connector = DiscordConnector(discord_config)
                handler = AsyncMock()
                connector.register_slash_command(
                    "my_plugin", handler, name="test", description="A test command"
                )
                assert mock_bot.tree.add_command.called

    async def test_register_interaction_handler(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(discord_config)
            handler = AsyncMock()
            connector.register_interaction_handler(
                "my_plugin", "button_click", "claim", handler
            )
            assert "my_plugin:claim" in connector._interaction_handlers

    async def test_namespaced_routing(self, discord_config):
        """Two plugins registering the same custom_id don't collide."""
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(discord_config)
            handler_a = AsyncMock()
            handler_b = AsyncMock()
            connector.register_interaction_handler("plugin_a", "button_click", "submit", handler_a)
            connector.register_interaction_handler("plugin_b", "button_click", "submit", handler_b)
            assert "plugin_a:submit" in connector._interaction_handlers
            assert "plugin_b:submit" in connector._interaction_handlers
            assert connector._interaction_handlers["plugin_a:submit"] is handler_a
            assert connector._interaction_handlers["plugin_b:submit"] is handler_b

    async def test_unregister_plugin_handlers(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(discord_config)
            handler = AsyncMock()
            connector.register_interaction_handler("my_plugin", "button_click", "claim", handler)
            connector.unregister_plugin("my_plugin")
            assert "my_plugin:claim" not in connector._interaction_handlers

    async def test_sync_commands(self, discord_config):
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_bot.tree.sync = AsyncMock()
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(discord_config)
            await connector.sync_commands()
            mock_bot.tree.sync.assert_awaited_once()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_discord_connector.py -v`
Expected: FAIL (module not found)

**Step 3: Implement DiscordConnector**

Create `squadpy/discord/connector.py`:

```python
"""Discord connector — wraps discord.py bot as a core service."""

import asyncio
import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from squadpy.config import DiscordConfig

logger = logging.getLogger("squadpy.discord")


class DiscordConnector:
    """Core Discord service wrapping a discord.py Bot."""

    def __init__(self, config: DiscordConfig):
        self._config = config
        self.guild_id = config.guild_id

        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        self.bot = commands.Bot(
            command_prefix=config.command_prefix,
            intents=intents,
        )
        self._ready = asyncio.Event()
        self._bot_task: asyncio.Task | None = None
        self._interaction_handlers: dict[str, Any] = {}
        self._slash_commands: dict[str, app_commands.Command] = {}
        self.guild: discord.Guild | None = None

        @self.bot.event
        async def on_ready():
            self.guild = self.bot.get_guild(self.guild_id)
            if self.guild:
                logger.info("Discord connected: %s (guild: %s)", self.bot.user, self.guild.name)
            else:
                logger.warning("Discord connected but guild %s not found", self.guild_id)
            self._ready.set()

        @self.bot.event
        async def on_interaction(interaction: discord.Interaction):
            # Only handle component interactions (buttons, selects, modals)
            if interaction.type == discord.InteractionType.component:
                custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
                handler = self._interaction_handlers.get(custom_id)
                if handler:
                    try:
                        await handler(interaction)
                    except Exception:
                        logger.exception("Error in interaction handler for %s", custom_id)
            elif interaction.type == discord.InteractionType.modal_submit:
                custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
                handler = self._interaction_handlers.get(custom_id)
                if handler:
                    try:
                        await handler(interaction)
                    except Exception:
                        logger.exception("Error in modal handler for %s", custom_id)

    async def start(self, token: str) -> None:
        """Start the Discord bot as an asyncio task."""
        self._bot_task = asyncio.create_task(self.bot.start(token))
        logger.info("Discord bot starting...")

    async def wait_until_ready(self) -> None:
        """Wait until the bot is connected and ready."""
        await self._ready.wait()

    async def close(self) -> None:
        """Shut down the Discord bot."""
        await self.bot.close()
        if self._bot_task:
            self._bot_task.cancel()
        logger.info("Discord bot closed")

    # --- Convenience methods ---

    async def send(
        self,
        channel_id: int,
        content: str | None = None,
        embed: discord.Embed | None = None,
        view: discord.ui.View | None = None,
    ) -> discord.Message | None:
        """Send a message to a channel."""
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            logger.warning("Channel %s not found", channel_id)
            return None
        return await channel.send(content=content, embed=embed, view=view)

    async def edit_message(self, message: discord.Message, **kwargs) -> discord.Message:
        """Edit an existing message."""
        return await message.edit(**kwargs)

    async def create_thread(
        self, message: discord.Message, name: str
    ) -> discord.Thread:
        """Create a thread from a message."""
        return await message.create_thread(name=name)

    def get_channel(self, channel_id: int):
        """Get a channel by ID."""
        return self.bot.get_channel(channel_id)

    # --- Interaction routing ---

    def register_slash_command(
        self, plugin_name: str, func, *, name: str, description: str = ""
    ) -> None:
        """Register a slash command for a plugin."""
        cmd = app_commands.Command(
            name=name,
            description=description or name,
            callback=func,
        )
        key = f"{plugin_name}:{name}"
        self._slash_commands[key] = cmd
        self.bot.tree.add_command(cmd, guild=discord.Object(id=self.guild_id))
        logger.debug("Registered slash command /%s for %s", name, plugin_name)

    def register_interaction_handler(
        self,
        plugin_name: str,
        event_type: str,
        custom_id: str | None,
        func,
    ) -> None:
        """Register a Discord interaction handler with namespaced custom_id."""
        if custom_id:
            namespaced_id = f"{plugin_name}:{custom_id}"
        else:
            namespaced_id = f"{plugin_name}:__{event_type}"
        self._interaction_handlers[namespaced_id] = func
        logger.debug("Registered %s handler %s for %s", event_type, namespaced_id, plugin_name)

    def unregister_plugin(self, plugin_name: str) -> None:
        """Remove all handlers for a plugin (used during hot-reload)."""
        prefix = f"{plugin_name}:"
        # Remove interaction handlers
        to_remove = [k for k in self._interaction_handlers if k.startswith(prefix)]
        for k in to_remove:
            del self._interaction_handlers[k]
        # Remove slash commands
        cmd_keys = [k for k in self._slash_commands if k.startswith(prefix)]
        for k in cmd_keys:
            cmd = self._slash_commands.pop(k)
            self.bot.tree.remove_command(cmd.name, guild=discord.Object(id=self.guild_id))
        logger.debug("Unregistered all handlers for %s", plugin_name)

    async def sync_commands(self) -> None:
        """Sync slash commands to the guild."""
        await self.bot.tree.sync(guild=discord.Object(id=self.guild_id))
        logger.info("Synced %d slash commands to guild", len(self._slash_commands))

    def namespace_custom_id(self, plugin_name: str, custom_id: str) -> str:
        """Generate a namespaced custom_id for a plugin's UI component."""
        return f"{plugin_name}:{custom_id}"
```

**Step 4: Update `squadpy/discord/__init__.py`**

```python
from squadpy.discord.connector import DiscordConnector

__all__ = ["DiscordConnector"]
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_discord_connector.py -v`
Expected: All pass

**Step 6: Run full test suite**

Run: `pytest tests/ -v`
Expected: All existing + new tests pass

**Step 7: Commit**

```bash
git add squadpy/discord/ tests/test_discord_connector.py
git commit -m "feat: add DiscordConnector with interaction routing"
```

---

### Task 5: Plugin Loader Discord Integration

**Files:**
- Modify: `squadpy/plugin_loader.py:24-40,127-133` (add discord handler fields + scanning)
- Create: `tests/test_discord_integration.py`

**Step 1: Write failing tests**

Create `tests/test_discord_integration.py`:

```python
"""Tests for Discord integration with plugin loader."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from squadpy.plugin import Plugin, on_event, slash_command, on_discord
from squadpy.plugin_loader import PluginLoader, PluginStatus, LoadedPlugin


class DiscordTestPlugin(Plugin):
    name = "Discord Test"
    requires = ["rcon", "discord"]

    @slash_command(name="hello", description="Say hello")
    async def hello_cmd(self, interaction):
        pass

    @on_discord("button_click", custom_id="click_me")
    async def handle_click(self, interaction):
        pass

    @on_event("test_event")
    async def handle_test(self, event):
        pass


class TestLoadedPluginDiscordFields:
    def test_loaded_plugin_has_slash_commands(self):
        lp = LoadedPlugin(
            name="Test", dir_name="test",
            status=PluginStatus.ENABLED,
            slash_commands=[{"name": "hello"}, "hello_cmd"],
        )
        assert len(lp.slash_commands) > 0

    def test_loaded_plugin_has_discord_handlers(self):
        lp = LoadedPlugin(
            name="Test", dir_name="test",
            status=PluginStatus.ENABLED,
            discord_handlers=[({"event_type": "button_click"}, "handle_click")],
        )
        assert len(lp.discord_handlers) > 0


class TestPluginLoaderDiscordScanning:
    def test_get_slash_commands_from_class(self):
        commands = DiscordTestPlugin.get_slash_commands()
        assert len(commands) == 1
        meta, method_name = commands[0]
        assert meta["name"] == "hello"
        assert method_name == "hello_cmd"

    def test_get_discord_handlers_from_class(self):
        handlers = DiscordTestPlugin.get_discord_handlers()
        assert len(handlers) == 1
        meta, method_name = handlers[0]
        assert meta["event_type"] == "button_click"
        assert meta["custom_id"] == "click_me"


class TestPluginRequiresDiscord:
    async def test_plugin_requiring_discord_fails_without_it(self):
        """Plugin with requires=['discord'] fails when discord service is None."""
        services = {
            "rcon": MagicMock(),
            "discord": None,
            "db": None,
            "server": MagicMock(),
        }
        loader = PluginLoader(
            plugins_dir=Path(__file__).parent / "fixtures" / "plugins",
            config_dir=Path(__file__).parent / "fixtures" / "config" / "plugins",
        )
        # The good_plugin requires ["rcon"] so it should still load
        results = await loader.load_all(services)
        good = next(r for r in results if r.name == "Good Plugin")
        assert good.status == PluginStatus.ENABLED
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_discord_integration.py -v`
Expected: FAIL (LoadedPlugin doesn't accept slash_commands/discord_handlers)

**Step 3: Update LoadedPlugin dataclass**

In `squadpy/plugin_loader.py`, update `LoadedPlugin`:

```python
@dataclass
class LoadedPlugin:
    name: str
    dir_name: str
    status: PluginStatus
    instance: Plugin | None = None
    error: str = ""
    event_handlers: list[tuple[str, str]] = field(default_factory=list)
    periodic_tasks: list[tuple[str, float]] = field(default_factory=list)
    slash_commands: list[tuple[dict, str]] = field(default_factory=list)
    discord_handlers: list[tuple[dict, str]] = field(default_factory=list)
```

In `_load_one`, after line 128, add scanning:

```python
slash_commands = plugin_cls.get_slash_commands()
discord_handlers = plugin_cls.get_discord_handlers()
```

And update the return on line 131-133:

```python
return LoadedPlugin(
    name=name, dir_name=info.dir_name, status=PluginStatus.ENABLED,
    instance=instance, event_handlers=event_handlers, periodic_tasks=periodic_tasks,
    slash_commands=slash_commands, discord_handlers=discord_handlers,
)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_discord_integration.py tests/test_plugin_loader.py -v`
Expected: All pass (existing tests unaffected)

**Step 5: Commit**

```bash
git add squadpy/plugin_loader.py tests/test_discord_integration.py
git commit -m "feat: plugin loader scans for Discord decorators"
```

---

### Task 6: Server Orchestrator Discord Lifecycle

**Files:**
- Modify: `squadpy/server.py` (add Discord startup/shutdown, update summary, wire commands)
- Modify: `tests/test_server.py`

**Step 1: Write failing tests**

Add to `tests/test_server.py`:

```python
from squadpy.config import DiscordConfig


class TestServerDiscordConfig:
    def test_server_config_with_discord(self):
        """ServerConfig accepts discord section."""
        config = ServerConfig(
            rcon={"host": "127.0.0.1", "password": "test"},
            discord={"enabled": True, "token": "tok", "guild_id": 123},
        )
        assert config.discord.enabled is True

    def test_server_config_without_discord(self):
        config = ServerConfig(
            rcon={"host": "127.0.0.1", "password": "test"},
        )
        assert config.discord.enabled is False


class TestStartupSummaryDiscord:
    def test_format_discord_ok(self):
        line = format_service_line("Discord", True, "connected (SquadPy#1234)")
        assert "Discord" in line
        assert "ok" in line
        assert "connected" in line

    def test_format_discord_not_configured(self):
        line = format_service_line("Discord", False, "not configured")
        assert "Discord" in line
        assert "not configured" in line
```

**Step 2: Run tests to verify they pass (these should already pass with config changes)**

Run: `pytest tests/test_server.py -v`
Expected: All pass

**Step 3: Update server.py**

Update imports at top of `squadpy/server.py`:

```python
from squadpy.discord.connector import DiscordConnector
```

In `__init__`, add:

```python
self._discord: DiscordConnector | None = None
```

In `start()`, after log reader block and before plugin loading, add Discord startup:

```python
# Connect Discord (if configured)
discord_ok = False
discord_detail = ""
if self._server_config.discord.enabled:
    try:
        self._discord = DiscordConnector(self._server_config.discord)
        await self._discord.start(self._server_config.discord.token)
        await asyncio.wait_for(self._discord.wait_until_ready(), timeout=30.0)
        discord_ok = True
        bot_name = str(self._discord.bot.user) if self._discord.bot.user else "unknown"
        discord_detail = f"connected ({bot_name})"
    except Exception as e:
        discord_detail = str(e)
        logger.error("Discord connection failed: %s", e)
        self._discord = None
else:
    discord_detail = "not configured"
```

Update services dict:

```python
services = {
    "rcon": self._rcon if rcon_ok else None,
    "log_reader": self._log_parser if log_ok else None,
    "discord": self._discord,
    "db": None,
    "server": self,
}
```

After plugin loading, register Discord handlers and sync commands:

```python
if self._discord:
    for lp in self._loaded_plugins:
        if lp.status == PluginStatus.ENABLED and lp.instance:
            self._register_plugin_discord(lp)
    try:
        await self._discord.sync_commands()
    except Exception as e:
        logger.error("Failed to sync Discord commands: %s", e)
```

Add a new method `_register_plugin_discord`:

```python
def _register_plugin_discord(self, loaded: LoadedPlugin) -> None:
    if not self._discord:
        return
    plugin_name = loaded.dir_name
    for meta, method_name in loaded.slash_commands:
        method = getattr(loaded.instance, method_name)
        self._discord.register_slash_command(
            plugin_name, method, name=meta["name"], description=meta.get("description", ""),
        )
    for meta, method_name in loaded.discord_handlers:
        method = getattr(loaded.instance, method_name)
        self._discord.register_interaction_handler(
            plugin_name, meta["event_type"], meta.get("custom_id"), method,
        )
```

Update `_print_summary` signature and body to accept discord params:

```python
def _print_summary(self, rcon_ok, rcon_detail, log_ok=False, log_detail="", discord_ok=False, discord_detail=""):
```

Replace the Discord line:

```python
format_service_line("Discord", discord_ok, discord_detail),
```

Update the `_print_summary` call in `start()`:

```python
self._print_summary(rcon_ok, rcon_detail, log_ok, log_detail, discord_ok, discord_detail)
```

In `stop()`, after plugin disable loop and before RCON close:

```python
if self._discord:
    await self._discord.close()
```

Update `reload_plugin` services dict to include discord:

```python
services = {
    "rcon": self._rcon,
    "log_reader": self._log_parser,
    "discord": self._discord,
    "db": None,
    "server": self,
}
```

And in reload_plugin, after unsubscribing events, add Discord deregister:

```python
if self._discord:
    self._discord.unregister_plugin(target.dir_name)
```

And after re-registering events/periodic on successful reload:

```python
if self._discord:
    self._register_plugin_discord(new_loaded)
    try:
        await self._discord.sync_commands()
    except Exception:
        logger.exception("Failed to sync commands after reload")
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v`
Expected: All pass

**Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All pass

**Step 6: Commit**

```bash
git add squadpy/server.py tests/test_server.py
git commit -m "feat: integrate Discord into server lifecycle"
```

---

### Task 7: Built-in PluginManager Plugin

**Files:**
- Create: `plugins/plugin_manager/plugin.py`
- Create: `config/plugins/plugin_manager.toml.example`
- Create: `tests/test_plugin_manager.py`

**Step 1: Write failing tests**

Create `tests/test_plugin_manager.py`:

```python
"""Tests for the built-in PluginManager plugin."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from squadpy.plugin import slash_command, on_event


class TestPluginManagerImport:
    def test_can_import_plugin(self):
        """PluginManager plugin can be imported."""
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "plugin_manager",
            Path(__file__).parent.parent / "plugins" / "plugin_manager" / "plugin.py",
        )
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert hasattr(module, "PluginManager")

    def test_plugin_has_required_attributes(self):
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "plugin_manager",
            Path(__file__).parent.parent / "plugins" / "plugin_manager" / "plugin.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls = module.PluginManager

        assert cls.name == "Plugin Manager"
        assert "rcon" in cls.requires
        assert "discord" in cls.requires

    def test_plugin_has_slash_commands(self):
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "plugin_manager",
            Path(__file__).parent.parent / "plugins" / "plugin_manager" / "plugin.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls = module.PluginManager

        commands = cls.get_slash_commands()
        names = {meta["name"] for meta, _ in commands}
        assert "status" in names
        assert "plugins" in names
        assert "reload" in names


class TestPluginManagerHandlers:
    @pytest.fixture
    def plugin(self):
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "plugin_manager",
            Path(__file__).parent.parent / "plugins" / "plugin_manager" / "plugin.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        mock_rcon = MagicMock()
        mock_discord = MagicMock()
        mock_server = MagicMock()
        mock_server.version = "0.1.0"
        mock_server.running = True
        mock_server._loaded_plugins = []

        return module.PluginManager(
            rcon=mock_rcon,
            discord=mock_discord,
            config={"admin_role_id": 123456},
            server=mock_server,
        )

    async def test_status_command_responds(self, plugin):
        """The /status command sends a response."""
        interaction = AsyncMock()
        interaction.response = AsyncMock()
        await plugin.status_cmd(interaction)
        interaction.response.send_message.assert_awaited_once()

    async def test_plugins_command_responds(self, plugin):
        """The /plugins command sends a response."""
        interaction = AsyncMock()
        interaction.response = AsyncMock()
        await plugin.plugins_cmd(interaction)
        interaction.response.send_message.assert_awaited_once()

    async def test_reload_command_calls_server(self, plugin):
        """The /reload command calls server.reload_plugin()."""
        interaction = AsyncMock()
        interaction.response = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.roles = [MagicMock(id=123456)]
        plugin.server.reload_plugin = AsyncMock(return_value=(True, ""))
        await plugin.reload_cmd(interaction, plugin_name="test_plugin")
        plugin.server.reload_plugin.assert_awaited_once_with("test_plugin")

    async def test_reload_without_admin_role_rejected(self, plugin):
        """The /reload command rejects users without admin role."""
        interaction = AsyncMock()
        interaction.response = AsyncMock()
        interaction.user = MagicMock()
        interaction.user.roles = [MagicMock(id=999999)]  # Wrong role
        await plugin.reload_cmd(interaction, plugin_name="test_plugin")
        # Should respond with permission error, not call reload
        plugin.server.reload_plugin.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugin_manager.py -v`
Expected: FAIL (plugin_manager module not found)

**Step 3: Create PluginManager plugin**

Create `plugins/plugin_manager/__init__.py` (empty file).

Create `plugins/plugin_manager/plugin.py`:

```python
"""Built-in Plugin Manager — /status, /plugins, /reload slash commands."""

import datetime

from squadpy.plugin import Plugin, slash_command


class PluginManager(Plugin):
    name = "Plugin Manager"
    description = "Server management slash commands"
    requires = ["rcon", "discord"]

    async def on_enable(self):
        self._start_time = datetime.datetime.now()

    @slash_command(name="status", description="Show server status")
    async def status_cmd(self, interaction):
        uptime = datetime.datetime.now() - self._start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        lines = [
            f"**SquadPy v{self.server.version}**",
            f"Uptime: {hours}h {minutes}m {seconds}s",
        ]
        await interaction.response.send_message("\n".join(lines))

    @slash_command(name="plugins", description="List loaded plugins")
    async def plugins_cmd(self, interaction):
        plugins = self.server._loaded_plugins
        if not plugins:
            await interaction.response.send_message("No plugins loaded.")
            return

        lines = []
        for lp in plugins:
            status = lp.status.value
            lines.append(f"**{lp.name}** — {status}")
            if lp.error:
                lines.append(f"  Error: {lp.error}")

        await interaction.response.send_message("\n".join(lines))

    @slash_command(name="reload", description="Reload a plugin")
    async def reload_cmd(self, interaction, plugin_name: str):
        admin_role_id = self.config.get("admin_role_id", 0)
        user_role_ids = {role.id for role in interaction.user.roles}

        if admin_role_id and admin_role_id not in user_role_ids:
            await interaction.response.send_message(
                "You do not have permission to reload plugins.", ephemeral=True,
            )
            return

        success, error = await self.server.reload_plugin(plugin_name)
        if success:
            await interaction.response.send_message(f"Plugin `{plugin_name}` reloaded.")
        else:
            await interaction.response.send_message(f"Failed to reload `{plugin_name}`: {error}")
```

**Step 4: Create config example**

Create `config/plugins/plugin_manager.toml.example`:

```toml
enabled = true

[settings]
admin_role_id = 0  # Discord role ID required for /reload (0 = no restriction)
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_plugin_manager.py -v`
Expected: All pass

**Step 6: Run full test suite**

Run: `pytest tests/ -v`
Expected: All pass

**Step 7: Commit**

```bash
git add plugins/plugin_manager/ config/plugins/plugin_manager.toml.example tests/test_plugin_manager.py
git commit -m "feat: add built-in PluginManager plugin with /status, /plugins, /reload"
```

---

### Task 8: Final Integration Test & Cleanup

**Files:**
- Modify: `tests/test_discord_integration.py` (add full integration tests)
- Run full suite

**Step 1: Add integration tests for hot-reload with Discord**

Add to `tests/test_discord_integration.py`:

```python
class TestHotReloadDiscord:
    async def test_reload_deregisters_old_discord_handlers(self):
        """When a plugin is reloaded, old Discord handlers are removed."""
        from squadpy.discord.connector import DiscordConnector
        from squadpy.config import DiscordConfig
        from unittest.mock import patch

        config = DiscordConfig(enabled=True, token="tok", guild_id=123)
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_bot.tree = MagicMock()
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(config)

            # Register some handlers
            handler = AsyncMock()
            connector.register_interaction_handler("my_plugin", "button_click", "btn", handler)
            assert "my_plugin:btn" in connector._interaction_handlers

            # Unregister (simulating reload)
            connector.unregister_plugin("my_plugin")
            assert "my_plugin:btn" not in connector._interaction_handlers

    async def test_reload_does_not_affect_other_plugins(self):
        """Reloading one plugin doesn't touch another's handlers."""
        from squadpy.discord.connector import DiscordConnector
        from squadpy.config import DiscordConfig
        from unittest.mock import patch

        config = DiscordConfig(enabled=True, token="tok", guild_id=123)
        with patch("squadpy.discord.connector.commands") as mock_commands:
            mock_bot = MagicMock()
            mock_bot.tree = MagicMock()
            mock_commands.Bot.return_value = mock_bot

            connector = DiscordConnector(config)

            handler_a = AsyncMock()
            handler_b = AsyncMock()
            connector.register_interaction_handler("plugin_a", "button_click", "btn", handler_a)
            connector.register_interaction_handler("plugin_b", "button_click", "btn", handler_b)

            connector.unregister_plugin("plugin_a")
            assert "plugin_a:btn" not in connector._interaction_handlers
            assert "plugin_b:btn" in connector._interaction_handlers
```

**Step 2: Run full test suite**

Run: `pytest tests/ -v`
Expected: All pass

**Step 3: Commit**

```bash
git add tests/test_discord_integration.py
git commit -m "test: add hot-reload Discord integration tests"
```

**Step 4: Run final verification**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass, zero failures
