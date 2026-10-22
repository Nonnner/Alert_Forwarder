import logging
import unittest
from datetime import datetime

from config.settings import Settings
from domain.errors import ConfigurationError

BASE_ENV = {
    "STELLAR_HOST": "stellar.example",
    "STELLAR_REFRESH_TOKEN": "refresh-token",
    "DESTINATION_API_URL": "https://dest.example/events",
    "API_KEY": "secret",
    "SENSOR_ID": "sensor-1",
}


def build_env(**overrides):
    env = dict(BASE_ENV)
    env.update(overrides)
    return env


class SettingsTest(unittest.TestCase):
    def test_reads_defaults(self):
        settings = Settings.from_env(build_env())

        self.assertEqual(settings.stellar.host, "stellar.example")
        self.assertTrue(settings.stellar.verify_tls)
        self.assertEqual(settings.stellar.request_timeout, 30)
        self.assertEqual(settings.stellar.search_time_zone, "+07:00")
        self.assertEqual(settings.destination.request_timeout, 30)
        self.assertEqual(settings.logging.log_file, "log.txt")
        self.assertTrue(settings.logging.enabled)
        self.assertEqual(settings.logging.level, logging.INFO)
        self.assertTrue(settings.logging.log_request)
        self.assertTrue(settings.logging.log_response)
        self.assertEqual(settings.logging.retention_days, 7)
        self.assertTrue(settings.stats.enabled)
        self.assertEqual(settings.stats.file, "stats.json")
        self.assertEqual(settings.stats.retention_days, 30)
        self.assertEqual(settings.scheduler.run_interval_minutes, 5)
        self.assertIsNone(settings.scheduler.initial_lookback_minutes)
        self.assertIsNone(settings.scheduler.initial_start_time)
        self.assertFalse(settings.scheduler.run_once)

    def test_reads_explicit_values(self):
        settings = Settings.from_env(
            build_env(
                STELLAR_VERIFY_TLS="false",
                REQUEST_TIMEOUT="10",
                SEARCH_TIME_ZONE="+09:00",
                LOG_FILE="logs/forwarder.log",
                LOG_ENABLED="false",
                LOG_LEVEL="debug",
                LOG_REQUEST="false",
                LOG_RESPONSE="no",
                LOG_RETENTION_DAYS="0",
                STATS_ENABLED="no",
                STATS_FILE="data/stats.json",
                STATS_RETENTION_DAYS="14",
                RUN_INTERVAL_MINUTES="2",
                INITIAL_LOOKBACK_MINUTES="30",
                INITIAL_START_TIME="2026-10-21T00:00:00+07:00",
                RUN_ONCE="yes",
            )
        )

        self.assertFalse(settings.stellar.verify_tls)
        self.assertEqual(settings.stellar.request_timeout, 10)
        self.assertEqual(settings.stellar.search_time_zone, "+09:00")
        self.assertEqual(settings.logging.log_file, "logs/forwarder.log")
        self.assertFalse(settings.logging.enabled)
        self.assertEqual(settings.logging.level, logging.DEBUG)
        self.assertFalse(settings.logging.log_request)
        self.assertFalse(settings.logging.log_response)
        self.assertEqual(settings.logging.retention_days, 0)
        self.assertFalse(settings.stats.enabled)
        self.assertEqual(settings.stats.file, "data/stats.json")
        self.assertEqual(settings.stats.retention_days, 14)
        self.assertEqual(settings.scheduler.run_interval_minutes, 2)
        self.assertEqual(settings.scheduler.initial_lookback_minutes, 30)
        self.assertEqual(
            settings.scheduler.initial_start_time,
            datetime.fromisoformat("2026-10-21T00:00:00+07:00"),
        )
        self.assertTrue(settings.scheduler.run_once)

    def test_accepts_legacy_environment_aliases(self):
        env = build_env()
        env.pop("API_KEY")
        env.update(
            {
                "DESTINATION_API_KEY": "dest-secret",
                "POLL_INTERVAL_MINUTES": "7",
                "INITIAL_LOOPBACK_MINUTES": "45",
            }
        )

        settings = Settings.from_env(env)

        self.assertEqual(settings.destination.api_key, "dest-secret")
        self.assertEqual(settings.scheduler.run_interval_minutes, 7)
        self.assertEqual(settings.scheduler.initial_lookback_minutes, 45)

    def test_missing_stellar_token_is_reported(self):
        env = build_env()
        env.pop("STELLAR_REFRESH_TOKEN")

        with self.assertRaises(ConfigurationError):
            Settings.from_env(env)

    def test_missing_destination_configuration_lists_every_field(self):
        env = build_env()
        del env["DESTINATION_API_URL"]
        del env["SENSOR_ID"]

        with self.assertRaises(ConfigurationError) as context:
            Settings.from_env(env)

        self.assertIn("DESTINATION_API_URL", str(context.exception))
        self.assertIn("SENSOR_ID", str(context.exception))

    def test_destination_url_requires_scheme(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env(build_env(DESTINATION_API_URL="dest.example/events"))

    def test_api_key_rejects_line_breaks(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env(build_env(API_KEY="secret\nX-Injected: 1"))

    def test_invalid_numbers_are_rejected(self):
        for name, value in (
            ("REQUEST_TIMEOUT", "zero"),
            ("REQUEST_TIMEOUT", "0"),
            ("RUN_INTERVAL_MINUTES", "-1"),
            ("INITIAL_LOOKBACK_MINUTES", "abc"),
        ):
            with self.subTest(name=name, value=value), self.assertRaises(
                ConfigurationError
            ):
                Settings.from_env(build_env(**{name: value}))

    def test_invalid_initial_start_is_rejected(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env(build_env(INITIAL_START_TIME="21/10/2026"))

    def test_invalid_log_level_is_rejected(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env(build_env(LOG_LEVEL="verbose"))

    def test_invalid_log_flag_is_rejected(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env(build_env(LOG_REQUEST="maybe"))

    def test_invalid_retention_values_are_rejected(self):
        for name, value in (
            ("LOG_RETENTION_DAYS", "-1"),
            ("STATS_RETENTION_DAYS", "0"),
        ):
            with self.subTest(name=name, value=value), self.assertRaises(
                ConfigurationError
            ):
                Settings.from_env(build_env(**{name: value}))


if __name__ == "__main__":
    unittest.main()
