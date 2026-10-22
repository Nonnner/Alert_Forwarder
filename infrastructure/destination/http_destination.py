"""HTTP destination that posts every event as a JSON document."""

from __future__ import annotations

import logging

import requests

from domain.entities.event import Event
from domain.errors import DeliveryError
from domain.repositories.destination import Destination

MAX_LOGGED_BODY_LENGTH = 2000
SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
    }
)

_logger = logging.getLogger("stellar.forwarder")


def build_auth_header(api_key: str) -> str:
    if api_key.lower().startswith("basic "):
        return api_key
    return f"Basic {api_key}"


def truncate(text: str, limit: int = MAX_LOGGED_BODY_LENGTH) -> str:
    if len(text) > limit:
        return text[:limit] + "...[truncated]"
    return text


def mask_header_value(name: str, value: str) -> str:
    if name.lower() not in SENSITIVE_HEADERS:
        return value

    scheme, separator, _ = value.partition(" ")
    return f"{scheme} ****" if separator else "****"


class HttpDestination(Destination):
    """Delivers events to a JSON HTTP endpoint using basic authentication."""

    def __init__(
        self,
        url: str,
        api_key: str,
        sensor_id: str,
        request_timeout: int = 30,
        log_request: bool = True,
        log_response: bool = True,
        session: requests.Session | None = None,
    ) -> None:
        self._url = url
        self._sensor_id = sensor_id
        self._timeout = request_timeout
        self._log_request = log_request
        self._log_response = log_response
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": build_auth_header(api_key),
            }
        )

    def send(self, event: Event) -> None:
        payload = event.as_payload(self._sensor_id)
        prepared = self._session.prepare_request(
            requests.Request("POST", self._url, json=payload)
        )
        if self._log_request:
            self._log_request_message(prepared)

        try:
            response = self._session.send(prepared, timeout=self._timeout)
        except requests.exceptions.RequestException as exc:
            raise DeliveryError(
                f"POST {self._url} failed: {type(exc).__name__}: {exc}"
            ) from exc

        if self._log_response:
            self._log_response_message(response)

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise DeliveryError(
                f"Destination {self._url} returned HTTP {response.status_code}"
            ) from exc

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "HttpDestination":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def _log_request_message(self, request: requests.PreparedRequest) -> None:
        headers = ", ".join(
            f"{name}: {mask_header_value(name, value)}"
            for name, value in request.headers.items()
        )
        body = request.body or ""
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")

        _logger.info(
            "Forward request: %s %s, headers={%s}, body=%s",
            request.method,
            request.url,
            headers,
            truncate(str(body)) or "<empty>",
        )

    @staticmethod
    def _log_response_message(response: requests.Response) -> None:
        _logger.info(
            "Forward response: status=%d, elapsed=%.3fs, body=%s",
            response.status_code,
            response.elapsed.total_seconds(),
            truncate(response.text or "") or "<empty>",
        )
