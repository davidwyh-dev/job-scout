from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Job:
    id: str
    title: str
    company: str
    location: str
    is_remote: bool
    url: str
    source: str
    date_posted: datetime | None = None
    description_snippet: str = ""
    salary_range: str | None = None
    job_type: str | None = None
    discovered_via: str | None = None

    @property
    def richness_score(self) -> int:
        """Higher score = more complete data. Used for dedup tie-breaking."""
        score = 0
        if self.description_snippet:
            score += len(self.description_snippet)
        if self.salary_range:
            score += 50
        if self.date_posted:
            score += 20
        if self.job_type:
            score += 10
        return score
