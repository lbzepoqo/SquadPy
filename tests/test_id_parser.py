"""Tests for Online ID parsing utility."""

from squadpy.log_parser.id_parser import parse_online_ids


class TestParseOnlineIds:
    def test_both_eos_and_steam(self):
        raw = "EOS: 000250f5e359453bb9ad313db051f19e steam: 76561198376713392"
        result = parse_online_ids(raw)
        assert result == {
            "eos_id": "000250f5e359453bb9ad313db051f19e",
            "steam_id": "76561198376713392",
        }

    def test_eos_only(self):
        raw = "EOS: 000250f5e359453bb9ad313db051f19e"
        result = parse_online_ids(raw)
        assert result == {
            "eos_id": "000250f5e359453bb9ad313db051f19e",
            "steam_id": "",
        }

    def test_invalid_returns_empty(self):
        raw = "INVALID"
        result = parse_online_ids(raw)
        assert result == {"eos_id": "", "steam_id": ""}

    def test_empty_string(self):
        raw = ""
        result = parse_online_ids(raw)
        assert result == {"eos_id": "", "steam_id": ""}

    def test_with_trailing_space(self):
        raw = "EOS: 0002ded45cb5412e8d5c7833a92d36b3 steam: 76561198376630934 "
        result = parse_online_ids(raw)
        assert result["eos_id"] == "0002ded45cb5412e8d5c7833a92d36b3"
        assert result["steam_id"] == "76561198376630934"
