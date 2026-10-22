import logging
import os
import tempfile
import unittest
from logging.handlers import TimedRotatingFileHandler

from infrastructure.logging.logger import LOGGER_NAME, configure_logging, get_logger


class ConfigureLoggingTest(unittest.TestCase):
    def setUp(self):
        self._logger = get_logger()
        self._saved_disabled = self._logger.disabled
        self._saved_handlers = list(self._logger.handlers)
        self._logger.handlers.clear()
        self._logger.disabled = False

    def tearDown(self):
        for handler in self._logger.handlers:
            handler.close()
        self._logger.handlers.clear()
        self._logger.handlers.extend(self._saved_handlers)
        self._logger.disabled = self._saved_disabled

    def test_disabled_logging_does_not_write_a_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "app.log")
            logger = configure_logging(log_file=path, enabled=False)

            self.assertTrue(logger.disabled)
            self.assertEqual(logger.name, LOGGER_NAME)
            self.assertEqual(len(logger.handlers), 1)
            self.assertIsInstance(logger.handlers[0], logging.NullHandler)

            logger.info("ignored")
            self.assertFalse(os.path.exists(path))

    def test_writes_records_to_log_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "app.log")
            logger = configure_logging(log_file=path, level=logging.INFO)

            logger.info("forwarded 1 record")
            content = self._read_and_close(path)

        self.assertIn("forwarded 1 record", content)

    def test_level_filters_lower_severity_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "app.log")
            logger = configure_logging(log_file=path, level=logging.WARNING)

            logger.info("skipped record")
            logger.warning("kept record")
            content = self._read_and_close(path)

        self.assertNotIn("skipped record", content)
        self.assertIn("kept record", content)

    def test_file_handler_rotates_at_midnight_with_retention(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "app.log")
            configure_logging(log_file=path, level=logging.INFO, retention_days=5)

            handler = self._file_handler()

            self.assertIsInstance(handler, TimedRotatingFileHandler)
            self.assertEqual(handler.when, "MIDNIGHT")
            self.assertEqual(handler.backupCount, 5)
            self.assertEqual(handler.suffix, "%Y-%m-%d")
            self._close_handlers()

    def test_rotation_deletes_logs_older_than_retention(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "app.log")
            for name in ("app.log.2000-01-01", "app.log.2000-01-02", "app.log.2000-01-03"):
                with open(os.path.join(temp_dir, name), "w", encoding="utf-8") as stream:
                    stream.write("old\n")

            logger = configure_logging(
                log_file=path, level=logging.INFO, retention_days=1
            )
            logger.info("before rotation")

            self._file_handler().doRollover()

            rotated = [name for name in os.listdir(temp_dir) if name.startswith("app.log.")]
            self._close_handlers()

        self.assertEqual(len(rotated), 1)
        self.assertFalse(any(name.startswith("app.log.2000") for name in rotated))

    def _read_and_close(self, path):
        for handler in self._logger.handlers:
            handler.flush()
        with open(path, encoding="utf-8") as stream:
            content = stream.read()
        self._close_handlers()
        return content

    def _close_handlers(self):
        # Release open files so TemporaryDirectory can delete them on Windows.
        for handler in self._logger.handlers:
            handler.close()

    def _file_handler(self):
        for handler in self._logger.handlers:
            if isinstance(handler, TimedRotatingFileHandler):
                return handler
        raise AssertionError("no rotating file handler configured")


if __name__ == "__main__":
    unittest.main()
