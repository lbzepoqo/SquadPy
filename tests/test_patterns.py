"""Tests for Squad log line regex patterns."""

from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import match_line
from squadpy.events.types import (
    PlayerConnected, JoinSucceeded, PlayerDisconnected,
    PlayerDamaged, PlayerWounded, PlayerDied, PlayerRevived,
    Teamkill, SquadCreated, PlayerSwitchedTeam,
    NextLayerSet,
    SeedingThresholdUp, SeedingThresholdDown,
    PlayerPossess, PlayerUnpossess, NewGame, RoundEnded,
    ServerTickRate, AdminBroadcast, PlayerWarned, PlayerKicked, PlayerBanned,
    AdminCamPossess, AdminCamUnpossess, DeployableDamaged,
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


class TestSquadCreated:
    def test_parses_squad_created_line(self):
        line = "[2026.02.14-13.20.47:203][418]LogSquad: ObsidianHorse47 (Online IDs: EOS: 00029e5d00e947bbaed1b364814dd427) has created Squad 1 (Squad Name: ASDASDASD) on United States Army"
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, SquadCreated)
        assert event.squad_id == 1
        assert event.squad_name == "ASDASDASD"
        assert event.team_name == "United States Army"
        assert event.team_id == 0
        assert event.creator.eos_id == "00029e5d00e947bbaed1b364814dd427"
        assert event.creator.name == "ObsidianHorse47"

    def test_resolves_team_id_from_cached_creator_team(self):
        line = "[2026.02.14-13.20.47:203][418]LogSquad: ObsidianHorse47 (Online IDs: EOS: 00029e5d00e947bbaed1b364814dd427) has created Squad 1 (Squad Name: Squad 1) on United States Army"
        store = EventStore()
        store.players["00029e5d00e947bbaed1b364814dd427"] = {
            "name": "ObsidianHorse47",
            "steam_id": "76561198061567555",
            "team_id": 1,
        }
        event = match_line(line, store)
        assert isinstance(event, SquadCreated)
        assert event.team_id == 1
        assert store.player_teams_by_name["ObsidianHorse47"] == 1

    def test_resolves_team_id_from_rcon_team_name_cache(self):
        line = "[2026.02.14-13.20.47:203][418]LogSquad: ObsidianHorse47 (Online IDs: EOS: 00029e5d00e947bbaed1b364814dd427) has created Squad 1 (Squad Name: Squad 1) on United States Army"
        store = EventStore()
        store.team_ids_by_name["United States Army"] = 1
        event = match_line(line, store)
        assert isinstance(event, SquadCreated)
        assert event.team_id == 1


class TestPlayerSwitchedTeam:
    def test_emits_when_cached_team_changes(self):
        store = EventStore()
        first_assignment = "[2026.02.14-00.50.32:400][ 45]LogSquad: Player  PamanPanda has been added to Team 1"
        switch_assignment = "[2026.02.14-00.51.32:400][ 46]LogSquad: Player  PamanPanda has been added to Team 2"

        first_event = match_line(first_assignment, store)
        second_event = match_line(switch_assignment, store)

        assert first_event is None
        assert isinstance(second_event, PlayerSwitchedTeam)
        assert second_event.player.name == "PamanPanda"
        assert second_event.old_team == 1
        assert second_event.new_team == 2

    def test_does_not_emit_for_duplicate_team_assignment(self):
        store = EventStore()
        line = "[2026.02.14-00.50.32:400][ 45]LogSquad: Player  PamanPanda has been added to Team 2"
        match_line(line, store)
        event = match_line(line, store)
        assert event is None


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


class TestTeamkill:
    def test_wounded_same_team_queues_teamkill_event(self):
        store = EventStore()
        lines = [
            "[2026.02.14-00.50.32:400][ 45]LogSquad: Player  PamanPanda has been added to Team 2",
            "[2026.02.14-01.09.56:371][244]LogSquad: Player  Blackburn has been added to Team 2",
            "[2026.02.14-00.52.27:960][412]LogSquadTrace: [DedicatedServer]OnPossess(): PC=PamanPanda (Online IDs: EOS: 000202cd1a3a4c739203a874221393d0 steam: 76561198161847878) Pawn=BP_Soldier_VDV_SquadLeader_Desert_C_2147407760 FullPath=BP_Soldier_VDV_SquadLeader_Desert_C /SquadAdminTools/Maps/SATSeed/Maps/Tallil/L_SAT_Tallil_Seed_v1.L_SAT_Tallil_Seed_v1:PersistentLevel.BP_Soldier_VDV_SquadLeader_Desert_C_2147407760",
            "[2026.02.14-01.11.39:377][810]LogSquadTrace: [DedicatedServer]OnPossess(): PC=Blackburn (Online IDs: EOS: 00024bce20aa414282702cf909896053 steam: 76561198191272778) Pawn=BP_Soldiers_WPMC_SL_05_C_2147379502 FullPath=BP_Soldiers_WPMC_SL_05_C /SquadAdminTools/Maps/SATSeed/Maps/Tallil/L_SAT_Tallil_Seed_v1.L_SAT_Tallil_Seed_v1:PersistentLevel.BP_Soldiers_WPMC_SL_05_C_2147379502",
            "[2026.02.14-01.16.31:277][417]LogSquadTrace: [DedicatedServer]Wound(): Player:[INAF]  PamanPanda KillingDamage=150.000000 from BP_PlayerController_SATSeed_C_2147382416 (Online IDs: EOS: 00024bce20aa414282702cf909896053 steam: 76561198191272778 | Controller ID: BP_PlayerController_SATSeed_C_2147382416) caused by BP_M134_Loach_Dual_C_2147377585",
        ]

        emitted: list[object] = []
        for line in lines:
            event = match_line(line, store)
            if event is not None:
                emitted.append(event)
            emitted.extend(store.drain_pending_events())

        teamkills = [e for e in emitted if isinstance(e, Teamkill)]
        assert len(teamkills) == 1
        teamkill = teamkills[0]
        assert teamkill.attacker.eos_id == "00024bce20aa414282702cf909896053"
        assert teamkill.attacker.name == "Blackburn"
        assert teamkill.victim.eos_id == "000202cd1a3a4c739203a874221393d0"
        assert teamkill.victim.name == "PamanPanda"
        assert teamkill.weapon == "BP_M134_Loach_Dual_C"

    def test_wounded_different_team_does_not_queue_teamkill(self):
        store = EventStore()
        lines = [
            "[2026.02.14-00.50.32:400][ 45]LogSquad: Player  PamanPanda has been added to Team 1",
            "[2026.02.14-01.09.56:371][244]LogSquad: Player  Blackburn has been added to Team 2",
            "[2026.02.14-00.52.27:960][412]LogSquadTrace: [DedicatedServer]OnPossess(): PC=PamanPanda (Online IDs: EOS: 000202cd1a3a4c739203a874221393d0 steam: 76561198161847878) Pawn=BP_Soldier_VDV_SquadLeader_Desert_C_2147407760 FullPath=BP_Soldier_VDV_SquadLeader_Desert_C /SquadAdminTools/Maps/SATSeed/Maps/Tallil/L_SAT_Tallil_Seed_v1.L_SAT_Tallil_Seed_v1:PersistentLevel.BP_Soldier_VDV_SquadLeader_Desert_C_2147407760",
            "[2026.02.14-01.11.39:377][810]LogSquadTrace: [DedicatedServer]OnPossess(): PC=Blackburn (Online IDs: EOS: 00024bce20aa414282702cf909896053 steam: 76561198191272778) Pawn=BP_Soldiers_WPMC_SL_05_C_2147379502 FullPath=BP_Soldiers_WPMC_SL_05_C /SquadAdminTools/Maps/SATSeed/Maps/Tallil/L_SAT_Tallil_Seed_v1.L_SAT_Tallil_Seed_v1:PersistentLevel.BP_Soldiers_WPMC_SL_05_C_2147379502",
            "[2026.02.14-01.16.31:277][417]LogSquadTrace: [DedicatedServer]Wound(): Player:[INAF]  PamanPanda KillingDamage=150.000000 from BP_PlayerController_SATSeed_C_2147382416 (Online IDs: EOS: 00024bce20aa414282702cf909896053 steam: 76561198191272778 | Controller ID: BP_PlayerController_SATSeed_C_2147382416) caused by BP_M134_Loach_Dual_C_2147377585",
        ]

        for line in lines:
            match_line(line, store)

        assert store.drain_pending_events() == []

    def test_died_same_team_without_prior_wound_queues_teamkill_event(self):
        store = EventStore()
        lines = [
            "[2026.02.14-00.50.32:400][ 45]LogSquad: Player  PamanPanda has been added to Team 2",
            "[2026.02.14-01.09.56:371][244]LogSquad: Player  Blackburn has been added to Team 2",
            "[2026.02.14-00.52.27:960][412]LogSquadTrace: [DedicatedServer]OnPossess(): PC=PamanPanda (Online IDs: EOS: 000202cd1a3a4c739203a874221393d0 steam: 76561198161847878) Pawn=BP_Soldier_VDV_SquadLeader_Desert_C_2147407760 FullPath=BP_Soldier_VDV_SquadLeader_Desert_C /SquadAdminTools/Maps/SATSeed/Maps/Tallil/L_SAT_Tallil_Seed_v1.L_SAT_Tallil_Seed_v1:PersistentLevel.BP_Soldier_VDV_SquadLeader_Desert_C_2147407760",
            "[2026.02.14-01.11.39:377][810]LogSquadTrace: [DedicatedServer]OnPossess(): PC=Blackburn (Online IDs: EOS: 00024bce20aa414282702cf909896053 steam: 76561198191272778) Pawn=BP_Soldiers_WPMC_SL_05_C_2147379502 FullPath=BP_Soldiers_WPMC_SL_05_C /SquadAdminTools/Maps/SATSeed/Maps/Tallil/L_SAT_Tallil_Seed_v1.L_SAT_Tallil_Seed_v1:PersistentLevel.BP_Soldiers_WPMC_SL_05_C_2147379502",
            "[2026.02.14-01.16.33:333][420]LogSquadTrace: [DedicatedServer]Die(): Player:[INAF]  PamanPanda KillingDamage=100.000000 from BP_PlayerController_SATSeed_C_2147382416 (Online IDs: EOS: 00024bce20aa414282702cf909896053 steam: 76561198191272778 | Contoller ID: BP_PlayerController_SATSeed_C_2147382416) caused by BP_M134_Loach_Dual_C_2147377585",
        ]

        emitted: list[object] = []
        for line in lines:
            event = match_line(line, store)
            if event is not None:
                emitted.append(event)
            emitted.extend(store.drain_pending_events())

        teamkills = [e for e in emitted if isinstance(e, Teamkill)]
        assert len(teamkills) == 1
        teamkill = teamkills[0]
        assert teamkill.attacker.name == "Blackburn"
        assert teamkill.victim.name == "PamanPanda"
        assert teamkill.weapon == "BP_M134_Loach_Dual_C"

    def test_wounded_then_died_same_attacker_queues_one_teamkill(self):
        store = EventStore()
        lines = [
            "[2026.02.14-00.50.32:400][ 45]LogSquad: Player  PamanPanda has been added to Team 2",
            "[2026.02.14-01.09.56:371][244]LogSquad: Player  Blackburn has been added to Team 2",
            "[2026.02.14-00.52.27:960][412]LogSquadTrace: [DedicatedServer]OnPossess(): PC=PamanPanda (Online IDs: EOS: 000202cd1a3a4c739203a874221393d0 steam: 76561198161847878) Pawn=BP_Soldier_VDV_SquadLeader_Desert_C_2147407760 FullPath=BP_Soldier_VDV_SquadLeader_Desert_C /SquadAdminTools/Maps/SATSeed/Maps/Tallil/L_SAT_Tallil_Seed_v1.L_SAT_Tallil_Seed_v1:PersistentLevel.BP_Soldier_VDV_SquadLeader_Desert_C_2147407760",
            "[2026.02.14-01.11.39:377][810]LogSquadTrace: [DedicatedServer]OnPossess(): PC=Blackburn (Online IDs: EOS: 00024bce20aa414282702cf909896053 steam: 76561198191272778) Pawn=BP_Soldiers_WPMC_SL_05_C_2147379502 FullPath=BP_Soldiers_WPMC_SL_05_C /SquadAdminTools/Maps/SATSeed/Maps/Tallil/L_SAT_Tallil_Seed_v1.L_SAT_Tallil_Seed_v1:PersistentLevel.BP_Soldiers_WPMC_SL_05_C_2147379502",
            "[2026.02.14-01.16.31:277][417]LogSquadTrace: [DedicatedServer]Wound(): Player:[INAF]  PamanPanda KillingDamage=150.000000 from BP_PlayerController_SATSeed_C_2147382416 (Online IDs: EOS: 00024bce20aa414282702cf909896053 steam: 76561198191272778 | Controller ID: BP_PlayerController_SATSeed_C_2147382416) caused by BP_M134_Loach_Dual_C_2147377585",
            "[2026.02.14-01.16.33:333][420]LogSquadTrace: [DedicatedServer]Die(): Player:[INAF]  PamanPanda KillingDamage=-300.000000 from BP_PlayerController_SATSeed_C_2147382416 (Online IDs: EOS: 00024bce20aa414282702cf909896053 steam: 76561198191272778 | Contoller ID: BP_PlayerController_SATSeed_C_2147382416) caused by BP_Soldier_WPMC_SL_05_C_2147379502",
        ]

        emitted: list[object] = []
        for line in lines:
            event = match_line(line, store)
            if event is not None:
                emitted.append(event)
            emitted.extend(store.drain_pending_events())

        teamkills = [e for e in emitted if isinstance(e, Teamkill)]
        assert len(teamkills) == 1
        assert teamkills[0].weapon == "BP_M134_Loach_Dual_C"


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


class TestPlayerPossess:
    def test_infantry(self):
        line = '[2026.02.06-15.05.03:337][386]LogSquadTrace: [DedicatedServer]OnPossess(): PC=U\u0274\u0274. Gunrunner (Online IDs: EOS: 00022f823cdc4f1cad945c19ff4e8b37 steam: 76561198031492269) Pawn=BP_Soldier_TLF_Medic_01_C_2147464264 FullPath=BP_Soldier_TLF_Medic_01_C /Game/Maps/Sumari/Gameplay_Layers/Sumari_Seed_v1.Sumari_Seed_v1:PersistentLevel.BP_Soldier_TLF_Medic_01_C_2147464264'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerPossess)
        assert event.player.eos_id == "00022f823cdc4f1cad945c19ff4e8b37"
        assert event.possess_classname == "BP_Soldier_TLF_Medic_01_C"

    def test_vehicle(self):
        line = '[2026.02.06-15.28.52:780][490]LogSquadTrace: [DedicatedServer]OnPossess(): PC=PAPA_ \u039e_TAN (Online IDs: EOS: 000250f5e359453bb9ad313db051f19e steam: 76561198376713392) Pawn=BP_Loach_CAS_Small_C_2147396130 FullPath=BP_Loach_CAS_Small_C /Game/Maps/Jensens_Range/Gameplay_Layers/Jensens_Range_WPMC-TLF.Jensens_Range_WPMC-TLF:PersistentLevel.BP_Loach_CAS_Small_C_2147396130'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerPossess)
        assert event.possess_classname == "BP_Loach_CAS_Small_C"


class TestPlayerUnpossess:
    def test_normal(self):
        line = '[2026.02.06-15.18.55:664][475]LogSquadTrace: [DedicatedServer]OnUnPossess(): PC=U\u0274\u0274. Gunrunner (Online IDs: EOS: 00022f823cdc4f1cad945c19ff4e8b37 steam: 76561198031492269) current health value 100.000000'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerUnpossess)
        assert event.player.eos_id == "00022f823cdc4f1cad945c19ff4e8b37"
        assert event.health == 100.0
        assert event.exited_vehicle is False

    def test_vehicle_exit(self):
        line = '[2026.02.06-15.36.45:676][655]LogSquadTrace: [DedicatedServer]OnUnPossess(): PC=PAPA_ \u039e_TAN (Online IDs: EOS: 000250f5e359453bb9ad313db051f19e steam: 76561198376713392) Exited Vehicle Pawn=PAPA_ \u039e_TAN (Asset Name=BP_Loach_CAS_Small_C) FullPath=BP_Loach_CAS_Small_C /Game/Maps/Jensens_Range/Gameplay_Layers/Jensens_Range_WPMC-TLF.Jensens_Range_WPMC-TLF:PersistentLevel.BP_Loach_CAS_Small_C_2147396130 Seat Number=0'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerUnpossess)
        assert event.exited_vehicle is True
        assert event.vehicle_name == "BP_Loach_CAS_Small_C"
        assert event.seat_number == 0


class TestAdminCamPossess:
    def test_admin_cam_possess_from_correlated_lines(self):
        store = EventStore()
        match_line(
            '[2026.02.14-05.23.57:674][804]LogSquadTrace: [DedicatedServer]OnPossess(): PC=Callsign (Online IDs: EOS: 00025c44975740ca82effe91ef190757 steam: 76561199267250463) Pawn=BP_DeveloperAdminCam_C_2146619275 FullPath=BP_DeveloperAdminCam_C /SquadAdminTools/Maps/SATSeed/Maps/Tallil/L_SAT_Tallil_Seed_v1.L_SAT_Tallil_Seed_v1:PersistentLevel.BP_DeveloperAdminCam_C_2146619275',
            store,
        )
        event = match_line(
            '[2026.02.14-05.23.57:674][804]LogSquad: Warning: Admin Camera possessed.',
            store,
        )
        assert isinstance(event, AdminCamPossess)
        assert event.admin.name == "Callsign"
        assert event.admin.eos_id == "00025c44975740ca82effe91ef190757"
        assert event.admin.steam_id == "76561199267250463"
        assert event.target == "Admin Camera"
        assert event.context["pawn_classname"] == "BP_DeveloperAdminCam_C"
        assert "BP_DeveloperAdminCam_C" in event.context["full_path"]

    def test_admin_cam_warning_without_context_returns_none(self):
        store = EventStore()
        event = match_line(
            '[2026.02.14-05.23.57:674][804]LogSquad: Warning: Admin Camera possessed.',
            store,
        )
        assert event is None


class TestAdminCamUnpossess:
    def test_admin_cam_unpossess_from_correlated_open_close(self):
        store = EventStore()
        match_line(
            '[2026.02.02-12.23.29:659][529]LogSquadTrace: [DedicatedServer]OnPossess(): PC=Callsign (Online IDs: EOS: 00025c44975740ca82effe91ef190757 steam: 76561199267250463) Pawn=BP_DeveloperAdminCam_C_2141703157 FullPath=BP_DeveloperAdminCam_C /Game/Maps/Yehorivka/Gameplay_Layers/Yehorivka_RAAS_v2.Yehorivka_RAAS_v2:PersistentLevel.BP_DeveloperAdminCam_C_2141703157',
            store,
        )
        match_line(
            '[2026.02.02-12.23.29:660][529]LogSquad: Warning: Admin Camera possessed.',
            store,
        )
        event = match_line(
            '[2026.02.02-12.29.43:890][912]LogSquadTrace: [DedicatedServer]OnUnPossess(): PC=Callsign (Online IDs: EOS: 00025c44975740ca82effe91ef190757 steam: 76561199267250463)',
            store,
        )
        assert isinstance(event, AdminCamUnpossess)
        assert event.admin.name == "Callsign"
        assert event.admin.eos_id == "00025c44975740ca82effe91ef190757"
        assert event.admin.steam_id == "76561199267250463"
        assert event.target == "Admin Camera"
        assert event.context["pawn_classname"] == "BP_DeveloperAdminCam_C"
        assert event.context["open_chain_id"] == 529
        assert event.context["close_chain_id"] == 912

    def test_admin_cam_unpossess_without_open_session_returns_none(self):
        store = EventStore()
        event = match_line(
            '[2026.02.02-12.29.43:890][912]LogSquadTrace: [DedicatedServer]OnUnPossess(): PC=Callsign (Online IDs: EOS: 00025c44975740ca82effe91ef190757 steam: 76561199267250463)',
            store,
        )
        assert event is None


class TestNewGame:
    def test_vanilla_map(self):
        line = '[2026.02.06-15.19.26:022][383]LogWorld: Bringing World /Game/Maps/Jensens_Range/Gameplay_Layers/Jensens_Range_WPMC-TLF.Jensens_Range_WPMC-TLF up for play (max tick rate 64) at 2026.02.06-15.19.26'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, NewGame)
        assert event.dlc == "Game"
        assert event.map_classname == "Jensens_Range"
        assert event.layer_classname == "Jensens_Range_WPMC-TLF"

    def test_modded_map(self):
        line = '[2026.02.07-05.58.50:012][867]LogWorld: Bringing World /HawksLayerPack/Maps/Mutaha/Gameplay_Layers/HLP_Mutaha_GRAAS_v1.HLP_Mutaha_GRAAS_v1 up for play (max tick rate 64) at 2026.02.07-05.58.50'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, NewGame)
        assert event.dlc == "HawksLayerPack"
        assert event.layer_classname == "HLP_Mutaha_GRAAS_v1"

    def test_transition_map_ignored(self):
        line = '[2026.02.06-15.19.25:580][366]LogWorld: Bringing World /Game/Maps/TransitionMap.TransitionMap up for play (max tick rate 64) at 2026.02.06-15.19.25'
        store = EventStore()
        event = match_line(line, store)
        assert event is None

    def test_clears_event_store(self):
        store = EventStore()
        store.session["old"] = {"data": 1}
        store.players["eos"] = {"name": "test"}
        line = '[2026.02.06-15.19.26:022][383]LogWorld: Bringing World /Game/Maps/Jensens_Range/Gameplay_Layers/Jensens_Range_WPMC-TLF.Jensens_Range_WPMC-TLF up for play (max tick rate 64) at 2026.02.06-15.19.26'
        match_line(line, store)
        assert store.session == {}


class TestRoundEnded:
    def test_with_winner_and_loser(self):
        store = EventStore()
        store.round_winner = {"team": "1", "subfaction": "MEA", "tickets": 50}
        store.round_loser = {"team": "2", "subfaction": "USA", "tickets": 0}
        line = '[2026.02.06-15.18.55:666][475]LogGameState: Match State Changed from InProgress to WaitingPostMatch'
        event = match_line(line, store)
        assert isinstance(event, RoundEnded)
        assert event.winner is not None
        assert event.loser is not None
        assert event.winner["team"] == "1"
        assert event.loser["team"] == "2"
        assert store.round_winner is None
        assert store.round_loser is None

    def test_draw(self):
        store = EventStore()
        line = '[2026.02.06-15.18.55:666][475]LogGameState: Match State Changed from InProgress to WaitingPostMatch'
        event = match_line(line, store)
        assert isinstance(event, RoundEnded)
        assert event.winner is None
        assert event.loser is None


class TestRoundWinnerAndTickets:
    def test_round_winner_stores_not_emits(self):
        line = '[2026.02.06-15.18.55:664][475]LogSquadTrace: [DedicatedServer]DetermineMatchWinner(): Manticore Security Task Force won on Sumari Bala'
        store = EventStore()
        event = match_line(line, store)
        assert event is None
        assert store.round_winner is not None
        assert store.round_winner["winner"] == "Manticore Security Task Force"

    def test_draw_stores(self):
        line = '[2026.02.06-15.18.55:664][475]LogSquadTrace: [DedicatedServer]DetermineMatchWinner(): The game was a draw on Sumari Bala'
        store = EventStore()
        event = match_line(line, store)
        assert event is None
        assert store.round_winner is not None
        assert store.round_winner["winner"] is None

    def test_round_tickets_stores_winner(self):
        line = "[2026.02.06-20.45.07:818][740]LogSquadGameEvents: Display: Team 1, Irregular Battle Group ( Middle Eastern Insurgents ) has won the match with 2 Tickets on layer Sumari Bala Seed v1 (level Sumari Bala)!"
        store = EventStore()
        event = match_line(line, store)
        assert event is None
        assert store.round_winner is not None
        assert store.round_winner["tickets"] == 2

    def test_round_tickets_stores_loser(self):
        line = "[2026.02.06-20.45.07:818][740]LogSquadGameEvents: Display: Team 2, 21st Division ( Ground Forces of Iran ) has lost the match with 0 Tickets on layer Sumari Bala Seed v1 (level Sumari Bala)!"
        store = EventStore()
        event = match_line(line, store)
        assert event is None
        assert store.round_loser is not None
        assert store.round_loser["tickets"] == 0


class TestServerTickRate:
    def test_tick_rate(self):
        line = '[2026.02.06-15.02.16:900][771]LogSquad: USQGameState: Server Tick Rate: 63.78'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, ServerTickRate)
        assert event.tick_rate == 63.78


class TestAdminBroadcast:
    def test_broadcast(self):
        line = '[2026.02.06-11.00.09:436][125]LogSquad: ADMIN COMMAND: Message broadcasted <Custom squad creation will be unlocked in 10 seconds. Default squad names are allowed.> from RCON'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, AdminBroadcast)
        assert "Custom squad creation" in event.message
        assert event.from_player == "RCON"
        assert event.source == "RCON"
        assert event.source_detail == "RCON"


class TestNextLayerSet:
    def test_next_layer_set_from_rcon(self):
        line = "[2026.02.07-10.24.24:119][100]LogSquad: ADMIN COMMAND: Set next layer to BlackCoast_RAAS_v1 AFU+Mechanized TLF+Mechanized from RCON"
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, NextLayerSet)
        assert event.layer == "BlackCoast_RAAS_v1 AFU+Mechanized TLF+Mechanized"
        assert event.source == "RCON"
        assert event.source_detail == "RCON"

    def test_next_layer_set_from_ingame_player(self):
        line = "[2026.02.06-18.57.01:681][ 48]LogSquad: ADMIN COMMAND: Set next layer to Sumari_Seed_v1 MEI IMF from player 6. [Online IDs= EOS: 0002da64425942219800515623ef26f8 steam: 76561198438981792] Uɴɴ.s.  CornierDuke"
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, NextLayerSet)
        assert event.layer == "Sumari_Seed_v1 MEI IMF"
        assert event.source == "IN_GAME"
        assert event.source_detail.startswith("player 6.")


class TestSeedingThresholdTransitions:
    def test_emits_seeding_threshold_up_on_increase(self):
        store = EventStore()
        line_1 = "[2026.02.02-02.40.14:835][575]LogSquad: ADMIN COMMAND: Set SeedTargetPlayerCount to 15 from RCON"
        line_2 = "[2026.02.02-02.58.59:380][429]LogSquad: ADMIN COMMAND: Set SeedTargetPlayerCount to 20 from RCON"

        first_event = match_line(line_1, store)
        second_event = match_line(line_2, store)

        assert first_event is None
        assert isinstance(second_event, SeedingThresholdUp)
        assert second_event.old_threshold == 15
        assert second_event.new_threshold == 20
        assert second_event.source == "RCON"

    def test_emits_seeding_threshold_down_on_decrease(self):
        store = EventStore()
        line_1 = "[2026.02.02-02.40.14:835][575]LogSquad: ADMIN COMMAND: Set SeedTargetPlayerCount to 20 from RCON"
        line_2 = "[2026.02.02-02.58.59:380][429]LogSquad: ADMIN COMMAND: Set SeedTargetPlayerCount to 15 from RCON"

        match_line(line_1, store)
        event = match_line(line_2, store)

        assert isinstance(event, SeedingThresholdDown)
        assert event.old_threshold == 20
        assert event.new_threshold == 15
        assert event.source == "RCON"


class TestPlayerWarned:
    def test_warned(self):
        line = '[2026.02.02-02.40.44:503][466]LogSquad: ADMIN COMMAND: Remote admin has warned player  Rellmi. Message was "Type !commands to know the server commands." from RCON'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerWarned)
        assert event.admin == "Remote admin"
        assert event.player.name == "Rellmi"
        assert event.reason == "Type !commands to know the server commands."
        assert event.source == "RCON"
        assert event.source_detail == "RCON"

    def test_warned_source_normalization_for_ingame(self):
        line = '[2026.02.02-02.40.44:503][466]LogSquad: ADMIN COMMAND: Remote admin has warned player  Rellmi. Message was "Stop." from player 6. [Online IDs= EOS: 0002da64425942219800515623ef26f8 steam: 76561198438981792] CornierDuke'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerWarned)
        assert event.source == "IN_GAME"
        assert event.source_detail.startswith("player 6.")


class TestPlayerKicked:
    def test_kicked(self):
        line = '[2026.02.02-02.40.56:981][517]LogSquad: ADMIN COMMAND: Remote admin has kicked player  Rellmi. Reason was "Spamming in command chat." from RCON'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerKicked)
        assert event.admin == "Remote admin"
        assert event.player.name == "Rellmi"
        assert event.reason == "Spamming in command chat."
        assert event.source == "RCON"
        assert event.source_detail == "RCON"

    def test_kicked_source_normalization_for_ingame(self):
        line = '[2026.02.02-02.40.56:981][517]LogSquad: ADMIN COMMAND: Remote admin has kicked player  Rellmi. Reason was "Spamming in command chat." from player 6. [Online IDs= EOS: 0002da64425942219800515623ef26f8 steam: 76561198438981792] CornierDuke'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, PlayerKicked)
        assert event.source == "IN_GAME"
        assert event.source_detail.startswith("player 6.")


class TestPlayerBanned:
    def test_banned_from_ingame_command_with_correlated_reason(self):
        store = EventStore()
        match_line(
            '[2026.02.14-09.48.09:451][919]LogOnlineGame: Display: Banning player: ObsidianHorse47 ; Reason = Kupal admin',
            store,
        )
        match_line(
            '[2026.02.14-09.48.09:451][919]LogOnlineGame: Display: Kicking player:  ObsidianHorse47 ; Reason = Banned from the server for 0 Day(s). Admin Reason: Kupal admin.',
            store,
        )
        event = match_line(
            '[2026.02.14-09.48.09:451][919]LogSquad: ADMIN COMMAND:  ObsidianHorse47 [EOSID 00029e5d00e947bbaed1b364814dd427] Banned player 77. [Online IDs= EOS: 00029e5d00e947bbaed1b364814dd427 steam: 76561198061567555]  ObsidianHorse47 for interval -612331984 from player 77. [Online IDs= EOS: 00029e5d00e947bbaed1b364814dd427 steam: 76561198061567555]  ObsidianHorse47',
            store,
        )
        assert isinstance(event, PlayerBanned)
        assert event.admin == "ObsidianHorse47"
        assert event.player.eos_id == "00029e5d00e947bbaed1b364814dd427"
        assert event.player.steam_id == "76561198061567555"
        assert event.player.name == "ObsidianHorse47"
        assert event.duration == "0 Day(s)"
        assert event.reason == "Kupal admin"
        assert event.source == "IN_GAME"
        assert event.source_detail.startswith("player 77.")

    def test_banned_from_rcon_with_correlated_reason(self):
        store = EventStore()
        match_line(
            '[2026.02.14-09.53.12:293][914]LogOnlineGame: Display: Banning player: ObsidianHorse47 ; Reason = Kupal na admin',
            store,
        )
        match_line(
            '[2026.02.14-09.53.12:294][914]LogOnlineGame: Display: Kicking player:  ObsidianHorse47 ; Reason = Banned from the server for 1 Day(s). Admin Reason: Kupal na admin.',
            store,
        )
        event = match_line(
            '[2026.02.14-09.53.12:294][914]LogSquad: ADMIN COMMAND: N/A Banned player 46. [Online IDs= EOS: 00029e5d00e947bbaed1b364814dd427 steam: 76561198061567555]  ObsidianHorse47 for interval -171852224 from RCON',
            store,
        )
        assert isinstance(event, PlayerBanned)
        assert event.admin == "N/A"
        assert event.player.name == "ObsidianHorse47"
        assert event.duration == "1 Day(s)"
        assert event.reason == "Kupal na admin"
        assert event.source == "RCON"
        assert event.source_detail == "RCON"


class TestDeployableDamaged:
    def test_deployable(self):
        line = '[2026.02.06-17.05.08:591][826]LogSquadTrace: [DedicatedServer]TakeDamage(): ASQDeployable::TakeDamage[SQRadialDamage] BP_I_Sandbag_80 for 115.000000 damage (type=BP_Fragmentation_DamageType_C) direct hit = 0'
        store = EventStore()
        event = match_line(line, store)
        assert isinstance(event, DeployableDamaged)
        assert event.deployable == "BP_I_Sandbag_80"
        assert event.damage == 115.0
        assert event.damage_source == "SQRadialDamage"
        assert event.damage_type == "BP_Fragmentation_DamageType_C"
        assert event.direct_hit is False
