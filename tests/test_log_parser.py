"""Integration tests for the LogParser — feeds lines, verifies events."""

import asyncio

import pytest

from squadpy.events.emitter import EventBus
from squadpy.events.types import (
    BaseEvent, PlayerConnected, JoinSucceeded, PlayerDamaged,
    PlayerWounded, PlayerDied, RoundEnded, ServerTickRate,
)
from squadpy.log_parser.parser import LogParser
from squadpy.log_parser.reader import LogReader


class MockLogReader(LogReader):
    """Feeds pre-set lines to the parser."""

    def __init__(self, lines: list[str]):
        self._lines = lines
        self._running = False

    async def start(self):
        self._running = True

    async def stop(self):
        self._running = False

    async def tail(self):
        for line in self._lines:
            if not self._running:
                break
            yield line


class TestLogParser:
    async def test_emits_player_connected(self):
        lines = [
            '[2026.02.06-15.02.11:098][401]LogSquad: PostLogin: NewPlayer: BP_PlayerController_C /Game/Maps/Sumari/Gameplay_Layers/Sumari_Seed_v1.Sumari_Seed_v1:PersistentLevel.BP_PlayerController_C_2147476661 (IP: 174.110.37.249 | Online IDs: EOS: 000250f5e359453bb9ad313db051f19e steam: 76561198376713392)',
        ]
        events = await self._run_parser(lines)
        assert len(events) == 1
        assert isinstance(events[0], PlayerConnected)

    async def test_connect_then_join(self):
        lines = [
            '[2026.02.06-15.02.11:098][401]LogSquad: PostLogin: NewPlayer: BP_PlayerController_C /Game/Maps/Sumari/Gameplay_Layers/Sumari_Seed_v1.Sumari_Seed_v1:PersistentLevel.BP_PlayerController_C_2147476661 (IP: 174.110.37.249 | Online IDs: EOS: 000250f5e359453bb9ad313db051f19e steam: 76561198376713392)',
            '[2026.02.06-15.02.11:099][401]LogNet: Join succeeded: PAPA_ \u039e_TAN',
        ]
        events = await self._run_parser(lines)
        assert len(events) == 2
        assert isinstance(events[0], PlayerConnected)
        assert isinstance(events[1], JoinSucceeded)
        assert events[1].player.eos_id == "000250f5e359453bb9ad313db051f19e"

    async def test_damage_wound_die_sequence(self):
        lines = [
            '[2026.02.06-16.57.06:079][ 49]LogSquad: Player: enwez ActualDamage=58.952755 from  lord billybean (Online IDs: EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 | Player Controller ID: BP_PlayerController_C_2147285821)caused by BP_KBA3_HEAT_C_2147362075',
            '[2026.02.06-16.57.19:764][922]LogSquadTrace: [DedicatedServer]Wound(): Player: enwez KillingDamage=37.075439 from BP_PlayerController_C_2147285821 (Online IDs: EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 | Controller ID: BP_PlayerController_C_2147285821) caused by BP_KBA3_HEAT_C_2147362075',
            '[2026.02.06-16.57.23:024][130]LogSquadTrace: [DedicatedServer]Die(): Player: enwez KillingDamage=-300.000000 from BP_PlayerController_C_2147285821 (Online IDs: EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 | Contoller ID: BP_PlayerController_C_2147285821) caused by BP_Soldier_RU_HAT_RPG28_Desert_C_2147279843',
        ]
        events = await self._run_parser(lines)
        assert len(events) == 3
        assert isinstance(events[0], PlayerDamaged)
        assert isinstance(events[1], PlayerWounded)
        assert isinstance(events[2], PlayerDied)

    async def test_unmatched_lines_ignored(self):
        lines = [
            '[2026.02.06-15.02.16:900][771]LogSquad: USQGameState: Server Tick Rate: 63.78',
            'some random unmatched line',
            '[2026.02.06-15.02.26:935][411]LogSquad: USQGameState: Server Tick Rate: 63.78',
        ]
        events = await self._run_parser(lines)
        assert len(events) == 2
        assert all(isinstance(e, ServerTickRate) for e in events)

    async def _run_parser(self, lines: list[str]) -> list[BaseEvent]:
        """Helper: run parser with mock reader and capture all emitted events."""
        collected: list[BaseEvent] = []
        bus = EventBus()

        async def capture(event: BaseEvent):
            collected.append(event)

        # Subscribe to all possible event names
        event_names = [
            "player_connected", "join_succeeded", "player_disconnected",
            "player_damaged", "player_wounded", "player_died", "player_revived",
            "player_possess", "player_unpossess", "new_game", "round_ended",
            "server_tick_rate", "admin_broadcast", "deployable_damaged",
        ]
        for name in event_names:
            bus.subscribe(name, capture)

        reader = MockLogReader(lines)
        parser = LogParser(reader=reader, event_bus=bus)
        await parser.run()
        return collected
