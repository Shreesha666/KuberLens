"""
ipos.markets API Client.
Provides open, free access to Indian Primary Market data:
- Master IPO directory (Mainboard & SME)
- Granular issue terms, price bands, issue sizes, and timelines
- Real-time exchange subscription records (QIB, NII, Retail multiples)
Reference: https://ipos.markets/api-docs
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

BASE_URL = "https://ipos.markets"
DEFAULT_TIMEOUT = 12
DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


class IPOSMarketsClient:
    """Client for fetching public market datasets from ipos.markets."""

    def __init__(self, base_url: str = BASE_URL, timeout: int = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _fetch_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        if params:
            query_str = urllib.parse.urlencode(params)
            url = f"{url}?{query_str}"

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            logger.warning("HTTP error fetching %s: %s %s", url, e.code, e.reason)
            return None
        except urllib.error.URLError as e:
            logger.warning("Network connection error fetching %s: %s", url, e.reason)
            return None
        except Exception as e:
            logger.warning("Unexpected error fetching %s: %s", url, e)
            return None

    def get_overview(self) -> dict[str, Any] | None:
        """Fetches macro counts and open/upcoming/recent debut issues."""
        return self._fetch_json("data/overview.json")

    def get_issues_index(self) -> list[dict[str, Any]]:
        """Fetches complete manifest of all 3,000+ Indian Mainboard and SME IPOs."""
        data = self._fetch_json("data/issues_index.json")
        if isinstance(data, dict):
            return data.get("issues", [])
        elif isinstance(data, list):
            return data
        return []

    def get_issue_detail(self, slug: str) -> dict[str, Any] | None:
        """Fetches granular issue details, price bands, issue size, and category subscriptions."""
        if not slug:
            return None
        return self._fetch_json(f"data/issue/{slug}.json")

    def get_subscriptions_manifest(self) -> list[dict[str, Any]]:
        """Fetches latest exchange book subscription multiples across all active issues."""
        data = self._fetch_json("api/v1/subscription")
        if isinstance(data, dict):
            return data.get("issues", [])
        return []

    def get_subscription_for_symbol(self, symbol: str) -> dict[str, Any] | None:
        """Fetches subscription snapshot for a specific NSE symbol, BSE ticker, or slug."""
        if not symbol:
            return None
        return self._fetch_json("api/v1/subscription", params={"symbol": symbol.strip().upper()})
