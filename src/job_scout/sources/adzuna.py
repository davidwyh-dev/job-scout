from __future__ import annotations

import logging

import requests

from job_scout.config import SearchConfig
from job_scout.models import Job
from job_scout.sources.base import BaseSource

logger = logging.getLogger(__name__)

API_BASE = "https://api.adzuna.com/v1/api/jobs/us/search"


class AdzunaSource(BaseSource):
    def __init__(self, app_id: str = "", app_key: str = "") -> None:
        self._app_id = app_id
        self._app_key = app_key

    @property
    def name(self) -> str:
        return "Adzuna"

    def fetch(self, config: SearchConfig) -> list[Job]:
        if not self._app_id or not self._app_key:
            logger.warning("Adzuna credentials not configured — skipping")
            return []

        all_jobs: list[Job] = []

        for title_query in config.titles[:3]:
            for location in config.locations[:2]:
                try:
                    jobs = self._search(title_query, location, config)
                    all_jobs.extend(jobs)
                except Exception as e:
                    logger.error("Adzuna [%s / %s] failed: %s", title_query, location, e)

        if config.include_remote:
            for title_query in config.titles[:3]:
                try:
                    jobs = self._search(title_query, "USA", config, remote=True)
                    all_jobs.extend(jobs)
                except Exception as e:
                    logger.error("Adzuna [%s / remote] failed: %s", title_query, e)

        return all_jobs

    def _search(
        self, what: str, where: str, config: SearchConfig, remote: bool = False
    ) -> list[Job]:
        params: dict = {
            "app_id": self._app_id,
            "app_key": self._app_key,
            "what": what,
            "where": where,
            "results_per_page": min(config.results_per_source, 50),
            "max_days_old": config.hours_old // 24 or 2,
            "sort_by": "date",
        }
        if remote:
            params["what"] = f"{what} remote"

        resp = requests.get(f"{API_BASE}/1", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        jobs: list[Job] = []
        for result in data.get("results", []):
            title = result.get("title", "")
            if not _matches_title(title, config):
                continue

            location_str = result.get("location", {}).get("display_name", "")
            is_remote = "remote" in title.lower() or "remote" in location_str.lower()

            salary_min = result.get("salary_min")
            salary_max = result.get("salary_max")
            salary = None
            if salary_min or salary_max:
                parts = []
                if salary_min:
                    parts.append(f"${int(salary_min):,}")
                if salary_max:
                    parts.append(f"${int(salary_max):,}")
                salary = " - ".join(parts)

            description = result.get("description", "")

            jobs.append(Job(
                id=f"adzuna:{result['id']}",
                title=title,
                company=result.get("company", {}).get("display_name", ""),
                location=location_str,
                is_remote=is_remote,
                url=result.get("redirect_url", ""),
                source="adzuna",
                description_snippet=description[:300].strip(),
                salary_range=salary,
            ))

        logger.info("Adzuna [%s / %s]: %d jobs", what, where, len(jobs))
        return jobs


def _matches_title(title: str, config: SearchConfig) -> bool:
    title_lower = title.lower()
    for exclude in config.title_exclude:
        if exclude.lower() in title_lower:
            return False
    for include in config.titles:
        if include.lower() in title_lower:
            return True
    return False
