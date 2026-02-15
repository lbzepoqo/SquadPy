"""Local replay harness for plugin development loops."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from squadpy.events.emitter import EventBus
from squadpy.events.types import BaseEvent
from squadpy.layers import LayerCatalogService
from squadpy.log_parser import LogParser, LogReader
from squadpy.plugin_loader import LoadedPlugin, PluginLoader, PluginStatus
from squadpy.rcon.client import parse_players, parse_squads
from squadpy.rcon.types import RconPlayer, RconSquad


@dataclass(frozen=True)
class SimulationResult:
    """Summary of one local replay run."""

    events: list[str]
    event_counts: dict[str, int]
    rcon_commands: list[str]
    plugins: list[dict[str, str]]
    runtime_errors: list[dict[str, str]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "events": self.events,
            "event_counts": self.event_counts,
            "rcon_commands": self.rcon_commands,
            "plugins": self.plugins,
            "runtime_errors": self.runtime_errors,
        }


class _RecordingEventBus(EventBus):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []

    async def emit(self, event: BaseEvent) -> None:
        self.events.append(event.event_name)
        await super().emit(event)


class FixtureLogReader(LogReader):
    """In-memory log reader for deterministic replay."""

    def __init__(self, lines: list[str]):
        self._lines = lines
        self._running = False

    @classmethod
    def from_file(cls, path: Path) -> "FixtureLogReader":
        lines = path.read_text(encoding="utf-8").splitlines()
        return cls(lines)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def tail(self):
        for line in self._lines:
            if not self._running:
                break
            if line.strip():
                yield line


class FixtureRconClient:
    """Deterministic RCON replay client backed by fixture responses."""

    def __init__(self, responses: dict[str, list[str]] | None = None):
        self._responses = {command: list(items) for command, items in (responses or {}).items()}
        self._indices: dict[str, int] = {}
        self.executed_commands: list[str] = []

    @classmethod
    def from_fixture_file(cls, path: Path) -> "FixtureRconClient":
        return cls(load_rcon_fixture(path))

    async def execute(self, command: str) -> str:
        normalized_command = str(command).strip()
        if not normalized_command:
            raise ValueError("command must be non-empty")
        self.executed_commands.append(normalized_command)

        values = self._responses.get(normalized_command)
        if not values:
            raise RuntimeError(f"No fixture response configured for command: {normalized_command}")

        index = self._indices.get(normalized_command, 0)
        if index < len(values):
            response = values[index]
            self._indices[normalized_command] = index + 1
            return response
        return values[-1]

    async def list_players(self) -> list[RconPlayer]:
        response = await self.execute("ListPlayers")
        return parse_players(response)

    async def list_squads(self) -> list[RconSquad]:
        response = await self.execute("ListSquads")
        return parse_squads(response)

    async def broadcast(self, message: str) -> str:
        return await self.execute(f"AdminBroadcast {message}")

    async def warn(self, player_id: str, message: str) -> str:
        return await self.execute(f'AdminWarn "{player_id}" {message}')

    async def kick(self, player_id: str, reason: str) -> str:
        return await self.execute(f'AdminKick "{player_id}" {reason}')

    async def ban(self, player_id: str, duration: str | int, reason: str) -> str:
        return await self.execute(f'AdminBan "{player_id}" "{duration}" {reason}')


def load_rcon_fixture(path: Path) -> dict[str, list[str]]:
    """Load replay responses from a JSON fixture file."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    responses: dict[str, list[str]] = {}

    if isinstance(raw, dict) and isinstance(raw.get("responses"), list):
        entries = raw["responses"]
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("responses entries must be objects")
            command = str(entry.get("command", "")).strip()
            if not command:
                raise ValueError("responses entry is missing command")

            response: str
            if "response_file" in entry:
                response_file = Path(str(entry["response_file"]))
                if not response_file.is_absolute():
                    response_file = path.parent / response_file
                response = response_file.read_text(encoding="utf-8")
            elif "response" in entry:
                response = str(entry["response"])
            else:
                raise ValueError("responses entry must include response or response_file")

            responses.setdefault(command, []).append(response)
        return responses

    if isinstance(raw, dict):
        for command, value in raw.items():
            normalized_command = str(command).strip()
            if not normalized_command:
                raise ValueError("fixture command keys must be non-empty")
            if isinstance(value, list):
                responses[normalized_command] = [str(item) for item in value]
            else:
                responses[normalized_command] = [str(value)]
        return responses

    raise ValueError("rcon fixture must be a JSON object")


class LocalSimulationHarness:
    """Replay log + RCON fixtures through plugins for local development loops."""

    def __init__(
        self,
        *,
        log_reader: FixtureLogReader,
        rcon_client: FixtureRconClient | None,
        plugins_dir: Path,
        plugin_config_dir: Path,
        plugin_names: list[str] | None = None,
        run_periodic_once: bool = True,
    ):
        self._log_reader = log_reader
        self._rcon = rcon_client
        self._plugins_dir = plugins_dir
        self._plugin_config_dir = plugin_config_dir
        self._plugin_names = {name.strip() for name in (plugin_names or []) if name.strip()}
        self._run_periodic_once = run_periodic_once
        self._event_bus = _RecordingEventBus()
        self._runtime_errors: list[dict[str, str]] = []

    @classmethod
    def from_fixture_files(
        cls,
        *,
        log_fixture: Path,
        rcon_fixture: Path | None,
        plugins_dir: Path,
        plugin_config_dir: Path,
        plugin_names: list[str] | None = None,
        run_periodic_once: bool = True,
    ) -> "LocalSimulationHarness":
        log_reader = FixtureLogReader.from_file(log_fixture)
        rcon = FixtureRconClient.from_fixture_file(rcon_fixture) if rcon_fixture else None
        return cls(
            log_reader=log_reader,
            rcon_client=rcon,
            plugins_dir=plugins_dir,
            plugin_config_dir=plugin_config_dir,
            plugin_names=plugin_names,
            run_periodic_once=run_periodic_once,
        )

    async def run(self) -> SimulationResult:
        layers = LayerCatalogService()
        loader = PluginLoader(
            plugins_dir=self._plugins_dir,
            config_dir=self._plugin_config_dir,
        )
        loaded_plugins = await self._load_plugins(loader, layers=layers)
        self._register_events(loaded_plugins)

        parser = LogParser(
            reader=self._log_reader,
            event_bus=self._event_bus,
            rcon_client=cast(Any, self._rcon),
        )
        await parser.run()

        if self._run_periodic_once:
            await self._run_periodic_once_for_plugins(loaded_plugins)

        await self._disable_plugins(loaded_plugins)

        event_counts = dict(Counter(self._event_bus.events))
        return SimulationResult(
            events=list(self._event_bus.events),
            event_counts=event_counts,
            rcon_commands=list(self._rcon.executed_commands if self._rcon else []),
            plugins=[
                {
                    "name": plugin.name,
                    "dir_name": plugin.dir_name,
                    "status": plugin.status.value,
                    "error": plugin.error,
                }
                for plugin in loaded_plugins
            ],
            runtime_errors=list(self._runtime_errors),
        )

    async def _load_plugins(
        self,
        loader: PluginLoader,
        *,
        layers: LayerCatalogService,
    ) -> list[LoadedPlugin]:
        discovered = loader.discover()
        if self._plugin_names:
            discovered_names = {item.dir_name for item in discovered}
            missing = sorted(self._plugin_names - discovered_names)
            if missing:
                names = ", ".join(missing)
                raise ValueError(f"Requested plugins not found: {names}")
            discovered = [item for item in discovered if item.dir_name in self._plugin_names]

        services = {
            "rcon": self._rcon,
            "log_reader": self._log_reader,
            "discord": None,
            "db": None,
            "layers": layers,
            "server": self,
        }

        results: list[LoadedPlugin] = []
        for info in discovered:
            loaded = await loader._load_one(info, services)
            results.append(loaded)
        return results

    def _register_events(self, loaded_plugins: list[LoadedPlugin]) -> None:
        for plugin in loaded_plugins:
            if plugin.status != PluginStatus.ENABLED or plugin.instance is None:
                continue
            for event_name, method_name in plugin.event_handlers:
                handler = getattr(plugin.instance, method_name)
                self._event_bus.subscribe(event_name, handler)

    async def _run_periodic_once_for_plugins(self, loaded_plugins: list[LoadedPlugin]) -> None:
        for plugin in loaded_plugins:
            if plugin.status != PluginStatus.ENABLED or plugin.instance is None:
                continue
            for method_name, _interval in plugin.periodic_tasks:
                method = getattr(plugin.instance, method_name)
                try:
                    await method()
                except Exception as exc:
                    self._runtime_errors.append(
                        {
                            "plugin": plugin.name,
                            "source": f"periodic:{method_name}",
                            "detail": str(exc),
                        }
                    )

    async def _disable_plugins(self, loaded_plugins: list[LoadedPlugin]) -> None:
        for plugin in loaded_plugins:
            if plugin.status == PluginStatus.ENABLED and plugin.instance is not None:
                try:
                    await plugin.instance.on_disable()
                except Exception as exc:
                    self._runtime_errors.append(
                        {
                            "plugin": plugin.name,
                            "source": "on_disable",
                            "detail": str(exc),
                        }
                    )
