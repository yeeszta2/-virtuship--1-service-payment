import unittest
from unittest.mock import MagicMock

import requests

from src.circuit_breaker import CircuitBreaker
from src.payment_client import (PaymentGatewayClient, PaymentGatewayRejected,
                                PaymentGatewayUnavailable)


def make_client(session, threshold=2):
    return PaymentGatewayClient("https://gateway.test/v1", "key-123", 3.0,
                                CircuitBreaker(threshold, 30), session)


def response(status, body=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body or {}
    return r


class PaymentClientTest(unittest.TestCase):
    def test_success_returns_json_and_sends_timeout_and_idempotency(self):
        session = MagicMock()
        session.post.return_value = response(200, {"reference": "GW-1"})
        result = make_client(session).create_payment("ORD-1", 5000, "idem-1")
        self.assertEqual(result["reference"], "GW-1")
        kwargs = session.post.call_args.kwargs
        self.assertEqual(kwargs["timeout"], (3.0, 3.0))          # timeout selalu terpasang
        self.assertEqual(kwargs["headers"]["Idempotency-Key"], "idem-1")

    def test_timeout_becomes_unavailable(self):
        session = MagicMock()
        session.post.side_effect = requests.Timeout()
        with self.assertRaises(PaymentGatewayUnavailable):
            make_client(session).create_payment("ORD-1", 5000, "idem-1")

    def test_server_error_becomes_unavailable(self):
        session = MagicMock()
        session.post.return_value = response(503)
        with self.assertRaises(PaymentGatewayUnavailable):
            make_client(session).create_payment("ORD-1", 5000, "idem-1")

    def test_client_error_becomes_rejected(self):
        session = MagicMock()
        session.post.return_value = response(422)
        with self.assertRaises(PaymentGatewayRejected):
            make_client(session).create_payment("ORD-1", 5000, "idem-1")

    def test_circuit_opens_and_stops_calling_partner(self):
        session = MagicMock()
        session.post.side_effect = requests.ConnectionError()
        client = make_client(session, threshold=2)
        for _ in range(2):
            with self.assertRaises(PaymentGatewayUnavailable):
                client.create_payment("ORD-1", 5000, "idem-1")
        calls_before = session.post.call_count
        with self.assertRaises(PaymentGatewayUnavailable):       # ditolak tanpa menyentuh mitra
            client.create_payment("ORD-1", 5000, "idem-1")
        self.assertEqual(session.post.call_count, calls_before)


if __name__ == "__main__":
    unittest.main()
