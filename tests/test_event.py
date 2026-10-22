import unittest

from domain.entities.event import Event


class EventTest(unittest.TestCase):
    def test_payload_keeps_original_and_adds_lowercase_aliases(self):
        event = Event(
            {
                "UNIT_ID": "unit-1",
                "UNIT_NAME": "sensor",
                "VENDOR_ID": "vendor",
            }
        )

        payload = event.as_payload("sensor-123")

        self.assertEqual(payload["UNIT_ID"], "unit-1")
        self.assertEqual(payload["unit_id"], "unit-1")
        self.assertEqual(payload["UNIT_NAME"], "sensor")
        self.assertEqual(payload["unit_name"], "sensor")
        self.assertEqual(payload["VENDOR_ID"], "vendor")
        self.assertEqual(payload["vendor_id"], "vendor")
        self.assertEqual(payload["sensor_id"], "sensor-123")

    def test_existing_lowercase_value_wins(self):
        event = Event({"UNIT_ID": "upper", "unit_id": "lower"})

        payload = event.as_payload("sensor-123")

        self.assertEqual(payload["unit_id"], "lower")

    def test_original_record_is_not_mutated(self):
        data = {"UNIT_ID": "unit-1"}
        event = Event(data)

        event.as_payload("sensor-123")

        self.assertEqual(data, {"UNIT_ID": "unit-1"})

    def test_rejects_non_mapping_data(self):
        with self.assertRaises(ValueError):
            Event(["not", "a", "mapping"])

    def test_fingerprint_prefers_document_identifier(self):
        first = Event({"stellar_uuid": "doc-1", "message": "a"})
        second = Event({"stellar_uuid": "doc-1", "message": "b"})

        self.assertEqual(first.fingerprint(), second.fingerprint())
        self.assertNotEqual(
            first.fingerprint(), Event({"stellar_uuid": "doc-2"}).fingerprint()
        )

    def test_fingerprint_falls_back_to_content(self):
        first = Event({"a": 1, "b": [1, 2]})
        reordered = Event({"b": [1, 2], "a": 1})

        self.assertEqual(first.fingerprint(), reordered.fingerprint())
        self.assertNotEqual(first.fingerprint(), Event({"a": 2}).fingerprint())


if __name__ == "__main__":
    unittest.main()
