from __future__ import annotations

import logging

import requests

from job_scout.config import SearchConfig
from job_scout.models import Job
from job_scout.sources.base import BaseSource

logger = logging.getLogger(__name__)

API_BASE = "https://api.ashbyhq.com/posting-api/job-board"


class AshbySource(BaseSource):
    def __init__(self, companies: list[dict]) -> None:
        self._companies = companies

    @property
    def name(self) -> str:
        return "Ashby"

    def fetch(self, config: SearchConfig) -> list[Job]:
        all_jobs: list[Job] = []
        for company in self._companies:
            slug = company["slug"]
            company_name = company["name"]
            try:
                jobs = self._fetch_board(slug, company_name, config)
                all_jobs.extend(jobs)
                logger.info("Ashby [%s]: %d matching jobs", company_name, len(jobs))
            except Exception as e:
                logger.error("Ashby [%s] failed: %s", company_name, e)
        return all_jobs

    def _fetch_board(self, slug: str, company_name: str, config: SearchConfig) -> list[Job]:
        resp = requests.get(
            f"{API_BASE}/{slug}",
            params={"includeCompensation": "true"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        jobs: list[Job] = []
        for posting in data.get("jobs", []):
            title = posting.get("title", "")
            if not _matches_title(title, config):
                continue

            location = posting.get("location", "")
            is_remote = posting.get("isRemote", False) or "remote" in location.lower()
            location_match = is_remote or _matches_location(location, config)

            if not location_match:
                continue

            description = posting.get("descriptionPlain", "")
            snippet = description[:300].strip() if description else ""

            salary = None
            compensation = posting.get("compensation")
            if compensation:
                try:
                    comp_str = compensation.get("compensationTierSummary", "")
                    if comp_str:
                        salary = comp_str
                except (AttributeError, TypeError):
                    pass

            posting_url = posting.get("jobUrl", f"https://jobs.ashbyhq.com/{slug}/{posting.get('id', '')}")

            jobs.append(Job(
                id=f"ashby:{slug}:{posting['id']}",
                title=title,
                company=company_name,
                location=location,
                is_remote=is_remote,
                url=posting_url,
                source=f"ashby:{slug}",
                description_snippet=snippet,
                salary_range=salary,
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
