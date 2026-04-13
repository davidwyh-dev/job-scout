from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(self, file_path: str) -> None:
        self._path = Path(file_path)
        self._data: dict = {"sent_jobs": {}, "last_run": None, "discovered_ats_boards": {}, "public_company_cache": {}}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path) as f:
                    loaded = json.load(f)
                # Merge with defaults so missing keys are always present
                self._data.update(loaded)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load state file, starting fresh: %s", e)
        self._data.setdefault("sent_jobs", {})
        self._data.setdefault("last_run", None)
        self._data.setdefault("discovered_ats_boards", {})
        self._data.setdefault("public_company_cache", {})

    def save(self) -> None:
        self._data["last_run"] = datetime.now(timezone.utc).isoformat()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2)

    def is_already_sent(self, job_id: str) -> bool:
        return job_id in self._data["sent_jobs"]

    def mark_sent(self, job_ids: list[str]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for jid in job_ids:
            self._data["sent_jobs"][jid] = now

    def prune(self, max_age_days: int) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        to_remove = []
        for jid, ts in self._data["sent_jobs"].items():
            try:
                sent_at = datetime.fromisoformat(ts)
                if sent_at < cutoff:
                    to_remove.append(jid)
            except (ValueError, TypeError):
                to_remove.append(jid)
        for jid in to_remove:
            del self._data["sent_jobs"][jid]
        if to_remove:
            logger.info("Pruned %d old entries from state", len(to_remove))

    # --- Discovered ATS boards (from indirect pipeline) ---

    @property
    def discovered_ats_boards(self) -> dict[str, dict]:
        return self._data.get("discovered_ats_boards", {})

    def update_discovered_boards(self, boards: list[dict]) -> None:
        for board in boards:
            key = board["slug"]
            self._data.setdefault("discovered_ats_boards", {})[key] = board

    @property
    def all_discovered_boards(self) -> list[dict]:
        return list(self._data.get("discovered_ats_boards", {}).values())

    # --- Public company cache ---

    @property
    def public_company_cache(self) -> dict[str, bool]:
        return self._data.get("public_company_cache", {})

    def update_public_company_cache(self, cache: dict[str, bool]) -> None:
        self._data.setdefault("public_company_cache", {}).update(cache)
