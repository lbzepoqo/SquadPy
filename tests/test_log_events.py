"""Tests for log parser event dataclasses."""

from squadpy.events.types import (
    PlayerID,
    PlayerConnected,
    PlayerDisconnected,
    JoinSucceeded,
    PlayerDamaged,
    PlayerWounded,
    PlayerDied,
    Teamkill,
    SquadCreated,
    PlayerRevived,
    PlayerPossess,
    PlayerUnpossess,
    NewGame,
    RoundEnded,
    RoundTickets,
    ServerTickRate,
    AdminBroadcast,
    PlayerWarned,
    PlayerKicked,
    PlayerBanned,
    AdminCamPossess,
    AdminCamUnpossess,
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


class TestPlayerWarned:
    def test_event_name(self):
        e = PlayerWarned()
        assert e.event_name == "player_warned"

    def test_fields(self):
        pid = PlayerID(name="Rellmi")
        e = PlayerWarned(
            admin="Remote admin",
            player=pid,
            reason="Welcome to the server.",
            source="RCON",
        )
        assert e.admin == "Remote admin"
        assert e.player.name == "Rellmi"
        assert e.reason == "Welcome to the server."
        assert e.source == "RCON"


class TestPlayerKicked:
    def test_event_name(self):
        e = PlayerKicked()
        assert e.event_name == "player_kicked"

    def test_fields(self):
        pid = PlayerID(name="Rellmi")
        e = PlayerKicked(
            admin="Remote admin",
            player=pid,
            reason="Spamming in command chat.",
            source="RCON",
        )
        assert e.admin == "Remote admin"
        assert e.player.name == "Rellmi"
        assert e.reason == "Spamming in command chat."
        assert e.source == "RCON"


class TestPlayerBanned:
    def test_event_name(self):
        e = PlayerBanned()
        assert e.event_name == "player_banned"

    def test_fields(self):
        pid = PlayerID(name="Rellmi")
        e = PlayerBanned(
            admin="Remote admin",
            player=pid,
            duration="1d",
            reason="Cheating",
            source="RCON",
        )
        assert e.admin == "Remote admin"
        assert e.player.name == "Rellmi"
        assert e.duration == "1d"
        assert e.reason == "Cheating"
        assert e.source == "RCON"


class TestAdminCamPossess:
    def test_event_name(self):
        e = AdminCamPossess()
        assert e.event_name == "admin_cam_possess"

    def test_fields(self):
        admin = PlayerID(
            eos_id="00025c44975740ca82effe91ef190757",
            steam_id="76561199267250463",
            name="Callsign",
        )
        e = AdminCamPossess(
            admin=admin,
            target="Admin Camera",
            context={"pawn_classname": "BP_DeveloperAdminCam_C"},
        )
        assert e.admin.name == "Callsign"
        assert e.target == "Admin Camera"
        assert e.context["pawn_classname"] == "BP_DeveloperAdminCam_C"


class TestAdminCamUnpossess:
    def test_event_name(self):
        e = AdminCamUnpossess()
        assert e.event_name == "admin_cam_unpossess"

    def test_fields(self):
        admin = PlayerID(
            eos_id="00025c44975740ca82effe91ef190757",
            steam_id="76561199267250463",
            name="Callsign",
        )
        e = AdminCamUnpossess(
            admin=admin,
            target="Admin Camera",
            context={"open_chain_id": 529, "close_chain_id": 912},
        )
        assert e.admin.name == "Callsign"
        assert e.target == "Admin Camera"
        assert e.context["open_chain_id"] == 529
        assert e.context["close_chain_id"] == 912


class TestTeamkill:
    def test_event_name(self):
        e = Teamkill()
        assert e.event_name == "teamkill"

    def test_fields(self):
        attacker = PlayerID(
            eos_id="00024bce20aa414282702cf909896053",
            steam_id="76561198191272778",
            name="Blackburn",
        )
        victim = PlayerID(
            eos_id="000202cd1a3a4c739203a874221393d0",
            steam_id="76561198161847878",
            name="PamanPanda",
        )
        e = Teamkill(
            attacker=attacker,
            victim=victim,
            weapon="BP_M134_Loach_Dual_C",
        )
        assert e.attacker.name == "Blackburn"
        assert e.victim.name == "PamanPanda"
        assert e.weapon == "BP_M134_Loach_Dual_C"


class TestSquadCreated:
    def test_event_name(self):
        e = SquadCreated()
        assert e.event_name == "squad_created"

    def test_fields(self):
        creator = PlayerID(
            eos_id="00029e5d00e947bbaed1b364814dd427",
            steam_id="76561198061567555",
            name="ObsidianHorse47",
        )
        e = SquadCreated(
            team_id=1,
            team_name="United States Army",
            squad_id=1,
            squad_name="Squad 1",
            creator=creator,
        )
        assert e.team_id == 1
        assert e.team_name == "United States Army"
        assert e.squad_id == 1
        assert e.squad_name == "Squad 1"
        assert e.creator.name == "ObsidianHorse47"
