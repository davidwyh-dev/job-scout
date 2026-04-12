from __future__ import annotations

import logging

import requests

from job_scout.config import SearchConfig
from job_scout.models import Job
from job_scout.sources.base import BaseSource

logger = logging.getLogger(__name__)

API_BASE = "https://api.lever.co/v0/postings"


class LeverSource(BaseSource):
    def __init__(self, companies: list[dict]) -> None:
        self._companies = companies

    @property
    def name(self) -> str:
        return "Lever"

    def fetch(self, config: SearchConfig) -> list[Job]:
        all_jobs: list[Job] = []
        for company in self._companies:
            slug = company["slug"]
            company_name = company["name"]
            try:
                jobs = self._fetch_postings(slug, company_name, config)
                all_jobs.extend(jobs)
                logger.info("Lever [%s]: %d matching jobs", company_name, len(jobs))
            except Exception as e:
                logger.error("Lever [%s] failed: %s", company_name, e)
        return all_jobs

    def _fetch_postings(self, slug: str, company_name: str, config: SearchConfig) -> list[Job]:
        resp = requests.get(f"{API_BASE}/{slug}", timeout=30)
        resp.raise_for_status()
        postings = resp.json()

        jobs: list[Job] = []
        for posting in postings:
            title = posting.get("text", "")
            if not _matches_title(title, config):
                continue

            categories = posting.get("categories", {})
            location = categories.get("location", "")
            workplace_type = posting.get("workplaceType", "")

            is_remote = workplace_type == "remote" or "remote" in location.lower()
            location_match = is_remote or _matches_location(location, config)

            if not location_match:
                continue

            description = posting.get("descriptionPlain", "")
            snippet = description[:300].strip() if description else ""

            salary = None
            salary_range = posting.get("salaryRange", {})
            if salary_range and salary_range.get("min") is not None:
                try:
                    parts = []
                    if salary_range.get("min") is not None:
                        parts.append(f"${int(salary_range['min']):,}")
                    if salary_range.get("max") is not None:
                        parts.append(f"${int(salary_range['max']):,}")
                    salary = " - ".join(parts)
                except (ValueError, TypeError):
                    pass

            jobs.append(Job(
                id=f"lever:{slug}:{posting['id']}",
                title=title,
                company=company_name,
                location=location,
                is_remote=is_remote,
                url=posting.get("hostedUrl", f"https://jobs.lever.co/{slug}/{posting['id']}"),
                source=f"lever:{slug}",
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
