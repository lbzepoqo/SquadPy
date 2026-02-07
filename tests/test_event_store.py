"""Tests for the EventStore cross-line correlation state."""

from squadpy.log_parser.event_store import EventStore


class TestEventStore:
    def test_initial_state(self):
        store = EventStore()
        assert store.session == {}
        assert store.players == {}
        assert store.join_requests == {}
        assert store.disconnected == {}
        assert store.round_winner is None
        assert store.round_loser is None

    def test_clear_resets_all(self):
        store = EventStore()
        store.session["test"] = {"data": 1}
        store.players["eos123"] = {"name": "Player"}
        store.join_requests[42] = {"ip": "1.2.3.4"}
        store.disconnected["eos123"] = True
        store.round_winner = {"team": "1"}
        store.round_loser = {"team": "2"}
        store.clear()
        assert store.session == {}
        assert store.players == {}
        assert store.join_requests == {}
        assert store.disconnected == {}
        assert store.round_winner is None
        assert store.round_loser is None

    def test_session_stores_damage_correlation(self):
        store = EventStore()
        store.session["VictimName"] = {
            "attacker_eos_id": "abc",
            "weapon": "BP_Frag_C",
        }
        assert store.session["VictimName"]["weapon"] == "BP_Frag_C"

    def test_join_request_by_chain_id(self):
        store = EventStore()
        store.join_requests[401] = {
            "controller_name": "BP_PlayerController_C_123",
            "ip": "1.2.3.4",
            "eos_id": "abc",
            "steam_id": "123",
        }
        player = store.join_requests.pop(401)
        assert player["eos_id"] == "abc"
        assert 401 not in store.join_requests

    def test_round_tickets_storage(self):
        store = EventStore()
        store.round_winner = {"team": "1", "subfaction": "MEA", "tickets": 50}
        store.round_loser = {"team": "2", "subfaction": "USA", "tickets": 0}
        assert store.round_winner["tickets"] == 50
