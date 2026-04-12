from __future__ import annotations

import re
import logging
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from job_scout.models import Job

logger = logging.getLogger(__name__)

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "source", "ref", "refId", "trk", "trackingId", "currentJobId",
    "eBP", "refId", "position", "pageNum",
}

_COMPANY_SUFFIXES = re.compile(
    r"\s*,?\s*\b(inc\.?|ltd\.?|llc|co\.?|corp\.?|corporation|company|technologies|technology|labs?|group)\s*$",
    re.IGNORECASE,
)


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {k: v for k, v in params.items() if k.lower() not in _TRACKING_PARAMS}
    clean_query = urlencode(filtered, doseq=True)
    normalized = urlunparse((
        parsed.scheme,
        parsed.netloc.lower(),
        parsed.path.rstrip("/"),
        parsed.params,
        clean_query,
        "",
    ))
    return normalized


def _normalize_company(name: str) -> str:
    name = name.strip().lower()
    name = _COMPANY_SUFFIXES.sub("", name)
    return name.strip()


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())


def _dedup_key(job: Job) -> str:
    return f"{_normalize_company(job.company)}|{_normalize_title(job.title)}"


def deduplicate(jobs: list[Job]) -> list[Job]:
    seen_urls: dict[str, Job] = {}
    seen_keys: dict[str, Job] = {}
    results: list[Job] = []

    for job in jobs:
        norm_url = _normalize_url(job.url)

        # Layer 1: exact URL match
        if norm_url in seen_urls:
            existing = seen_urls[norm_url]
            if job.richness_score > existing.richness_score:
                results.remove(existing)
                results.append(job)
                seen_urls[norm_url] = job
                seen_keys[_dedup_key(job)] = job
            continue

        # Layer 2: fuzzy title + company match
        key = _dedup_key(job)
        if key in seen_keys:
            existing = seen_keys[key]
            if job.richness_score > existing.richness_score:
                results.remove(existing)
                results.append(job)
                seen_urls[norm_url] = job
                seen_keys[key] = job
            continue

        seen_urls[norm_url] = job
        seen_keys[key] = job
        results.append(job)

    deduped = len(jobs) - len(results)
    if deduped:
        logger.info("Deduplication removed %d duplicates (%d -> %d)", deduped, len(jobs), len(results))

    return results
