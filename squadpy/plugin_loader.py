"""Plugin discovery, loading, and lifecycle management."""

import importlib
import importlib.util
import logging
import sys
import tomllib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from squadpy.plugin import Plugin

logger = logging.getLogger("squadpy.plugins")


class PluginStatus(Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    FAILED = "failed"


@dataclass
class DiscoveredPlugin:
    dir_name: str
    module_path: Path
    config: dict
    enabled: bool


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


class PluginLoader:
    def __init__(self, plugins_dir: Path, config_dir: Path):
        self.plugins_dir = plugins_dir
        self.config_dir = config_dir

    def discover(self) -> list[DiscoveredPlugin]:
        discovered = []
        if not self.plugins_dir.exists():
            return discovered

        for plugin_dir in sorted(self.plugins_dir.iterdir()):
            if not plugin_dir.is_dir():
                continue
            module_path = plugin_dir / "plugin.py"
            if not module_path.exists():
                continue

            config_file = self.config_dir / f"{plugin_dir.name}.toml"
            config = {}
            enabled = True
            if config_file.exists():
                with open(config_file, "rb") as f:
                    config = tomllib.load(f)
                enabled = config.get("enabled", True)

            discovered.append(DiscoveredPlugin(
                dir_name=plugin_dir.name,
                module_path=module_path,
                config=config,
                enabled=enabled,
            ))

        return discovered

    async def load_all(self, services: dict[str, Any]) -> list[LoadedPlugin]:
        discovered = self.discover()
        results = []
        for plugin_info in discovered:
            result = await self._load_one(plugin_info, services)
            results.append(result)
        return results

    async def _load_one(self, info: DiscoveredPlugin, services: dict[str, Any]) -> LoadedPlugin:
        if not info.enabled:
            try:
                plugin_cls = self._import_plugin_class(info)
                name = plugin_cls.name or info.dir_name
            except Exception:
                name = info.dir_name
            return LoadedPlugin(name=name, dir_name=info.dir_name, status=PluginStatus.DISABLED)

        try:
            plugin_cls = self._import_plugin_class(info)
        except Exception as e:
            logger.error("Failed to import plugin %s: %s", info.dir_name, e)
            return LoadedPlugin(name=info.dir_name, dir_name=info.dir_name, status=PluginStatus.FAILED, error=str(e))

        name = plugin_cls.name or info.dir_name

        for req in plugin_cls.requires:
            if services.get(req) is None:
                error = f"Requires {req} but it is not configured"
                logger.error("Plugin %s: %s", name, error)
                return LoadedPlugin(name=name, dir_name=info.dir_name, status=PluginStatus.FAILED, error=error)

        try:
            settings = info.config.get("settings", {})
            instance = plugin_cls(
                rcon=services.get("rcon"),
                discord=services.get("discord"),
                db=services.get("db"),
                layers=services.get("layers"),
                config=settings,
                server=services.get("server"),
            )
        except Exception as e:
            logger.error("Failed to instantiate plugin %s: %s", name, e)
            return LoadedPlugin(name=name, dir_name=info.dir_name, status=PluginStatus.FAILED, error=str(e))

        try:
            await instance.on_enable()
        except Exception as e:
            logger.error("Plugin %s failed on enable: %s", name, e)
            return LoadedPlugin(name=name, dir_name=info.dir_name, status=PluginStatus.FAILED, error=str(e))

        event_handlers = plugin_cls.get_event_handlers()
        periodic_tasks = plugin_cls.get_periodic_tasks()
        slash_commands = plugin_cls.get_slash_commands()
        discord_handlers = plugin_cls.get_discord_handlers()

        logger.info("Plugin %s enabled", name)
        return LoadedPlugin(
            name=name, dir_name=info.dir_name, status=PluginStatus.ENABLED,
            instance=instance, event_handlers=event_handlers, periodic_tasks=periodic_tasks,
            slash_commands=slash_commands, discord_handlers=discord_handlers,
        )

    def _import_plugin_class(self, info: DiscoveredPlugin) -> type[Plugin]:
        module_name = f"squadpy_plugin_{info.dir_name}"
        module_path = info.module_path.resolve()
        cached_module = sys.modules.get(module_name)
        if cached_module is not None:
            cached_file = getattr(cached_module, "__file__", None)
            if cached_file is not None and Path(cached_file).resolve() == module_path:
                return self._find_plugin_class(cached_module, info.module_path)

        spec = importlib.util.spec_from_file_location(module_name, info.module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {info.module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        return self._find_plugin_class(module, info.module_path)

    @staticmethod
    def _find_plugin_class(module: Any, module_path: Path) -> type[Plugin]:
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, Plugin) and attr is not Plugin:
                return attr

        raise ImportError(f"No Plugin subclass found in {module_path}")

    @staticmethod
    def clear_module_cache(dir_name: str) -> None:
        sys.modules.pop(f"squadpy_plugin_{dir_name}", None)
