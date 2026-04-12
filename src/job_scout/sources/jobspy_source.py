from __future__ import annotations

import logging
from datetime import datetime, timezone

from job_scout.config import SearchConfig
from job_scout.models import Job
from job_scout.sources.base import BaseSource

logger = logging.getLogger(__name__)


class JobSpySource(BaseSource):
    def __init__(self, sites: list[str] | None = None) -> None:
        self._sites = sites or ["linkedin", "indeed", "glassdoor", "google"]

    @property
    def name(self) -> str:
        return "JobSpy"

    def fetch(self, config: SearchConfig) -> list[Job]:
        try:
            from jobspy import scrape_jobs
        except ImportError:
            logger.error("python-jobspy not installed — skipping JobSpy source")
            return []

        all_jobs: list[Job] = []

        # Query 1: location-based search
        for location in config.locations[:2]:  # Limit to avoid rate limits
            try:
                results = scrape_jobs(
                    site_name=self._sites,
                    search_term=" OR ".join(config.titles[:3]),
                    location=location,
                    results_wanted=config.results_per_source,
                    hours_old=config.hours_old,
                    country_indeed="USA",
                )
                all_jobs.extend(self._convert(results))
                logger.info("JobSpy [%s]: fetched %d jobs", location, len(results))
            except Exception as e:
                logger.error("JobSpy [%s] failed: %s", location, e)

        # Query 2: remote search
        if config.include_remote:
            try:
                results = scrape_jobs(
                    site_name=self._sites,
                    search_term=" OR ".join(config.titles[:3]),
                    location="USA",
                    is_remote=True,
                    results_wanted=config.results_per_source,
                    hours_old=config.hours_old,
                    country_indeed="USA",
                )
                all_jobs.extend(self._convert(results))
                logger.info("JobSpy [remote]: fetched %d jobs", len(results))
            except Exception as e:
                logger.error("JobSpy [remote] failed: %s", e)

        return all_jobs

    def _convert(self, df) -> list[Job]:
        jobs: list[Job] = []
        for _, row in df.iterrows():
            url = str(row.get("job_url", ""))
            if not url:
                continue

            date_posted = None
            raw_date = row.get("date_posted")
            if raw_date is not None:
                try:
                    if hasattr(raw_date, "to_pydatetime"):
                        date_posted = raw_date.to_pydatetime().replace(tzinfo=timezone.utc)
                    else:
                        date_posted = datetime.fromisoformat(str(raw_date)).replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass

            description = str(row.get("description", ""))
            snippet = description[:300].strip() if description else ""

            salary_parts = []
            for col in ("min_amount", "max_amount"):
                val = row.get(col)
                if val is not None and str(val) not in ("nan", "None", ""):
                    try:
                        salary_parts.append(f"${int(float(str(val))):,}")
                    except (ValueError, TypeError):
                        pass
            salary_range = " - ".join(salary_parts) if salary_parts else None

            is_remote = bool(row.get("is_remote", False))
            site = str(row.get("site", "unknown"))

            jobs.append(Job(
                id=f"jobspy:{site}:{url}",
                title=str(row.get("title", "")),
                company=str(row.get("company_name", row.get("company", ""))),
                location=str(row.get("location", "")),
                is_remote=is_remote,
                url=url,
                source=f"jobspy:{site}",
                date_posted=date_posted,
                description_snippet=snippet,
                salary_range=salary_range,
                job_type=str(row.get("job_type", "")) or None,
            ))
        return jobs
