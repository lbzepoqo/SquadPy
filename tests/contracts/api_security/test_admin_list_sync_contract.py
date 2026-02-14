"""Contract tests for admin list sync precedence and conflict handling."""

import pytest

from squadpy.admin_lists import (
    AdminListEntry,
    AdminListSource,
    AdminListSyncEngine,
)

pytestmark = [pytest.mark.contract, pytest.mark.api_security, pytest.mark.p1]


class StaticSource(AdminListSource):
    def __init__(self, *, name: str, entries: list[AdminListEntry]):
        super().__init__(name=name)
        self._entries = entries

    async def fetch(self) -> list[AdminListEntry]:
        return list(self._entries)


async def test_admin_list_sync_precedence_contract() -> None:
    """P1-CONN-004: precedence order determines winner and records conflicts."""
    local = StaticSource(
        name="local",
        entries=[AdminListEntry("76561198000000999", "owner", "local", "local")],
    )
    remote = StaticSource(
        name="remote",
        entries=[AdminListEntry("76561198000000999", "moderator", "remote", "remote")],
    )
    sftp = StaticSource(
        name="sftp",
        entries=[AdminListEntry("76561198000000999", "trial_admin", "sftp", "sftp")],
    )

    result = await AdminListSyncEngine(
        sources=[local, remote, sftp],
        precedence=["local", "remote", "sftp"],
    ).sync()

    merged = result.entries["76561198000000999"]
    assert merged.role == "owner"
    assert merged.source == "local"
    assert len(result.conflicts) == 2
    assert result.conflicts[0].chosen_source == "local"

