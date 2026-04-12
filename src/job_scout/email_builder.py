from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from job_scout.models import Job


def _find_templates_dir() -> Path:
    current = Path(__file__).resolve().parent
    for _ in range(10):
        candidate = current / "templates"
        if candidate.is_dir():
            return candidate
        current = current.parent
    raise FileNotFoundError("Could not find templates/ directory")


def build_email(jobs: list[Job], date: str | None = None) -> str:
    if date is None:
        date = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")

    direct_jobs = [j for j in jobs if j.discovered_via is None]
    indirect_jobs = [j for j in jobs if j.discovered_via is not None]

    # Sort by date (newest first), then by company name
    def sort_key(j: Job):
        dt = j.date_posted or datetime.min.replace(tzinfo=timezone.utc)
        return (-dt.timestamp(), j.company.lower())

    direct_jobs.sort(key=sort_key)
    indirect_jobs.sort(key=sort_key)

    # Count jobs per source category
    source_counts: dict[str, int] = {}
    for job in jobs:
        src = job.source.split(":")[0].title()
        source_counts[src] = source_counts.get(src, 0) + 1

    templates_dir = _find_templates_dir()
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
    template = env.get_template("digest.html")

    return template.render(
        date=date,
        total_jobs=len(jobs),
        source_counts=source_counts,
        direct_jobs=direct_jobs,
        indirect_jobs=indirect_jobs,
    )
