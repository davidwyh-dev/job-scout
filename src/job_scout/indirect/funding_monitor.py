from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import feedparser

logger = logging.getLogger(__name__)

# Pattern: "CompanyName raises/closes/secures $XM..."
_FUNDING_PATTERN = re.compile(
    r"^(.+?)\s+(?:raises?|closes?|secures?|announces?|lands?|gets?|nabs?)\s",
    re.IGNORECASE,
)

# Clean up extracted names
_NAME_CLEANUP = re.compile(r"\s*[-–—:|]\s*$")


def fetch_recently_funded_companies(
    rss_feeds: list[dict],
    funding_keywords: list[str],
    max_age_hours: int = 72,
) -> list[str]:
    """Parse RSS feeds and extract company names from funding-related headlines."""
    companies: list[str] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    keywords_lower = [kw.lower() for kw in funding_keywords]

    for feed_cfg in rss_feeds:
        url = feed_cfg["url"]
        feed_name = feed_cfg.get("name", url)
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                # Check age
                published = entry.get("published_parsed")
                if published:
                    entry_time = datetime(*published[:6], tzinfo=timezone.utc)
                    if entry_time < cutoff:
                        continue

                title = entry.get("title", "")
                summary = entry.get("summary", "")
                combined = f"{title} {summary}".lower()

                # Check if it's about funding
                if not any(kw in combined for kw in keywords_lower):
                    continue

                # Extract company name from headline
                name = _extract_company_name(title)
                if name and len(name) > 1 and len(name) < 100:
                    companies.append(name)
                    logger.info("Funding news [%s]: %s -> company: %s", feed_name, title[:80], name)

        except Exception as e:
            logger.error("RSS feed [%s] failed: %s", feed_name, e)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for name in companies:
        key = name.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(name)

    logger.info("Found %d recently funded companies from RSS", len(unique))
    return unique


def _extract_company_name(headline: str) -> str | None:
    """Extract company name from a funding headline.

    Examples:
        "Acme Corp raises $50M Series B" -> "Acme Corp"
        "Startup XYZ closes $20M round" -> "Startup XYZ"
        "TechCrunch: Acme raises $10M" -> "Acme"
    """
    # Strip common prefixes like "TechCrunch: " or "Exclusive: "
    headline = re.sub(r"^(?:exclusive|breaking|report|update|watch)\s*:\s*", "", headline, flags=re.IGNORECASE)

    match = _FUNDING_PATTERN.match(headline)
    if match:
        name = match.group(1).strip()
        name = _NAME_CLEANUP.sub("", name)
        # Remove surrounding quotes
        name = name.strip("'\"''""\u2018\u2019\u201c\u201d")
        return name.strip()

    return None
