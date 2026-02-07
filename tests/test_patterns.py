"""Tests for Squad log line regex patterns."""

from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import get_rules, match_line
from squadpy.events.types import (
    PlayerConnected, JoinSucceeded, PlayerDisconnected,
)


class TestPlayerConnected:
    def test_vanilla_postlogin(self):
        line = '[2026.02.06-15.02.11:098][401]LogSquad: PostLogin: NewPlayer: BP_PlayerController_C /Game/Maps/Sumari/Gameplay_Layers/Sumari_Seed_v1.Sumari_Seed_v1:PersistentLevel.BP_PlayerController_C_2147476661 (IP: 174.110.37.249 | Online IDs: EOS: 000250f5e359453bb9ad313db051f19e steam: 76561198376713392)'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerConnected)
        assert event.player.eos_id == "000250f5e359453bb9ad313db051f19e"
        assert event.player.steam_id == "76561198376713392"
        assert event.ip == "174.110.37.249"
        assert event.chain_id == 401

    def test_modded_postlogin(self):
        line = '[2026.02.02-02.40.04:646][926]LogSquad: PostLogin: NewPlayer: BP_PlayerController_SATSeed_C /SquadAdminTools/Maps/SATSeed/Maps/Tallil/L_SAT_Tallil_Seed_v1.L_SAT_Tallil_Seed_v1:PersistentLevel.BP_PlayerController_SATSeed_C_2147480511 (IP: 61.245.141.66 | Online IDs: EOS: 000234112f50474f82d740a777a6b2d0 steam: 76561198375634826)'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerConnected)
        assert event.player.eos_id == "000234112f50474f82d740a777a6b2d0"
        assert event.chain_id == 926

    def test_stores_join_request(self):
        line = '[2026.02.06-15.02.11:098][401]LogSquad: PostLogin: NewPlayer: BP_PlayerController_C /Game/Maps/Sumari/Gameplay_Layers/Sumari_Seed_v1.Sumari_Seed_v1:PersistentLevel.BP_PlayerController_C_2147476661 (IP: 174.110.37.249 | Online IDs: EOS: 000250f5e359453bb9ad313db051f19e steam: 76561198376713392)'
        store = EventStore()
        match_line(line, store)
        assert 401 in store.join_requests
        assert store.join_requests[401]["eos_id"] == "000250f5e359453bb9ad313db051f19e"


class TestJoinSucceeded:
    def test_basic(self):
        # First, set up a join request in the store
        store = EventStore()
        store.join_requests[401] = {
            "controller_name": "BP_PlayerController_C_2147476661",
            "ip": "174.110.37.249",
            "eos_id": "000250f5e359453bb9ad313db051f19e",
            "steam_id": "76561198376713392",
        }
        line = '[2026.02.06-15.02.11:099][401]LogNet: Join succeeded: PAPA_ \u039e_TAN'
        event = match_line(line, store)
        assert isinstance(event, JoinSucceeded)
        assert event.player_suffix == "PAPA_ \u039e_TAN"
        assert event.player.eos_id == "000250f5e359453bb9ad313db051f19e"
        assert event.chain_id == 401

    def test_consumes_join_request(self):
        store = EventStore()
        store.join_requests[712] = {"eos_id": "abc", "steam_id": "123", "ip": "1.1.1.1", "controller_name": "x"}
        line = '[2026.02.06-15.02.15:974][712]LogNet: Join succeeded: U\u0274\u0274. Gunrunner'
        match_line(line, store)
        assert 712 not in store.join_requests


class TestPlayerDisconnected:
    def test_vanilla(self):
        line = '[2026.02.06-16.07.47:345][330]LogNet: UChannel::Close: Sending CloseBunch. ChIndex == 0. Name: [UChannel] ChIndex: 0, Closing: 0 [UNetConnection] RemoteAddr: 174.110.37.249:58734, Name: RedpointEOSIpNetConnection_2147476691, Driver: Name:GameNetDriver Def:GameNetDriver RedpointEOSNetDriver_2147482413, IsServer: YES, PC: BP_PlayerController_C_2147476661, Owner: BP_PlayerController_C_2147476661, UniqueId: RedpointEOS:000250f5e359453bb9ad313db051f19e'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerDisconnected)
        assert event.player.eos_id == "000250f5e359453bb9ad313db051f19e"
        assert event.ip == "174.110.37.249"
        assert event.controller_name == "BP_PlayerController_C_2147476661"

    def test_marks_disconnected_in_store(self):
        line = '[2026.02.06-16.07.47:345][330]LogNet: UChannel::Close: Sending CloseBunch. ChIndex == 0. Name: [UChannel] ChIndex: 0, Closing: 0 [UNetConnection] RemoteAddr: 174.110.37.249:58734, Name: RedpointEOSIpNetConnection_2147476691, Driver: Name:GameNetDriver Def:GameNetDriver RedpointEOSNetDriver_2147482413, IsServer: YES, PC: BP_PlayerController_C_2147476661, Owner: BP_PlayerController_C_2147476661, UniqueId: RedpointEOS:000250f5e359453bb9ad313db051f19e'
        store = EventStore()
        match_line(line, store)
        assert store.disconnected["000250f5e359453bb9ad313db051f19e"] is True
