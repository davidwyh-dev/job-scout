from __future__ import annotations

import logging
import re

import requests

logger = logging.getLogger(__name__)

_SLUG_CLEANUP = re.compile(r"[^a-z0-9-]")

# ATS endpoints to probe
_ATS_PROBES = [
    {
        "platform": "greenhouse",
        "url_template": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    },
    {
        "platform": "lever",
        "url_template": "https://api.lever.co/v0/postings/{slug}",
    },
    {
        "platform": "ashby",
        "url_template": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    },
]


def resolve_ats_boards(
    company_names: list[str],
    already_known: dict[str, dict] | None = None,
) -> list[dict]:
    """For each company name, try to discover their ATS job board.

    Returns list of dicts: {"platform": ..., "slug": ..., "company": ...}
    """
    already_known = already_known or {}
    discovered: list[dict] = []

    for name in company_names:
        slug = _name_to_slug(name)
        if not slug:
            continue

        # Skip if we already know this board
        if slug in already_known:
            continue

        # Try each ATS platform
        board = _probe_slug(slug, name)
        if board:
            discovered.append(board)

        # Also try without hyphens (e.g., "acme corp" -> "acmecorp")
        alt_slug = slug.replace("-", "")
        if alt_slug != slug and alt_slug not in already_known:
            board = _probe_slug(alt_slug, name)
            if board:
                discovered.append(board)

    logger.info("Discovered %d new ATS boards from %d companies", len(discovered), len(company_names))
    return discovered


def _name_to_slug(name: str) -> str:
    slug = name.lower().strip()
    slug = _SLUG_CLEANUP.sub("-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def _probe_slug(slug: str, company_name: str) -> dict | None:
    for ats in _ATS_PROBES:
        url = ats["url_template"].format(slug=slug)
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Verify it actually has jobs (not just a 200 with empty data)
                has_jobs = False
                if isinstance(data, list) and len(data) > 0:
                    has_jobs = True
                elif isinstance(data, dict) and data.get("jobs"):
                    has_jobs = True

                if has_jobs:
                    logger.info(
                        "Discovered %s board for '%s' (slug: %s)",
                        ats["platform"], company_name, slug,
                    )
                    return {
                        "platform": ats["platform"],
                        "slug": slug,
                        "company": company_name,
                    }
        except (requests.RequestException, ValueError):
            continue

    return None
