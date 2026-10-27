import hashlib
import hmac
import json
import os
import tempfile
import time

from src.app import create_app
from src.circuit_breaker import CircuitBreaker
from src.config import Settings
from src.payment_client import PaymentGatewayClient
from src.repository import PaymentRepository

SECRET = "unit-test-webhook-secret"


def make_settings(path):
    return Settings("https://gateway.test/v1", "unit-test-api-key", SECRET, path, 3.0, 3, 30.0)


def make_app(client):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    settings = make_settings(path)
    repo = PaymentRepository(path)
    app = create_app(settings=settings, client=client, repo=repo)
    return app, repo, path


def sign(body: bytes, timestamp=None, secret=SECRET):
    ts = str(int(time.time()) if timestamp is None else timestamp)
    sig = hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return {"X-Signature": sig, "X-Timestamp": ts, "Content-Type": "application/json"}


class FakeClient:
    """Pengganti Payment Gateway untuk pengujian (tanpa jaringan)."""
    def __init__(self, behavior="ok"):
        self.behavior = behavior
        self.calls = 0

    def create_payment(self, order_id, amount, idempotency_key):
        from src.payment_client import PaymentGatewayRejected, PaymentGatewayUnavailable
        self.calls += 1
        if self.behavior == "down":
            raise PaymentGatewayUnavailable("down")
        if self.behavior == "reject":
            raise PaymentGatewayRejected("reject")
        return {"reference": "GW-123"}
