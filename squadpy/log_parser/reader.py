"""Abstract base class for log readers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LogReader(ABC):
    """Base class for log readers that tail Squad server log files."""

    @abstractmethod
    async def start(self) -> None:
        """Initialize and prepare for tailing."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop tailing and clean up resources."""

    @abstractmethod
    def tail(self) -> AsyncIterator[str]:
        """Yield new log lines as they appear."""
