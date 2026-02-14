"""Integration tests for the LogParser — feeds lines, verifies events."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from squadpy.events.emitter import EventBus
from squadpy.events.types import (
    BaseEvent, PlayerConnected, JoinSucceeded, PlayerDamaged,
    PlayerWounded, PlayerDied, PlayerPossess, PlayerUnpossess,
    NewGame, RoundEnded, ServerTickRate, AdminBroadcast, PlayerWarned, PlayerKicked,
    PlayerBanned, AdminCamPossess, AdminCamUnpossess, Teamkill, DeployableDamaged,
)
from squadpy.log_parser.parser import LogParser
from squadpy.log_parser.reader import LogReader
from squadpy.rcon.types import RconPlayer


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

    async def test_emits_possess_and_unpossess_events(self):
        lines = [
            '[2026.02.06-15.05.03:337][386]LogSquadTrace: [DedicatedServer]OnPossess(): PC=Gunrunner (Online IDs: EOS: 00022f823cdc4f1cad945c19ff4e8b37 steam: 76561198031492269) Pawn=BP_Soldier_TLF_Medic_01_C_2147464264 FullPath=BP_Soldier_TLF_Medic_01_C /Game/Maps/Sumari/Gameplay_Layers/Sumari_Seed_v1.Sumari_Seed_v1:PersistentLevel.BP_Soldier_TLF_Medic_01_C_2147464264',
            '[2026.02.06-15.36.45:676][655]LogSquadTrace: [DedicatedServer]OnUnPossess(): PC=Gunrunner (Online IDs: EOS: 00022f823cdc4f1cad945c19ff4e8b37 steam: 76561198031492269) Exited Vehicle Pawn=Gunrunner (Asset Name=BP_Loach_CAS_Small_C) FullPath=BP_Loach_CAS_Small_C /Game/Maps/Jensens_Range/Gameplay_Layers/Jensens_Range_WPMC-TLF.Jensens_Range_WPMC-TLF:PersistentLevel.BP_Loach_CAS_Small_C_2147396130 Seat Number=0',
        ]
        events = await self._run_parser(lines)
        assert len(events) == 2
        assert isinstance(events[0], PlayerPossess)
        assert isinstance(events[1], PlayerUnpossess)
        assert events[1].exited_vehicle is True
        assert events[1].vehicle_name == "BP_Loach_CAS_Small_C"

    async def test_emits_admin_broadcast_and_deployable_damage(self):
        lines = [
            '[2026.02.06-11.00.09:436][125]LogSquad: ADMIN COMMAND: Message broadcasted <Server restart in 5 minutes> from RCON',
            '[2026.02.06-17.05.08:591][826]LogSquadTrace: [DedicatedServer]TakeDamage(): ASQDeployable::TakeDamage[SQRadialDamage] BP_I_Sandbag_80 for 115.000000 damage (type=BP_Fragmentation_DamageType_C) direct hit = 0',
        ]
        events = await self._run_parser(lines)
        assert len(events) == 2
        assert isinstance(events[0], AdminBroadcast)
        assert isinstance(events[1], DeployableDamaged)
        assert events[1].deployable == "BP_I_Sandbag_80"
        assert events[1].direct_hit is False

    async def test_emits_player_warned(self):
        lines = [
            '[2026.02.02-02.40.44:503][466]LogSquad: ADMIN COMMAND: Remote admin has warned player  Rellmi. Message was "Type !commands to know the server commands." from RCON',
        ]
        events = await self._run_parser(lines)
        assert len(events) == 1
        assert isinstance(events[0], PlayerWarned)
        assert events[0].admin == "Remote admin"
        assert events[0].player.name == "Rellmi"
        assert events[0].source == "RCON"

    async def test_emits_player_kicked(self):
        lines = [
            '[2026.02.02-02.40.56:981][517]LogSquad: ADMIN COMMAND: Remote admin has kicked player  Rellmi. Reason was "Spamming in command chat." from RCON',
        ]
        events = await self._run_parser(lines)
        assert len(events) == 1
        assert isinstance(events[0], PlayerKicked)
        assert events[0].admin == "Remote admin"
        assert events[0].player.name == "Rellmi"
        assert events[0].source == "RCON"

    async def test_emits_player_banned(self):
        lines = [
            '[2026.02.14-09.53.12:293][914]LogOnlineGame: Display: Banning player: ObsidianHorse47 ; Reason = Kupal na admin',
            '[2026.02.14-09.53.12:294][914]LogOnlineGame: Display: Kicking player:  ObsidianHorse47 ; Reason = Banned from the server for 1 Day(s). Admin Reason: Kupal na admin.',
            '[2026.02.14-09.53.12:294][914]LogSquad: ADMIN COMMAND: N/A Banned player 46. [Online IDs= EOS: 00029e5d00e947bbaed1b364814dd427 steam: 76561198061567555]  ObsidianHorse47 for interval -171852224 from RCON',
        ]
        events = await self._run_parser(lines)
        assert len(events) == 1
        assert isinstance(events[0], PlayerBanned)
        assert events[0].admin == "N/A"
        assert events[0].player.name == "ObsidianHorse47"
        assert events[0].duration == "1 Day(s)"
        assert events[0].reason == "Kupal na admin"
        assert events[0].source == "RCON"

    async def test_emits_admin_cam_possess(self):
        lines = [
            '[2026.02.14-05.23.57:674][804]LogSquadTrace: [DedicatedServer]OnPossess(): PC=Callsign (Online IDs: EOS: 00025c44975740ca82effe91ef190757 steam: 76561199267250463) Pawn=BP_DeveloperAdminCam_C_2146619275 FullPath=BP_DeveloperAdminCam_C /SquadAdminTools/Maps/SATSeed/Maps/Tallil/L_SAT_Tallil_Seed_v1.L_SAT_Tallil_Seed_v1:PersistentLevel.BP_DeveloperAdminCam_C_2146619275',
            '[2026.02.14-05.23.57:674][804]LogSquad: Warning: Admin Camera possessed.',
        ]
        events = await self._run_parser(lines)
        assert len(events) == 2
        assert isinstance(events[0], PlayerPossess)
        assert isinstance(events[1], AdminCamPossess)
        assert events[1].admin.name == "Callsign"
        assert events[1].target == "Admin Camera"
        assert events[1].context["pawn_classname"] == "BP_DeveloperAdminCam_C"

    async def test_emits_admin_cam_unpossess(self):
        lines = [
            '[2026.02.02-12.23.29:659][529]LogSquadTrace: [DedicatedServer]OnPossess(): PC=Callsign (Online IDs: EOS: 00025c44975740ca82effe91ef190757 steam: 76561199267250463) Pawn=BP_DeveloperAdminCam_C_2141703157 FullPath=BP_DeveloperAdminCam_C /Game/Maps/Yehorivka/Gameplay_Layers/Yehorivka_RAAS_v2.Yehorivka_RAAS_v2:PersistentLevel.BP_DeveloperAdminCam_C_2141703157',
            '[2026.02.02-12.23.29:660][529]LogSquad: Warning: Admin Camera possessed.',
            '[2026.02.02-12.29.43:890][912]LogSquadTrace: [DedicatedServer]OnUnPossess(): PC=Callsign (Online IDs: EOS: 00025c44975740ca82effe91ef190757 steam: 76561199267250463)',
        ]
        events = await self._run_parser(lines)
        assert len(events) == 3
        assert isinstance(events[0], PlayerPossess)
        assert isinstance(events[1], AdminCamPossess)
        assert isinstance(events[2], AdminCamUnpossess)
        assert events[2].admin.name == "Callsign"
        assert events[2].target == "Admin Camera"
        assert events[2].context["open_chain_id"] == 529
        assert events[2].context["close_chain_id"] == 912

    async def test_emits_teamkill(self):
        lines = [
            "[2026.02.14-00.50.32:400][ 45]LogSquad: Player  PamanPanda has been added to Team 2",
            "[2026.02.14-01.09.56:371][244]LogSquad: Player  Blackburn has been added to Team 2",
            "[2026.02.14-00.52.27:960][412]LogSquadTrace: [DedicatedServer]OnPossess(): PC=PamanPanda (Online IDs: EOS: 000202cd1a3a4c739203a874221393d0 steam: 76561198161847878) Pawn=BP_Soldier_VDV_SquadLeader_Desert_C_2147407760 FullPath=BP_Soldier_VDV_SquadLeader_Desert_C /SquadAdminTools/Maps/SATSeed/Maps/Tallil/L_SAT_Tallil_Seed_v1.L_SAT_Tallil_Seed_v1:PersistentLevel.BP_Soldier_VDV_SquadLeader_Desert_C_2147407760",
            "[2026.02.14-01.11.39:377][810]LogSquadTrace: [DedicatedServer]OnPossess(): PC=Blackburn (Online IDs: EOS: 00024bce20aa414282702cf909896053 steam: 76561198191272778) Pawn=BP_Soldiers_WPMC_SL_05_C_2147379502 FullPath=BP_Soldiers_WPMC_SL_05_C /SquadAdminTools/Maps/SATSeed/Maps/Tallil/L_SAT_Tallil_Seed_v1.L_SAT_Tallil_Seed_v1:PersistentLevel.BP_Soldiers_WPMC_SL_05_C_2147379502",
            "[2026.02.14-01.16.31:277][417]LogSquadTrace: [DedicatedServer]Wound(): Player:[INAF]  PamanPanda KillingDamage=150.000000 from BP_PlayerController_SATSeed_C_2147382416 (Online IDs: EOS: 00024bce20aa414282702cf909896053 steam: 76561198191272778 | Controller ID: BP_PlayerController_SATSeed_C_2147382416) caused by BP_M134_Loach_Dual_C_2147377585",
        ]
        events = await self._run_parser(lines)
        teamkills = [event for event in events if isinstance(event, Teamkill)]
        assert len(teamkills) == 1
        teamkill = teamkills[0]
        assert teamkill.attacker.name == "Blackburn"
        assert teamkill.victim.name == "PamanPanda"
        assert teamkill.weapon == "BP_M134_Loach_Dual_C"

    async def test_emits_teamkill_from_rcon_player_cache(self):
        lines = [
            "[2026.02.14-01.16.31:277][417]LogSquadTrace: [DedicatedServer]Wound(): Player:[INAF]  PamanPanda KillingDamage=150.000000 from BP_PlayerController_SATSeed_C_2147382416 (Online IDs: EOS: 00024bce20aa414282702cf909896053 steam: 76561198191272778 | Controller ID: BP_PlayerController_SATSeed_C_2147382416) caused by BP_M134_Loach_Dual_C_2147377585",
        ]
        players = [
            RconPlayer(
                id=1,
                steam_id="76561198191272778",
                eos_id="00024bce20aa414282702cf909896053",
                name="Blackburn",
                team_id=2,
                squad_id=1,
                is_leader=False,
                role="Rifleman",
            ),
            RconPlayer(
                id=2,
                steam_id="76561198161847878",
                eos_id="000202cd1a3a4c739203a874221393d0",
                name="PamanPanda",
                team_id=2,
                squad_id=1,
                is_leader=False,
                role="Rifleman",
            ),
        ]
        events = await self._run_parser(lines, rcon_players=players)
        teamkills = [event for event in events if isinstance(event, Teamkill)]
        assert len(teamkills) == 1
        assert teamkills[0].attacker.name == "Blackburn"
        assert teamkills[0].victim.name == "PamanPanda"

    async def test_round_ended_uses_cached_winner_and_loser(self):
        lines = [
            '[2026.02.06-20.45.07:818][740]LogSquadGameEvents: Display: Team 1, Irregular Battle Group ( Middle Eastern Insurgents ) has won the match with 2 Tickets on layer Sumari Bala Seed v1 (level Sumari Bala)!',
            '[2026.02.06-20.45.07:818][741]LogSquadGameEvents: Display: Team 2, 21st Division ( Ground Forces of Iran ) has lost the match with 0 Tickets on layer Sumari Bala Seed v1 (level Sumari Bala)!',
            '[2026.02.06-15.18.55:666][475]LogGameState: Match State Changed from InProgress to WaitingPostMatch',
        ]
        events = await self._run_parser(lines)
        assert len(events) == 1
        assert isinstance(events[0], RoundEnded)
        assert events[0].winner is not None
        assert events[0].loser is not None
        assert events[0].winner["tickets"] == 2
        assert events[0].loser["tickets"] == 0

    async def test_new_game_carries_prior_winner(self):
        lines = [
            '[2026.02.06-15.18.55:664][475]LogSquadTrace: [DedicatedServer]DetermineMatchWinner(): Manticore Security Task Force won on Sumari Bala',
            '[2026.02.06-15.19.26:022][383]LogWorld: Bringing World /Game/Maps/Jensens_Range/Gameplay_Layers/Jensens_Range_WPMC-TLF.Jensens_Range_WPMC-TLF up for play (max tick rate 64) at 2026.02.06-15.19.26',
        ]
        events = await self._run_parser(lines)
        assert len(events) == 1
        assert isinstance(events[0], NewGame)
        assert events[0].winner is not None
        assert events[0].winner["winner"] == "Manticore Security Task Force"

    async def _run_parser(
        self,
        lines: list[str],
        rcon_players: list[RconPlayer] | None = None,
    ) -> list[BaseEvent]:
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
            "server_tick_rate", "admin_broadcast", "player_warned", "player_kicked",
            "player_banned", "admin_cam_possess", "admin_cam_unpossess",
            "teamkill", "deployable_damaged",
        ]
        for name in event_names:
            bus.subscribe(name, capture)

        reader = MockLogReader(lines)
        mock_rcon = None
        if rcon_players is not None:
            mock_rcon = AsyncMock()
            mock_rcon.list_players.return_value = rcon_players

        parser = LogParser(
            reader=reader,
            event_bus=bus,
            rcon_client=mock_rcon,
            player_cache_poll_seconds=3600.0,
        )
        await parser.run()
        return collected
