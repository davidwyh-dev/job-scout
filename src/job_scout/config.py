from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SearchConfig:
    titles: list[str]
    title_exclude: list[str]
    locations: list[str]
    include_remote: bool
    hours_old: int
    results_per_source: int
    exclude_public_companies: bool = False
    company_exclude: list[str] = field(default_factory=list)


@dataclass
class AppConfig:
    search: SearchConfig
    sources: dict
    ats_companies: dict
    indirect_sources: dict
    email: dict
    state: dict


def _find_project_root() -> Path:
    """Walk up from this file to find the directory containing config/."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "config").is_dir():
            return current
        current = current.parent
    raise FileNotFoundError("Could not find project root (directory containing config/)")


def load_config(path: str | None = None) -> AppConfig:
    if path is None:
        root = _find_project_root()
        path = str(root / "config" / "config.yaml")

    with open(path) as f:
        raw = yaml.safe_load(f)

    search = SearchConfig(
        titles=raw["search"]["titles"],
        title_exclude=raw["search"].get("title_exclude", []),
        locations=raw["search"]["locations"],
        include_remote=raw["search"].get("include_remote", True),
        hours_old=raw["search"].get("hours_old", 48),
        results_per_source=raw["search"].get("results_per_source", 50),
        exclude_public_companies=raw["search"].get("exclude_public_companies", False),
        company_exclude=raw["search"].get("company_exclude", []),
    )

    email_cfg = raw["email"]
    email_cfg["smtp_password"] = os.environ.get("GMAIL_APP_PASSWORD", "")

    sources = raw.get("sources", {})
    # Inject API keys from environment
    if "the_muse" in sources:
        sources["the_muse"]["api_key"] = os.environ.get("MUSE_API_KEY", "")
    if "adzuna" in sources:
        sources["adzuna"]["app_id"] = os.environ.get("ADZUNA_APP_ID", "")
        sources["adzuna"]["app_key"] = os.environ.get("ADZUNA_APP_KEY", "")

    return AppConfig(
        search=search,
        sources=sources,
        ats_companies=raw.get("ats_companies", {}),
        indirect_sources=raw.get("indirect_sources", {"enabled": False}),
        email=email_cfg,
        state=raw.get("state", {"file": "data/sent_jobs.json", "max_age_days": 30}),
    )
