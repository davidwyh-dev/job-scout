from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from job_scout.config import AppConfig, SearchConfig, load_config
from job_scout.dedup import deduplicate
from job_scout.email_builder import build_email
from job_scout.email_sender import send_digest
from job_scout.models import Job
from job_scout.sources.base import BaseSource
from job_scout.state import StateManager

logger = logging.getLogger("job_scout")


def _build_sources(config: AppConfig) -> list[BaseSource]:
    sources: list[BaseSource] = []

    # JobSpy (LinkedIn, Indeed, Glassdoor, Google, ZipRecruiter)
    jobspy_cfg = config.sources.get("jobspy", {})
    if jobspy_cfg.get("enabled", False):
        from job_scout.sources.jobspy_source import JobSpySource
        sources.append(JobSpySource(sites=jobspy_cfg.get("sites")))

    # Greenhouse
    gh_companies = config.ats_companies.get("greenhouse", [])
    if gh_companies:
        from job_scout.sources.greenhouse import GreenhouseSource
        sources.append(GreenhouseSource(gh_companies))

    # Lever
    lever_companies = config.ats_companies.get("lever", [])
    if lever_companies:
        from job_scout.sources.lever import LeverSource
        sources.append(LeverSource(lever_companies))

    # Ashby
    ashby_companies = config.ats_companies.get("ashby", [])
    if ashby_companies:
        from job_scout.sources.ashby import AshbySource
        sources.append(AshbySource(ashby_companies))

    # The Muse
    muse_cfg = config.sources.get("the_muse", {})
    if muse_cfg.get("enabled", False):
        from job_scout.sources.the_muse import TheMuseSource
        sources.append(TheMuseSource(api_key=muse_cfg.get("api_key", "")))

    # Adzuna
    adzuna_cfg = config.sources.get("adzuna", {})
    if adzuna_cfg.get("enabled", False):
        from job_scout.sources.adzuna import AdzunaSource
        sources.append(AdzunaSource(
            app_id=adzuna_cfg.get("app_id", ""),
            app_key=adzuna_cfg.get("app_key", ""),
        ))

    return sources


def _matches_title(job: Job, config: SearchConfig) -> bool:
    title_lower = job.title.lower()
    for exclude in config.title_exclude:
        if exclude.lower() in title_lower:
            return False
    for include in config.titles:
        if include.lower() in title_lower:
            return True
    return False


def _fetch_indirect_jobs(config: AppConfig, state: StateManager) -> list[Job]:
    """Phase 2: Discover jobs from recently funded companies."""
    indirect_cfg = config.indirect_sources
    if not indirect_cfg.get("enabled", False):
        return []

    from job_scout.indirect.career_page_resolver import resolve_ats_boards
    from job_scout.indirect.funding_monitor import fetch_recently_funded_companies

    # Step 1: Get recently funded companies from RSS
    rss_feeds = indirect_cfg.get("rss_feeds", [])
    keywords = indirect_cfg.get("funding_keywords", [])
    funded_companies = fetch_recently_funded_companies(rss_feeds, keywords)

    if not funded_companies:
        logger.info("No recently funded companies found in RSS")
        return []

    # Step 2: Resolve ATS boards for these companies
    new_boards = resolve_ats_boards(funded_companies, state.discovered_ats_boards)
    state.update_discovered_boards(new_boards)

    # Step 3: Fetch jobs from all discovered boards (new + previously cached)
    all_boards = state.all_discovered_boards
    if not all_boards:
        return []

    jobs: list[Job] = []
    for board in all_boards:
        platform = board["platform"]
        slug = board["slug"]
        company_name = board["company"]

        try:
            if platform == "greenhouse":
                from job_scout.sources.greenhouse import GreenhouseSource
                src = GreenhouseSource([{"board_token": slug, "name": company_name}])
            elif platform == "lever":
                from job_scout.sources.lever import LeverSource
                src = LeverSource([{"slug": slug, "name": company_name}])
            elif platform == "ashby":
                from job_scout.sources.ashby import AshbySource
                src = AshbySource([{"slug": slug, "name": company_name}])
            else:
                continue

            board_jobs = src.fetch(config.search)
            for j in board_jobs:
                j.discovered_via = "funding_news"
            jobs.extend(board_jobs)
        except Exception as e:
            logger.error("Indirect fetch [%s/%s] failed: %s", platform, slug, e)

    logger.info("Indirect pipeline: %d jobs from %d boards", len(jobs), len(all_boards))
    return jobs


def _resolve_state_path(config: AppConfig) -> str:
    """Resolve state file path relative to project root."""
    state_file = config.state.get("file", "data/sent_jobs.json")
    # If absolute, use as-is
    if Path(state_file).is_absolute():
        return state_file
    # Otherwise, resolve relative to project root (parent of src/)
    root = Path(__file__).resolve().parent.parent.parent
    return str(root / state_file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Job Scout — daily PM job digest")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report but don't send email")
    parser.add_argument("--config", type=str, default=None, help="Path to config YAML")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load config
    config = load_config(args.config)
    state = StateManager(_resolve_state_path(config))

    # Phase 1: Fetch from direct sources in parallel
    sources = _build_sources(config)
    logger.info("Fetching from %d direct sources...", len(sources))

    all_jobs: list[Job] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(src.fetch, config.search): src for src in sources}
        for future in as_completed(futures):
            source = futures[future]
            try:
                jobs = future.result(timeout=120)
                all_jobs.extend(jobs)
                logger.info("%s: fetched %d jobs", source.name, len(jobs))
            except Exception as e:
                logger.error("%s: failed: %s", source.name, e)

    # Phase 2: Indirect sources
    try:
        indirect_jobs = _fetch_indirect_jobs(config, state)
        all_jobs.extend(indirect_jobs)
    except Exception as e:
        logger.error("Indirect pipeline failed: %s", e)

    logger.info("Total raw jobs: %d", len(all_jobs))

    # Phase 3: Filter, dedup, remove already-sent
    all_jobs = [j for j in all_jobs if _matches_title(j, config.search)]
    logger.info("After title filter: %d", len(all_jobs))

    if config.search.exclude_public_companies or config.search.company_exclude:
        from job_scout.public_company_filter import PublicCompanyChecker
        checker = PublicCompanyChecker(config.search.company_exclude, state)
        all_jobs = [j for j in all_jobs if not checker.is_excluded(
            j.company, use_api=config.search.exclude_public_companies
        )]
        checker.flush_cache()
        logger.info("After public/excluded company filter: %d", len(all_jobs))

    all_jobs = deduplicate(all_jobs)
    logger.info("After dedup: %d", len(all_jobs))

    new_jobs = [j for j in all_jobs if not state.is_already_sent(j.id)]
    logger.info("New (unsent) jobs: %d", len(new_jobs))

    if args.dry_run:
        print(f"\n{'='*60}")
        print(f"DRY RUN — {len(new_jobs)} new jobs found")
        print(f"{'='*60}")
        for job in new_jobs[:20]:
            remote_tag = " [Remote]" if job.is_remote else ""
            funding_tag = " (via funding news)" if job.discovered_via else ""
            salary_tag = f" ({job.salary_range})" if job.salary_range else ""
            print(f"  {job.title} @ {job.company}{remote_tag}{salary_tag}{funding_tag}")
            print(f"    {job.source} — {job.url}")
        if len(new_jobs) > 20:
            print(f"  ... and {len(new_jobs) - 20} more")
        print()
        # Still persist state in dry run so we can test incrementally
        state.prune(config.state.get("max_age_days", 30))
        state.save()
        return

    # Phase 4: Send email
    if new_jobs:
        max_jobs = config.email.get("max_jobs_per_email", 50)
        jobs_to_send = new_jobs[:max_jobs]
        html = build_email(jobs_to_send)
        send_digest(html, config.email, job_count=len(jobs_to_send))
        state.mark_sent([j.id for j in jobs_to_send])
        logger.info("Sent digest with %d jobs", len(jobs_to_send))
    else:
        logger.info("No new jobs found — skipping email")

    # Phase 5: Persist state
    state.prune(config.state.get("max_age_days", 30))
    state.save()
    logger.info("State saved. Done.")


if __name__ == "__main__":
    main()
