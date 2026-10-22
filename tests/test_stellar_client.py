import unittest

import requests

from domain.errors import ConfigurationError, EventSourceError
from infrastructure.stellar.stellar_client import StellarClient


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)


class RecordingSession(requests.Session):
    def __init__(self, response=None, error=None):
        super().__init__()
        self.response = response or FakeResponse()
        self.error = error
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.error:
            raise self.error
        return self.response


class StellarClientTest(unittest.TestCase):
    def test_requires_host_and_token(self):
        with self.assertRaises(ConfigurationError):
            StellarClient(host="", refresh_token="token")
        with self.assertRaises(ConfigurationError):
            StellarClient(host="stellar.example", refresh_token="")

    def test_host_must_use_https(self):
        with self.assertRaises(ConfigurationError):
            StellarClient(host="http://stellar.example", refresh_token="token")

    def test_requests_access_token_with_bearer_refresh_token(self):
        session = RecordingSession(FakeResponse({"access_token": "access-1"}))
        client = StellarClient(
            "stellar.example", "refresh-token", verify_tls=False, session=session
        )

        token = client.get_access_token()

        self.assertEqual(token, "access-1")
        method, url, kwargs = session.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://stellar.example/connect/api/v1/access_token")
        self.assertEqual(kwargs["headers"], {"Authorization": "Bearer refresh-token"})
        self.assertFalse(kwargs["verify"])
        self.assertEqual(kwargs["timeout"], 30)

    def test_missing_access_token_is_an_error(self):
        client = StellarClient(
            "stellar.example",
            "refresh-token",
            session=RecordingSession(FakeResponse({"nope": True})),
        )

        with self.assertRaises(EventSourceError):
            client.get_access_token()

    def test_search_sends_query_with_bearer_access_token(self):
        payload = {"hits": {"hits": []}}
        session = RecordingSession(FakeResponse(payload))
        client = StellarClient("stellar.example", "refresh-token", session=session)

        result = client.search({"size": 10}, "access-1")

        self.assertEqual(result, payload)
        method, url, kwargs = session.calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(
            url,
            "https://stellar.example/connect/api/data/aella-syslog-*/_search",
        )
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer access-1")
        self.assertEqual(kwargs["json"], {"size": 10})

    def test_http_errors_are_wrapped(self):
        client = StellarClient(
            "stellar.example",
            "refresh-token",
            session=RecordingSession(FakeResponse({}, status_code=500)),
        )

        with self.assertRaises(EventSourceError):
            client.get_access_token()

    def test_transport_errors_are_wrapped(self):
        client = StellarClient(
            "stellar.example",
            "refresh-token",
            session=RecordingSession(error=requests.Timeout("timeout")),
        )

        with self.assertRaises(EventSourceError) as context:
            client.get_access_token()

        self.assertIsInstance(context.exception.__cause__, requests.Timeout)

    def test_invalid_json_is_wrapped(self):
        client = StellarClient(
            "stellar.example",
            "refresh-token",
            session=RecordingSession(FakeResponse(ValueError("bad json"))),
        )

        with self.assertRaises(EventSourceError):
            client.get_access_token()


if __name__ == "__main__":
    unittest.main()
