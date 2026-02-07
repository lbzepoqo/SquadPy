"""Utility for parsing Squad Online IDs (EOS + Steam) from log lines."""

import re

_EOS_RE = re.compile(r"EOS:\s*([0-9a-f]{32})")
_STEAM_RE = re.compile(r"steam:\s*(\d{17})")


def parse_online_ids(raw: str) -> dict[str, str]:
    """Parse an Online IDs string into eos_id and steam_id.

    Input format: 'EOS: <32hex> steam: <17digits>'
    Returns: {'eos_id': '...', 'steam_id': '...'}
    Missing IDs default to empty string.
    """
    eos_match = _EOS_RE.search(raw)
    steam_match = _STEAM_RE.search(raw)
    return {
        "eos_id": eos_match.group(1) if eos_match else "",
        "steam_id": steam_match.group(1) if steam_match else "",
    }
