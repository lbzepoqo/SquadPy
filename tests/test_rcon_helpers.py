"""Tests for RCON response parsing and convenience methods."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from squadpy.rcon.client import (
    parse_players,
    parse_squads,
    parse_map,
    _CURRENT_MAP_RE,
    _NEXT_MAP_RE,
    RconClient,
)
from squadpy.rcon.types import MapInfo, RconPlayer, RconSquad

FIXTURES = Path(__file__).parent / "fixtures" / "samples" / "rcon"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


class TestParseListPlayers:
    def test_sample1_count(self):
        """Sample 1 has 99 active players."""
        data = load_fixture("ListPlayers (Sample 1).txt")
        players = parse_players(data)
        assert len(players) == 99

    def test_sample1_basic_fields(self):
        """First player has expected fields."""
        data = load_fixture("ListPlayers (Sample 1).txt")
        players = parse_players(data)
        p = players[0]
        assert p.id == 87
        assert p.steam_id == "76561199202672950"
        assert p.eos_id == "000249f6e3454b2cae8e993a96838faa"
        assert p.name == "[INAF]  AMIN OPLEN"
        assert p.team_id == 1
        assert p.squad_id == 1
        assert p.is_leader is False
        assert p.role == "USA_MachineGunner_01"

    def test_sample1_na_squad_id(self):
        """Players with Squad ID: N/A get squad_id=0."""
        data = load_fixture("ListPlayers (Sample 1).txt")
        players = parse_players(data)
        # ID 4 Eiennein is N/A
        eiennein = next(p for p in players if p.id == 4)
        assert eiennein.squad_id == 0
        # ID 38 Seeloem is also N/A
        seeloem = next(p for p in players if p.id == 38)
        assert seeloem.squad_id == 0

    def test_sample1_trailing_comma_in_role(self):
        """Trailing commas in role field are stripped."""
        data = load_fixture("ListPlayers (Sample 1).txt")
        players = parse_players(data)
        # ID 53 Hakanai has WPMC_Rifleman_08,
        hakanai = next(p for p in players if p.id == 53)
        assert hakanai.role == "WPMC_Rifleman_08"
        assert not hakanai.role.endswith(",")

    def test_sample1_name_with_pipe(self):
        """Player names containing | are parsed correctly."""
        data = load_fixture("ListPlayers (Sample 1).txt")
        players = parse_players(data)
        # ID 42 has name: ɴямʟ |  SkandiaP [TH]
        skandia = next(p for p in players if p.id == 42)
        assert "|" in skandia.name
        assert "SkandiaP" in skandia.name

    def test_sample1_unicode_names(self):
        """Unicode characters in names are preserved."""
        data = load_fixture("ListPlayers (Sample 1).txt")
        players = parse_players(data)
        # ID 92 has CJK characters
        butcher = next(p for p in players if p.id == 92)
        assert "BUTCHER" in butcher.name

    def test_sample1_leader_flag(self):
        """Is Leader: True parsed correctly."""
        data = load_fixture("ListPlayers (Sample 1).txt")
        players = parse_players(data)
        # ID 18 is a leader
        ace = next(p for p in players if p.id == 18)
        assert ace.is_leader is True

    def test_sample2_active_count(self):
        """Sample 2 has 2 active players (disconnected section skipped)."""
        data = load_fixture("ListPlayers (Sample 2).txt")
        players = parse_players(data)
        assert len(players) == 2

    def test_sample2_both_unassigned(self):
        """Both players in sample 2 are unassigned (N/A)."""
        data = load_fixture("ListPlayers (Sample 2).txt")
        players = parse_players(data)
        assert all(p.squad_id == 0 for p in players)

    def test_sample2_disconnected_skipped(self):
        """Recently disconnected players are NOT included."""
        data = load_fixture("ListPlayers (Sample 2).txt")
        players = parse_players(data)
        names = [p.name for p in players]
        assert "UpsideDownFloof" not in " ".join(names)

    def test_empty_response(self):
        """Empty response returns empty list."""
        assert parse_players("") == []

    def test_malformed_lines_skipped(self):
        """Malformed lines don't crash, they're just skipped."""
        data = "garbage line\nID: bad data\n----- Active Players -----"
        assert parse_players(data) == []


class TestParseListSquads:
    def test_squad_count(self):
        """Sample has squads from 2 teams."""
        data = load_fixture("ListSquads.txt")
        squads = parse_squads(data)
        # Team 1: 13 squads (IDs 1-8, 10-14), Team 2: 11 squads
        assert len(squads) == 24

    def test_team_assignment(self):
        """Squads are assigned to correct teams."""
        data = load_fixture("ListSquads.txt")
        squads = parse_squads(data)
        team1 = [s for s in squads if s.team_id == 1]
        team2 = [s for s in squads if s.team_id == 2]
        assert len(team1) == 13
        assert len(team2) == 11

    def test_team_names(self):
        """Team names with special characters parsed correctly."""
        data = load_fixture("ListSquads.txt")
        squads = parse_squads(data)
        team2_squad = next(s for s in squads if s.team_id == 2)
        assert '"' in team2_squad.team_name  # Contains quotes

    def test_squad_fields(self):
        """Squad fields parsed correctly."""
        data = load_fixture("ListSquads.txt")
        squads = parse_squads(data)
        first = squads[0]
        assert first.id == 1
        assert first.name == "Squad 1"
        assert first.size == 1
        assert first.locked is True
        assert first.creator_name == "Arrex"
        assert first.creator_steam_id == "76561198112209427"
        assert first.creator_eos_id == "0002d52d94444153aa5084c59a43850f"
        assert first.team_id == 1

    def test_skipped_squad_ids(self):
        """Squad IDs can skip numbers (e.g. 8 -> 10)."""
        data = load_fixture("ListSquads.txt")
        squads = parse_squads(data)
        team1_ids = [s.id for s in squads if s.team_id == 1]
        assert 8 in team1_ids
        assert 9 not in team1_ids
        assert 10 in team1_ids

    def test_creator_with_special_chars(self):
        """Creator names with special characters parsed correctly."""
        data = load_fixture("ListSquads.txt")
        squads = parse_squads(data)
        # Sillychilli <3 is a creator
        rws = next(s for s in squads if s.name == "RWS")
        assert rws.creator_name == "Sillychilli <3"

    def test_empty_response(self):
        """Empty response returns empty list."""
        assert parse_squads("") == []


class TestParseMap:
    def test_current_map_with_factions(self):
        """ShowCurrentMap with factions suffix."""
        data = load_fixture("ShowCurrentMap.txt")
        info = parse_map(data, _CURRENT_MAP_RE)
        assert info is not None
        assert info.level == "Tallil Outskirts"
        assert info.layer == "SAT_Tallil_Seed_v1"
        assert info.factions == "VDV WPMC"

    def test_next_map_voting_enabled(self):
        """ShowNextMap when voting enabled returns None via 'not defined'."""
        data = load_fixture("ShowNextMap (Sample 1 - Voting enabled).txt")
        # This is "Next map is not defined" — no regex match
        info = parse_map(data, _NEXT_MAP_RE)
        assert info is None

    def test_next_map_voting_disabled(self):
        """ShowNextMap when set, with factions including +Support."""
        data = load_fixture("ShowNextMap (Sample 2 - Voting disabled).txt")
        info = parse_map(data, _NEXT_MAP_RE)
        assert info is not None
        assert info.level == "Sumari Bala"
        assert info.layer == "Sumari_Seed_v1"
        assert info.factions == "RGF+Support INS"

    def test_empty_response(self):
        """Empty response returns None."""
        assert parse_map("", _CURRENT_MAP_RE) is None


class TestRconClientConvenience:
    @pytest.fixture
    def client(self):
        c = RconClient(host="127.0.0.1", port=21114, password="test")
        c._connected = True
        c.execute = AsyncMock()
        return c

    async def test_list_players_calls_execute(self, client):
        client.execute.return_value = ""
        await client.list_players()
        client.execute.assert_awaited_once_with("ListPlayers")

    async def test_list_squads_calls_execute(self, client):
        client.execute.return_value = ""
        await client.list_squads()
        client.execute.assert_awaited_once_with("ListSquads")

    async def test_broadcast_calls_execute(self, client):
        client.execute.return_value = ""
        await client.broadcast("Hello world")
        client.execute.assert_awaited_once_with("AdminBroadcast Hello world")

    async def test_warn_quotes_player_id(self, client):
        client.execute.return_value = ""
        await client.warn("76561198000000000", "Stop that")
        client.execute.assert_awaited_once_with(
            'AdminWarn "76561198000000000" Stop that'
        )

    async def test_kick_quotes_player_id(self, client):
        client.execute.return_value = ""
        await client.kick("76561198000000000", "Banned")
        client.execute.assert_awaited_once_with(
            'AdminKick "76561198000000000" Banned'
        )

    async def test_ban_quotes_player_id_with_duration(self, client):
        client.execute.return_value = ""
        await client.ban("76561198000000000", "24h", "Cheating")
        client.execute.assert_awaited_once_with(
            'AdminBan "76561198000000000" 24h Cheating'
        )

    async def test_show_current_map_calls_execute(self, client):
        client.execute.return_value = "Current level is Test, layer is Test_v1, factions A B"
        result = await client.show_current_map()
        client.execute.assert_awaited_once_with("ShowCurrentMap")
        assert result is not None
        assert result.level == "Test"

    async def test_show_next_map_not_defined(self, client):
        client.execute.return_value = "Next map is not defined"
        result = await client.show_next_map()
        assert result is None

    async def test_show_next_map_defined(self, client):
        client.execute.return_value = "Next level is Sumari Bala, layer is Sumari_Seed_v1, factions RGF INS"
        result = await client.show_next_map()
        assert result is not None
        assert result.level == "Sumari Bala"

    async def test_list_players_returns_parsed(self, client):
        """Integration: real fixture data flows through convenience method."""
        client.execute.return_value = load_fixture("ListPlayers (Sample 1).txt")
        players = await client.list_players()
        assert len(players) == 99
        assert isinstance(players[0], RconPlayer)

    async def test_list_squads_returns_parsed(self, client):
        """Integration: real fixture data flows through convenience method."""
        client.execute.return_value = load_fixture("ListSquads.txt")
        squads = await client.list_squads()
        assert len(squads) == 24
        assert isinstance(squads[0], RconSquad)
