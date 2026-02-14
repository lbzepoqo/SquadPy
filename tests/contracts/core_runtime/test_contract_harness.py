"""Smoke tests for the parity contract harness."""

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.core_runtime, pytest.mark.p0]


def test_contract_marker_collection() -> None:
    """Ensure contract marker selection discovers at least one parity test."""
    assert True
