"""Tests for EndMatchVote plugin."""

import importlib.util
from importlib.abc import Loader
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from squadpy.events.types import ChatMessage
from squadpy.rcon.types import RconPlayer


def _load_plugin_class():
    spec = importlib.util.spec_from_file_location(
        "end_match_vote",
        Path(__file__).parent.parent / "plugins" / "end_match_vote" / "plugin.py",
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.EndMatchVote


def _chat(message: str, *, steam_id: str = "steam_a", channel: str = "ChatAll") -> ChatMessage:
    return ChatMessage(
        player_name="Player",
        steam_id=steam_id,
        eos_id="",
        channel=channel,
        message=message,
    )


def _players(count: int) -> list[RconPlayer]:
    players: list[RconPlayer] = []
    for idx in range(count):
        sid = f"steam_{idx}"
        players.append(
            RconPlayer(
                id=idx,
                steam_id=sid,
                eos_id="",
                name=f"Player_{sid}",
                team_id=1 if idx % 2 == 0 else 2,
                squad_id=1,
                is_leader=False,
                role="Rifleman",
            )
        )
    return players


class TestEndMatchVote:
    @pytest.fixture
    async def plugin(self):
        cls = _load_plugin_class()
        instance = cls(
            rcon=AsyncMock(),
            config={
                "command": "!endmatch",
                "allowed_channels": ["ChatAll"],
                "min_players": 1,
                "min_votes": 2,
                "vote_threshold_ratio": 0.5,
                "vote_window_seconds": 120,
                "cooldown_seconds": 300,
                "announce_progress": True,
                "progress_message": "Progress {votes}/{required} ({players})",
                "vote_recorded_message": "Recorded {votes}/{required}",
                "already_voted_message": "Already voted",
                "not_enough_players_message": "Need {min_players}",
                "cooldown_message": "Cooldown {remaining}s",
                "success_message": "Passed {votes}/{required}",
            },
        )
        await instance.on_enable()
        return instance

    async def test_vote_threshold_executes_end_match(self, plugin):
        """Match ends when votes reach computed required threshold."""
        plugin.rcon.list_players.return_value = _players(3)

        await plugin.handle_chat(_chat("!endmatch", steam_id="steam_a"))
        await plugin.handle_chat(_chat("!endmatch", steam_id="steam_b"))

        plugin.rcon.execute.assert_awaited_once_with("AdminEndMatch")
        assert plugin.rcon.broadcast.await_count == 2
        assert plugin.rcon.warn.await_count == 2

    async def test_duplicate_vote_is_rejected(self, plugin):
        """Same player cannot vote twice in a window."""
        plugin.rcon.list_players.return_value = _players(4)

        await plugin.handle_chat(_chat("!endmatch", steam_id="steam_a"))
        await plugin.handle_chat(_chat("!endmatch", steam_id="steam_a"))

        plugin.rcon.execute.assert_not_awaited()
        assert len(plugin._votes) == 1
        plugin.rcon.warn.assert_any_await("steam_a", "Already voted")

    async def test_vote_window_expiry_resets_previous_votes(self, plugin):
        """Votes expire after configured window and do not carry forward."""
        plugin.rcon.list_players.return_value = _players(4)
        plugin._test_now = 1000.0
        plugin._now = lambda: plugin._test_now

        await plugin.handle_chat(_chat("!endmatch", steam_id="steam_a"))
        plugin._test_now = 1131.0  # after vote_window_seconds=120
        await plugin.handle_chat(_chat("!endmatch", steam_id="steam_b"))

        plugin.rcon.execute.assert_not_awaited()
        assert plugin._votes == {"steam_b"}

    async def test_cooldown_blocks_new_vote_after_success(self, plugin):
        """After a successful vote, new vote requests are blocked until cooldown."""
        plugin.config["min_votes"] = 1
        plugin.config["vote_threshold_ratio"] = 0.1
        plugin.rcon.list_players.return_value = _players(2)
        plugin._test_now = 2000.0
        plugin._now = lambda: plugin._test_now

        await plugin.handle_chat(_chat("!endmatch", steam_id="steam_a"))
        plugin._test_now = 2030.0
        await plugin.handle_chat(_chat("!endmatch", steam_id="steam_b"))

        assert plugin.rcon.execute.await_count == 1
        plugin.rcon.warn.assert_any_await("steam_b", "Cooldown 270s")

    async def test_min_players_guard_blocks_vote(self, plugin):
        """Vote command is rejected when population is below min_players."""
        plugin.config["min_players"] = 5
        plugin.rcon.list_players.return_value = _players(3)

        await plugin.handle_chat(_chat("!endmatch", steam_id="steam_a"))

        plugin.rcon.execute.assert_not_awaited()
        plugin.rcon.warn.assert_awaited_once_with("steam_a", "Need 5")

    async def test_new_game_resets_vote_state(self, plugin):
        """New game clears open vote session state."""
        plugin._votes = {"steam_a", "steam_b"}
        plugin._window_started_at = 100.0
        await plugin.handle_new_game(object())
        assert plugin._votes == set()
        assert plugin._window_started_at is None

    async def test_plugin_attributes_and_handlers(self):
        cls = _load_plugin_class()
        assert cls.name == "End Match Vote"
        assert "rcon" in cls.requires

        handlers = cls.get_event_handlers()
        assert ("chat_message", "handle_chat") in handlers
        assert ("new_game", "handle_new_game") in handlers
