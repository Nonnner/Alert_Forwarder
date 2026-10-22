import json
import unittest
from datetime import timedelta

import requests

from domain.entities.event import Event
from domain.errors import DeliveryError
from infrastructure.destination.http_destination import (
    HttpDestination,
    build_auth_header,
    mask_header_value,
    truncate,
)


class FakeResponse:
    def __init__(self, status_code=200, text='{"ok":true}'):
        self.status_code = status_code
        self.text = text
        self.elapsed = timedelta(seconds=0.25)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)


class RecordingSession(requests.Session):
    def __init__(self, response=None, error=None):
        super().__init__()
        self.response = response or FakeResponse()
        self.error = error
        self.requests = []

    def send(self, request, **kwargs):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.response


class HttpDestinationTest(unittest.TestCase):
    def test_build_auth_header(self):
        self.assertEqual(build_auth_header("abc"), "Basic abc")
        self.assertEqual(build_auth_header("Basic abc"), "Basic abc")
        self.assertEqual(build_auth_header("basic abc"), "basic abc")

    def test_masks_only_sensitive_headers(self):
        self.assertEqual(
            mask_header_value("Authorization", "Basic abc"), "Basic ****"
        )
        self.assertEqual(mask_header_value("Cookie", "session=1"), "****")
        self.assertEqual(mask_header_value("Accept", "application/json"), "application/json")

    def test_truncates_long_text(self):
        self.assertEqual(truncate("abcdef", limit=3), "abc...[truncated]")
        self.assertEqual(truncate("abc", limit=3), "abc")

    def test_posts_event_payload_with_sensor_id(self):
        session = RecordingSession()
        destination = HttpDestination(
            url="https://dest.example/events",
            api_key="secret",
            sensor_id="sensor-1",
            session=session,
        )
        destination.send(Event({"UNIT_ID": "u1"}))

        request = session.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url, "https://dest.example/events")
        self.assertEqual(request.headers["Authorization"], "Basic secret")
        self.assertEqual(
            json.loads(request.body),
            {"UNIT_ID": "u1", "unit_id": "u1", "sensor_id": "sensor-1"},
        )

    def test_http_error_becomes_delivery_error(self):
        session = RecordingSession(response=FakeResponse(status_code=500))
        destination = HttpDestination("https://dest.example", "key", "sensor", session=session)

        with self.assertRaises(DeliveryError):
            destination.send(Event({"id": "1"}))

    def test_logs_request_and_response_by_default(self):
        destination = HttpDestination(
            "https://dest.example", "key", "sensor", session=RecordingSession()
        )

        with self.assertLogs("stellar.forwarder", level="INFO") as captured:
            destination.send(Event({"id": "1"}))

        output = "\n".join(captured.output)
        self.assertIn("Forward request", output)
        self.assertIn("Forward response", output)

    def test_request_logging_can_be_disabled(self):
        destination = HttpDestination(
            "https://dest.example",
            "key",
            "sensor",
            log_request=False,
            session=RecordingSession(),
        )

        with self.assertLogs("stellar.forwarder", level="INFO") as captured:
            destination.send(Event({"id": "1"}))

        output = "\n".join(captured.output)
        self.assertNotIn("Forward request", output)
        self.assertIn("Forward response", output)

    def test_response_logging_can_be_disabled(self):
        destination = HttpDestination(
            "https://dest.example",
            "key",
            "sensor",
            log_response=False,
            session=RecordingSession(),
        )

        with self.assertLogs("stellar.forwarder", level="INFO") as captured:
            destination.send(Event({"id": "1"}))

        output = "\n".join(captured.output)
        self.assertIn("Forward request", output)
        self.assertNotIn("Forward response", output)

    def test_disabling_both_logs_nothing_on_success(self):
        destination = HttpDestination(
            "https://dest.example",
            "key",
            "sensor",
            log_request=False,
            log_response=False,
            session=RecordingSession(),
        )

        with self.assertNoLogs("stellar.forwarder", level="INFO"):
            destination.send(Event({"id": "1"}))

    def test_transport_error_becomes_delivery_error(self):
        session = RecordingSession(error=requests.ConnectionError("boom"))
        destination = HttpDestination("https://dest.example", "key", "sensor", session=session)

        with self.assertRaises(DeliveryError) as context:
            destination.send(Event({"id": "1"}))

        self.assertIsInstance(context.exception.__cause__, requests.ConnectionError)


if __name__ == "__main__":
    unittest.main()
