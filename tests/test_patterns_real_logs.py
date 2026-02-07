"""Validate regex patterns against real Squad log files.

Skipped if sample files don't exist (they're gitignored).
"""

import pytest
from pathlib import Path

from squadpy.log_parser.event_store import EventStore
from squadpy.log_parser.patterns import match_line

SAMPLES_DIR = Path(__file__).parent / "fixtures" / "samples"


@pytest.mark.skipif(
    not SAMPLES_DIR.exists() or not list(SAMPLES_DIR.glob("*.log")),
    reason="No sample log files available",
)
class TestRealLogs:
    @pytest.fixture(params=list(SAMPLES_DIR.glob("*.log")) if SAMPLES_DIR.exists() else [])
    def log_file(self, request):
        return request.param

    def test_no_crashes(self, log_file):
        """Every line should either match a pattern or be silently skipped."""
        store = EventStore()
        match_count = 0
        line_count = 0
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line_count += 1
                result = match_line(line.rstrip(), store)
                if result is not None:
                    match_count += 1
        # Sanity: we should match at least some lines in a real log
        assert match_count > 0, f"No matches in {log_file.name} ({line_count} lines)"
        print(f"\n{log_file.name}: {match_count}/{line_count} lines matched")
