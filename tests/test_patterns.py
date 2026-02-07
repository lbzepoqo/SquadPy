"""Tests for Squad log line regex patterns."""

from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import get_rules, match_line
from squadpy.events.types import (
    PlayerConnected, JoinSucceeded, PlayerDisconnected,
    PlayerDamaged, PlayerWounded, PlayerDied, PlayerRevived,
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


class TestPlayerDamaged:
    def test_with_attacker(self):
        line = '[2026.02.06-16.57.06:079][ 49]LogSquad: Player: enwez ActualDamage=58.952755 from  lord billybean (Online IDs: EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 | Player Controller ID: BP_PlayerController_C_2147285821)caused by BP_KBA3_HEAT_C_2147362075'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerDamaged)
        assert event.victim_name == "enwez"
        assert event.damage == 58.952755
        assert event.attacker.eos_id == "0002ded45cb5412e8d5c7833a92d36b3"
        assert event.weapon == "BP_KBA3_HEAT_C"

    def test_self_damage(self):
        line = '[2026.02.06-16.41.00:573][464]LogSquad: Player: U\u0274\u0274. Gunrunner ActualDamage=72.000000 from nullptr (Online IDs: INVALID | Player Controller ID: None)caused by BP_Projectile_7_62mm_C_2147303529'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerDamaged)
        assert event.attacker.eos_id == ""
        assert event.victim_name == "U\u0274\u0274. Gunrunner"

    def test_stores_in_session(self):
        line = '[2026.02.06-16.57.06:079][ 49]LogSquad: Player: enwez ActualDamage=58.952755 from  lord billybean (Online IDs: EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 | Player Controller ID: BP_PlayerController_C_2147285821)caused by BP_KBA3_HEAT_C_2147362075'
        store = EventStore()
        match_line(line, store)
        assert "enwez" in store.session


class TestPlayerWounded:
    def test_with_attacker(self):
        line = '[2026.02.06-16.57.19:764][922]LogSquadTrace: [DedicatedServer]Wound(): Player: enwez KillingDamage=37.075439 from BP_PlayerController_C_2147285821 (Online IDs: EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 | Controller ID: BP_PlayerController_C_2147285821) caused by BP_KBA3_HEAT_C_2147362075'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerWounded)
        assert event.victim_name == "enwez"
        assert event.damage == 37.075439
        assert event.attacker.eos_id == "0002ded45cb5412e8d5c7833a92d36b3"
        assert event.weapon == "BP_KBA3_HEAT_C"

    def test_nullptr_attacker(self):
        line = '[2026.02.06-16.41.37:573][824]LogSquadTrace: [DedicatedServer]Wound(): Player: U\u0274\u0274. Gunrunner KillingDamage=71.000000 from nullptr (Online IDs: INVALID | Controller ID: None) caused by BP_Projectile_7_62mm_C_2147300368'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerWounded)
        assert event.attacker.eos_id == ""


class TestPlayerDied:
    def test_with_attacker(self):
        line = '[2026.02.06-16.57.23:024][130]LogSquadTrace: [DedicatedServer]Die(): Player: enwez KillingDamage=-300.000000 from BP_PlayerController_C_2147285821 (Online IDs: EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 | Contoller ID: BP_PlayerController_C_2147285821) caused by BP_Soldier_RU_HAT_RPG28_Desert_C_2147279843'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerDied)
        assert event.victim_name == "enwez"
        assert event.attacker.eos_id == "0002ded45cb5412e8d5c7833a92d36b3"

    def test_nullptr_attacker(self):
        line = '[2026.02.06-16.41.39:656][957]LogSquadTrace: [DedicatedServer]Die(): Player: U\u0274\u0274. Gunrunner KillingDamage=-300.000000 from nullptr (Online IDs: INVALID | Contoller ID: None) caused by BP_Soldier_RU_HAT_RPG28_Desert_C_2147305683'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerDied)
        assert event.attacker.eos_id == ""

    def test_correlates_with_prior_damage(self):
        store = EventStore()
        store.session["enwez"] = {
            "attacker_eos_id": "0002ded45cb5412e8d5c7833a92d36b3",
            "attacker_steam_id": "76561198376630934",
            "weapon": "BP_KBA3_HEAT_C",
        }
        line = '[2026.02.06-16.57.23:024][130]LogSquadTrace: [DedicatedServer]Die(): Player: enwez KillingDamage=-300.000000 from BP_PlayerController_C_2147285821 (Online IDs: EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 | Contoller ID: BP_PlayerController_C_2147285821) caused by BP_Soldier_RU_HAT_RPG28_Desert_C_2147279843'
        event = match_line(line, store)
        assert isinstance(event, PlayerDied)


class TestPlayerRevived:
    def test_revive(self):
        line = '[2026.02.06-19.15.02:917][959]LogSquad:  U\u0274\u0274. MegaDeth (Online IDs: EOS: 00026d000720444fb2f4328f9164e9d0 steam: 76561197982173556) has revived U\u0274\u0274.\u2718 Sith Lord Grogu (Online IDs: EOS: 0002677dbc8e4269b108f244a38029e5 steam: 76561198128476165).'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerRevived)
        assert event.reviver.eos_id == "00026d000720444fb2f4328f9164e9d0"
        assert event.reviver.name == "U\u0274\u0274. MegaDeth"
        assert event.victim.eos_id == "0002677dbc8e4269b108f244a38029e5"
        assert event.victim.name == "U\u0274\u0274.\u2718 Sith Lord Grogu"
