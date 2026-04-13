from __future__ import annotations

import logging
import urllib.parse
import urllib.request
import json

from job_scout.state import StateManager

logger = logging.getLogger(__name__)


class PublicCompanyChecker:
    def __init__(self, company_exclude: list[str], state: StateManager) -> None:
        self._exclude_lower = {name.lower() for name in company_exclude}
        self._state = state
        self._cache: dict[str, bool] = dict(state.public_company_cache)

    def is_excluded(self, company: str, *, use_api: bool = True) -> bool:
        if company.lower() in self._exclude_lower:
            logger.debug("Company '%s' matched manual exclude list", company)
            return True
        if use_api:
            return self._is_public(company)
        return False

    def _is_public(self, company: str) -> bool:
        key = company.lower()
        if key in self._cache:
            return self._cache[key]

        result = self._check_yahoo_finance(company)
        self._cache[key] = result
        if result:
            logger.info("Filtered public company: %s", company)
        return result

    def _check_yahoo_finance(self, company: str) -> bool:
        try:
            params = urllib.parse.urlencode({
                "q": company,
                "quotesCount": 1,
                "newsCount": 0,
                "enableFuzzyQuery": "false",
            })
            url = f"https://query2.finance.yahoo.com/v1/finance/search?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": "JobScout/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())

            quotes = data.get("quotes", [])
            if not quotes:
                return False

            quote = quotes[0]
            if quote.get("quoteType") != "EQUITY":
                return False

            short_name = (quote.get("shortname") or "").lower()
            long_name = (quote.get("longname") or "").lower()
            company_lower = company.lower()

            return company_lower in short_name or company_lower in long_name
        except Exception as e:
            logger.warning("Yahoo Finance lookup failed for '%s': %s", company, e)
            return False

    def flush_cache(self) -> None:
        self._state.update_public_company_cache(self._cache)
