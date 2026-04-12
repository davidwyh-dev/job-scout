from __future__ import annotations

import logging

import requests

from job_scout.config import SearchConfig
from job_scout.models import Job
from job_scout.sources.base import BaseSource

logger = logging.getLogger(__name__)

API_BASE = "https://www.themuse.com/api/public/jobs"


class TheMuseSource(BaseSource):
    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "The Muse"

    def fetch(self, config: SearchConfig) -> list[Job]:
        all_jobs: list[Job] = []

        try:
            # The Muse uses specific category and location params
            params: dict = {
                "category": "Product",
                "level": "Mid Level,Senior Level",
                "page": 0,
            }
            if self._api_key:
                params["api_key"] = self._api_key

            # Fetch NYC jobs
            params["location"] = "New York, NY"
            all_jobs.extend(self._fetch_page(params, config))

            # Fetch remote jobs
            if config.include_remote:
                params["location"] = "Flexible / Remote"
                all_jobs.extend(self._fetch_page(params, config))

        except Exception as e:
            logger.error("The Muse failed: %s", e)

        return all_jobs

    def _fetch_page(self, params: dict, config: SearchConfig) -> list[Job]:
        jobs: list[Job] = []
        # Fetch up to 3 pages (20 results per page)
        for page in range(3):
            params["page"] = page
            try:
                resp = requests.get(API_BASE, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error("The Muse page %d failed: %s", page, e)
                break

            results = data.get("results", [])
            if not results:
                break

            for posting in results:
                title = posting.get("name", "")
                if not _matches_title(title, config):
                    continue

                company_obj = posting.get("company", {})
                company_name = company_obj.get("name", "") if company_obj else ""

                locations = posting.get("locations", [])
                location_str = ", ".join(loc.get("name", "") for loc in locations) if locations else ""
                is_remote = "remote" in location_str.lower() or "flexible" in location_str.lower()

                refs = posting.get("refs", {})
                url = refs.get("landing_page", "")

                snippet = ""
                contents = posting.get("contents", "")
                if contents:
                    import re
                    text = re.sub(r"<[^>]+>", " ", contents)
                    text = re.sub(r"\s+", " ", text).strip()
                    snippet = text[:300]

                jobs.append(Job(
                    id=f"muse:{posting['id']}",
                    title=title,
                    company=company_name,
                    location=location_str,
                    is_remote=is_remote,
                    url=url,
                    source="the_muse",
                    description_snippet=snippet,
                ))

            if page >= data.get("page_count", 1) - 1:
                break

        logger.info("The Muse [%s]: fetched %d jobs", params.get("location", "?"), len(jobs))
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
