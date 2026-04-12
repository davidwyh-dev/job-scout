from __future__ import annotations

from abc import ABC, abstractmethod

from job_scout.config import SearchConfig
from job_scout.models import Job


class BaseSource(ABC):
    @abstractmethod
    def fetch(self, config: SearchConfig) -> list[Job]:
        """Fetch jobs matching the search config.

        Implementations must not raise — return an empty list on failure
        and log the error internally.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable source name for logging."""
