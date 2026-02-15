"""Tests for plugin discovery, loading, and error isolation."""

import builtins
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from squadpy.plugin_loader import PluginLoader, PluginStatus

FIXTURES = Path(__file__).parent / "fixtures"


class TestPluginDiscovery:
    def test_discover_plugins(self):
        loader = PluginLoader(
            plugins_dir=FIXTURES / "plugins",
            config_dir=FIXTURES / "config" / "plugins",
        )
        discovered = loader.discover()
        names = {d.dir_name for d in discovered}
        assert "good_plugin" in names
        assert "bad_plugin" in names
        assert "disabled_plugin" in names

    def test_discover_reads_config(self):
        loader = PluginLoader(
            plugins_dir=FIXTURES / "plugins",
            config_dir=FIXTURES / "config" / "plugins",
        )
        discovered = loader.discover()
        good = next(d for d in discovered if d.dir_name == "good_plugin")
        assert good.config["settings"]["test_value"] == 42
        assert good.enabled is True

    def test_discover_disabled_plugin(self):
        loader = PluginLoader(
            plugins_dir=FIXTURES / "plugins",
            config_dir=FIXTURES / "config" / "plugins",
        )
        discovered = loader.discover()
        disabled = next(d for d in discovered if d.dir_name == "disabled_plugin")
        assert disabled.enabled is False

    def test_discover_missing_config_is_disabled_by_default(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugin_dir = plugins_dir / "sample_plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(
            "from squadpy.plugin import Plugin\n\nclass SamplePlugin(Plugin):\n    name = \"Sample Plugin\"\n",
            encoding="utf-8",
        )
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        loader = PluginLoader(plugins_dir=plugins_dir, config_dir=config_dir)

        discovered = loader.discover()
        assert len(discovered) == 1
        assert discovered[0].enabled is False

    def test_discover_missing_config_can_be_auto_enabled_with_flag(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugin_dir = plugins_dir / "sample_plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(
            "from squadpy.plugin import Plugin\n\nclass SamplePlugin(Plugin):\n    name = \"Sample Plugin\"\n",
            encoding="utf-8",
        )
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        loader = PluginLoader(
            plugins_dir=plugins_dir,
            config_dir=config_dir,
            auto_enable_missing_configs=True,
        )

        discovered = loader.discover()
        assert len(discovered) == 1
        assert discovered[0].enabled is True


class TestPluginLoading:
    @pytest.fixture
    def services(self):
        return {
            "rcon": MagicMock(),
            "discord": None,
            "db": None,
            "layers": MagicMock(),
            "server": MagicMock(),
        }

    async def test_load_good_plugin(self, services):
        loader = PluginLoader(
            plugins_dir=FIXTURES / "plugins",
            config_dir=FIXTURES / "config" / "plugins",
        )
        results = await loader.load_all(services)
        good = next(r for r in results if r.name == "Good Plugin")
        assert good.status == PluginStatus.ENABLED
        assert good.instance is not None

    async def test_bad_plugin_fails_gracefully(self, services):
        loader = PluginLoader(
            plugins_dir=FIXTURES / "plugins",
            config_dir=FIXTURES / "config" / "plugins",
        )
        results = await loader.load_all(services)
        bad = next(r for r in results if r.name == "Bad Plugin")
        assert bad.status == PluginStatus.FAILED
        assert "Intentional failure" in bad.error

    async def test_disabled_plugin_skipped(self, services):
        loader = PluginLoader(
            plugins_dir=FIXTURES / "plugins",
            config_dir=FIXTURES / "config" / "plugins",
        )
        results = await loader.load_all(services)
        disabled = next(r for r in results if r.name == "Disabled Plugin")
        assert disabled.status == PluginStatus.DISABLED

    async def test_missing_requirement_fails(self, services):
        services["rcon"] = None
        loader = PluginLoader(
            plugins_dir=FIXTURES / "plugins",
            config_dir=FIXTURES / "config" / "plugins",
        )
        results = await loader.load_all(services)
        good = next(r for r in results if r.name == "Good Plugin")
        assert good.status == PluginStatus.FAILED
        assert "rcon" in good.error.lower()

    async def test_good_plugin_event_handlers_registered(self, services):
        loader = PluginLoader(
            plugins_dir=FIXTURES / "plugins",
            config_dir=FIXTURES / "config" / "plugins",
        )
        results = await loader.load_all(services)
        good = next(r for r in results if r.name == "Good Plugin")
        assert len(good.event_handlers) > 0

    async def test_shared_layers_service_passed_to_plugin_instance(self, services):
        loader = PluginLoader(
            plugins_dir=FIXTURES / "plugins",
            config_dir=FIXTURES / "config" / "plugins",
        )
        results = await loader.load_all(services)
        good = next(r for r in results if r.name == "Good Plugin")
        assert good.instance is not None
        assert good.instance.layers is services["layers"]

    async def test_reuses_cached_module_for_same_plugin_path(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugin_dir = plugins_dir / "counter_plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(
            """
import builtins
from squadpy.plugin import Plugin

counter_name = "_squadpy_counter_plugin_imports"
setattr(builtins, counter_name, getattr(builtins, counter_name, 0) + 1)

class CounterPlugin(Plugin):
    name = "Counter Plugin"
""".strip(),
            encoding="utf-8",
        )

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "counter_plugin.toml").write_text("enabled = true\n", encoding="utf-8")

        module_name = "squadpy_plugin_counter_plugin"
        counter_name = "_squadpy_counter_plugin_imports"

        sys.modules.pop(module_name, None)
        if hasattr(builtins, counter_name):
            delattr(builtins, counter_name)

        services = {
            "rcon": MagicMock(),
            "discord": None,
            "db": None,
            "layers": MagicMock(),
            "server": MagicMock(),
        }
        loader_a = PluginLoader(plugins_dir=plugins_dir, config_dir=config_dir)
        loader_b = PluginLoader(plugins_dir=plugins_dir, config_dir=config_dir)

        try:
            first = await loader_a.load_all(services)
            second = await loader_b.load_all(services)

            assert first[0].status == PluginStatus.ENABLED
            assert second[0].status == PluginStatus.ENABLED
            assert getattr(builtins, counter_name, 0) == 1
        finally:
            sys.modules.pop(module_name, None)
            if hasattr(builtins, counter_name):
                delattr(builtins, counter_name)
