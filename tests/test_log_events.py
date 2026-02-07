"""Tests for log parser event dataclasses."""

from squadpy.events.types import (
    PlayerID,
    PlayerConnected,
    PlayerDisconnected,
    JoinSucceeded,
    PlayerDamaged,
    PlayerWounded,
    PlayerDied,
    PlayerRevived,
    PlayerPossess,
    PlayerUnpossess,
    NewGame,
    RoundEnded,
    RoundTickets,
    ServerTickRate,
    AdminBroadcast,
    DeployableDamaged,
)


class TestPlayerID:
    def test_defaults(self):
        pid = PlayerID()
        assert pid.steam_id == ""
        assert pid.eos_id == ""
        assert pid.name == ""
        assert pid.controller == ""


class TestPlayerConnected:
    def test_event_name(self):
        e = PlayerConnected()
        assert e.event_name == "player_connected"

    def test_fields(self):
        pid = PlayerID(eos_id="abc", steam_id="123", name="Test")
        e = PlayerConnected(player=pid, ip="1.2.3.4", chain_id=42)
        assert e.player.eos_id == "abc"
        assert e.ip == "1.2.3.4"
        assert e.chain_id == 42


class TestPlayerDied:
    def test_event_name(self):
        e = PlayerDied()
        assert e.event_name == "player_died"

    def test_fields(self):
        attacker = PlayerID(eos_id="atk", steam_id="456")
        e = PlayerDied(
            victim_name="victim",
            damage=300.0,
            attacker=attacker,
            weapon="BP_Frag_C",
        )
        assert e.victim_name == "victim"
        assert e.attacker.eos_id == "atk"
        assert e.weapon == "BP_Frag_C"


class TestRoundEnded:
    def test_draw(self):
        e = RoundEnded()
        assert e.winner is None
        assert e.loser is None


class TestDeployableDamaged:
    def test_event_name(self):
        e = DeployableDamaged()
        assert e.event_name == "deployable_damaged"
