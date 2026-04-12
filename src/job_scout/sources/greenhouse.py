from __future__ import annotations

import logging
import re

import requests

from job_scout.config import SearchConfig
from job_scout.models import Job
from job_scout.sources.base import BaseSource

logger = logging.getLogger(__name__)

API_BASE = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseSource(BaseSource):
    def __init__(self, companies: list[dict]) -> None:
        self._companies = companies

    @property
    def name(self) -> str:
        return "Greenhouse"

    def fetch(self, config: SearchConfig) -> list[Job]:
        all_jobs: list[Job] = []
        for company in self._companies:
            token = company["board_token"]
            company_name = company["name"]
            try:
                jobs = self._fetch_board(token, company_name, config)
                all_jobs.extend(jobs)
                logger.info("Greenhouse [%s]: %d matching jobs", company_name, len(jobs))
            except Exception as e:
                logger.error("Greenhouse [%s] failed: %s", company_name, e)
        return all_jobs

    def _fetch_board(self, token: str, company_name: str, config: SearchConfig) -> list[Job]:
        resp = requests.get(f"{API_BASE}/{token}/jobs", params={"content": "true"}, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        jobs: list[Job] = []
        for posting in data.get("jobs", []):
            title = posting.get("title", "")
            if not _matches_title(title, config):
                continue

            location_name = ""
            loc_data = posting.get("location", {})
            if loc_data:
                location_name = loc_data.get("name", "")

            is_remote = "remote" in location_name.lower()
            location_match = is_remote or _matches_location(location_name, config)

            if not location_match:
                continue

            content = posting.get("content", "")
            snippet = _html_to_text(content)[:300].strip()

            jobs.append(Job(
                id=f"greenhouse:{token}:{posting['id']}",
                title=title,
                company=company_name,
                location=location_name,
                is_remote=is_remote,
                url=posting.get("absolute_url", f"https://boards.greenhouse.io/{token}/jobs/{posting['id']}"),
                source=f"greenhouse:{token}",
                description_snippet=snippet,
            ))
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


def _matches_location(location: str, config: SearchConfig) -> bool:
    loc_lower = location.lower()
    if config.include_remote and "remote" in loc_lower:
        return True
    for loc in config.locations:
        if loc.lower() in loc_lower:
            return True
    return False


def _html_to_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
