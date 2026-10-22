"""HTTP transport for the Stellar Cyber API."""

from __future__ import annotations

import logging
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunparse

import requests

from domain.errors import ConfigurationError, EventSourceError

ACCESS_TOKEN_PATH = "/connect/api/v1/access_token"
SEARCH_PATH = "/connect/api/data/aella-syslog-*/_search"

_logger = logging.getLogger("stellar.forwarder")


def _normalize_host(host: str) -> str:
    if not host:
        raise ConfigurationError(
            "Missing STELLAR_HOST in environment configuration"
        )

    configured_host = host if "://" in host else f"https://{host}"
    parsed_host = urlsplit(configured_host)
    if parsed_host.scheme != "https" or not parsed_host.netloc:
        raise ConfigurationError("STELLAR_HOST must be an HTTPS hostname")

    return urlunparse(("https", parsed_host.netloc, "", "", "", ""))


class StellarClient:
    """Thin transport around the Stellar Cyber REST endpoints."""

    def __init__(
        self,
        host: str,
        refresh_token: str,
        verify_tls: bool = True,
        request_timeout: int = 30,
        session: requests.Session | None = None,
    ) -> None:
        if not refresh_token:
            raise ConfigurationError(
                "Missing STELLAR_REFRESH_TOKEN in environment configuration"
            )

        self._host = _normalize_host(host)
        self._refresh_token = refresh_token
        self._verify_tls = verify_tls
        self._timeout = request_timeout
        self._session = session or requests.Session()

    def get_access_token(self) -> str:
        response = self._request(
            "POST",
            self._build_url(ACCESS_TOKEN_PATH),
            headers={"Authorization": f"Bearer {self._refresh_token}"},
        )
        _logger.info("Access token HTTP status: %s", response.status_code)
        self._raise_for_status(response, "access token request")

        payload = self._json_body(response, "access token")
        access_token = payload.get("access_token")
        if not access_token:
            raise EventSourceError("Access token missing from API response")

        return str(access_token)

    def search(
        self, query: Mapping[str, Any], access_token: str
    ) -> dict[str, Any]:
        response = self._request(
            "GET",
            self._build_url(SEARCH_PATH),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=query,
        )
        _logger.info("Data API HTTP status: %s", response.status_code)
        self._raise_for_status(response, "data query")

        return self._json_body(response, "data query")

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "StellarClient":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def _build_url(self, path: str) -> str:
        parsed_host = urlsplit(self._host)
        return urlunparse(("https", parsed_host.netloc, path, "", "", ""))

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        try:
            return self._session.request(
                method,
                url,
                timeout=self._timeout,
                verify=self._verify_tls,
                **kwargs,
            )
        except requests.exceptions.RequestException as exc:
            raise EventSourceError(
                f"{method} {url} failed: {type(exc).__name__}: {exc}"
            ) from exc

    @staticmethod
    def _raise_for_status(response: requests.Response, operation: str) -> None:
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise EventSourceError(
                f"Stellar {operation} failed with HTTP {response.status_code}"
            ) from exc

    @staticmethod
    def _json_body(
        response: requests.Response, operation: str
    ) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise EventSourceError(
                f"Stellar {operation} returned invalid JSON"
            ) from exc

        if not isinstance(payload, Mapping):
            raise EventSourceError(
                f"Stellar {operation} response is not a JSON object"
            )

        return dict(payload)
