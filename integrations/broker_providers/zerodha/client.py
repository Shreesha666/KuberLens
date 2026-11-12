"""
Zerodha Kite Connect v3 REST API Client.
Complies with Master Specification Section 22 and Development Plan Phase 10.
Implements read-only authentication, quotes, instruments, and portfolio holdings sync.
Enforces strict security: absolutely zero order placement endpoints exist or can be executed.
"""
import hashlib
import logging
import urllib.parse
from datetime import datetime, timedelta
from typing import Any

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)


class KiteConnectClient:
    """
    Read-only client interfacing with Zerodha Kite Connect v3 API.
    """
    BASE_URL = "https://api.kite.trade"
    LOGIN_URL = "https://kite.zerodha.com/connect/login"

    def __init__(self, api_key: str, access_token: str | None = None, api_secret: str | None = None):
        self.api_key = api_key.strip() if api_key else ""
        self.access_token = access_token.strip() if access_token else ""
        self.api_secret = api_secret.strip() if api_secret else ""
        self._session = requests.Session()
        self._session.headers.update({
            "X-Kite-Version": "3",
            "User-Agent": "IndianStockMarketIntel/1.0",
        })
        if self.api_key and self.access_token:
            self._session.headers["Authorization"] = f"token {self.api_key}:{self.access_token}"

    def get_login_url(self, redirect_url: str | None = None) -> str:
        """
        Builds user redirect URL for Kite Connect web login consent flow.
        """
        params = {"v": "3", "api_key": self.api_key}
        if redirect_url:
            params["redirect_url"] = redirect_url
        return f"{self.LOGIN_URL}?{urllib.parse.urlencode(params)}"

    def generate_session(self, request_token: str, api_secret: str | None = None) -> dict[str, Any]:
        """
        Exchanges daily ephemeral request_token for user access_token.
        Checksum format: SHA256(api_key + request_token + api_secret)
        """
        secret = api_secret or self.api_secret
        if not self.api_key or not secret:
            raise ValueError("Both api_key and api_secret are required to generate a session.")

        checksum_str = f"{self.api_key}{request_token}{secret}"
        checksum = hashlib.sha256(checksum_str.encode("utf-8")).hexdigest()

        payload = {
            "api_key": self.api_key,
            "request_token": request_token,
            "checksum": checksum,
        }

        url = f"{self.BASE_URL}/session/token"
        try:
            resp = self._session.post(url, data=payload, timeout=10)
            data = resp.json()
            if resp.status_code == 200 and data.get("status") == "success":
                session_data = data.get("data", {})
                self.access_token = session_data.get("access_token", "")
                self._session.headers["Authorization"] = f"token {self.api_key}:{self.access_token}"
                return session_data
            else:
                error_msg = data.get("message", f"HTTP {resp.status_code} authentication failure")
                logger.error("Kite session token generation failed: %s", error_msg)
                raise ConnectionError(f"Zerodha Kite authentication error: {error_msg}")
        except requests.RequestException as e:
            logger.error("Kite session request failed: %s", e)
            raise ConnectionError(f"Could not reach Zerodha Kite servers: {e}") from e

    def get_holdings(self) -> list[dict[str, Any]]:
        """
        Retrieves user long-term equity portfolio holdings.
        Endpoint: GET /portfolio/holdings
        """
        url = f"{self.BASE_URL}/portfolio/holdings"
        try:
            resp = self._session.get(url, timeout=10)
            data = resp.json()
            if resp.status_code == 200 and data.get("status") == "success":
                return data.get("data", [])
            else:
                msg = data.get("message", "Failed to retrieve holdings")
                raise ConnectionError(f"Kite holdings retrieval failed: {msg}")
        except requests.RequestException as e:
            logger.error("Kite holdings request error: %s", e)
            raise ConnectionError(f"Error connecting to Kite Connect: {e}") from e

    def get_positions(self) -> dict[str, list[dict[str, Any]]]:
        """
        Retrieves intraday and carryforward positions.
        Endpoint: GET /portfolio/positions
        """
        url = f"{self.BASE_URL}/portfolio/positions"
        try:
            resp = self._session.get(url, timeout=10)
            data = resp.json()
            if resp.status_code == 200 and data.get("status") == "success":
                return data.get("data", {"net": [], "day": []})
            else:
                msg = data.get("message", "Failed to retrieve positions")
                raise ConnectionError(f"Kite positions retrieval failed: {msg}")
        except requests.RequestException as e:
            logger.error("Kite positions request error: %s", e)
            raise ConnectionError(f"Error connecting to Kite Connect: {e}") from e

    def get_quote(self, instruments: list[str]) -> dict[str, Any]:
        """
        Retrieves market quotes for given instruments (e.g. ['NSE:RELIANCE', 'NSE:TCS']).
        Endpoint: GET /quote?i=...
        """
        if not instruments:
            return {}
        params = [("i", inst) for inst in instruments]
        url = f"{self.BASE_URL}/quote"
        try:
            resp = self._session.get(url, params=params, timeout=10)
            data = resp.json()
            if resp.status_code == 200 and data.get("status") == "success":
                return data.get("data", {})
            return {}
        except requests.RequestException as e:
            logger.warning("Kite quote request failed: %s", e)
            return {}

    @classmethod
    def calculate_token_expiry(cls) -> datetime:
        """
        Kite Connect access tokens expire every morning at 06:00 AM IST (00:30 UTC).
        Computes the next upcoming 06:00 AM IST expiration time.
        """
        now = timezone.now()
        # Next morning 00:30 UTC
        expiry = now.replace(hour=0, minute=30, second=0, microsecond=0)
        if expiry <= now:
            expiry += timedelta(days=1)
        return expiry

    # STRICT SAFETY PROTOCOL: No order placement allowed
    def place_order(self, *args, **kwargs):
        raise PermissionError(
            "CRITICAL SAFETY VIOLATION: Automatic or manual broker order placement is strictly "
            "prohibited by the platform's research-only policy (Architecture 2.1 & Master Spec Section 22)."
        )

    def modify_order(self, *args, **kwargs):
        raise PermissionError(
            "CRITICAL SAFETY VIOLATION: Broker order modification is prohibited."
        )

    def cancel_order(self, *args, **kwargs):
        raise PermissionError(
            "CRITICAL SAFETY VIOLATION: Broker order cancellation is prohibited."
        )
