import os
import unittest
from unittest.mock import patch

from src.config import load_settings

BASE = {"PAYMENT_API_BASE_URL": "https://gateway.test/v1", "PAYMENT_API_KEY": "k", "WEBHOOK_SECRET": "w"}


class ConfigTest(unittest.TestCase):
    def test_missing_secret_fails_fast_without_leaking_value(self):
        env = dict(BASE); env.pop("PAYMENT_API_KEY")
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                load_settings()
        self.assertIn("PAYMENT_API_KEY", str(ctx.exception))

    def test_http_url_rejected_outside_local(self):
        env = dict(BASE, PAYMENT_API_BASE_URL="http://gateway.test/v1")
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError):
                load_settings()

    def test_http_allowed_in_local(self):
        env = dict(BASE, PAYMENT_API_BASE_URL="http://localhost:9000/v1", APP_ENV="local")
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(load_settings().gateway_timeout_seconds, 3.0)


if __name__ == "__main__":
    unittest.main()
