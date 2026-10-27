import json
import os
import re
import unittest

from tests.helpers import FakeClient, make_app, sign

HEADERS = {"Idempotency-Key": "idem-1"}
BODY = {"order_id": "ORD-1", "amount": 25000}


class ApiTest(unittest.TestCase):
    def build(self, behavior="ok"):
        self.client_fake = FakeClient(behavior)
        app, self.repo, self.path = make_app(self.client_fake)
        self.http = app.test_client()
        self.addCleanup(os.remove, self.path)

    def test_missing_idempotency_key_rejected(self):
        self.build()
        r = self.http.post("/v1/payments", json=BODY)
        self.assertEqual(r.status_code, 400)

    def test_invalid_amount_rejected(self):
        self.build()
        for bad in (0, -5, "100", True, 10**12):
            r = self.http.post("/v1/payments", json={"order_id": "ORD-1", "amount": bad}, headers=HEADERS)
            self.assertEqual(r.status_code, 400, bad)

    def test_invalid_order_id_rejected(self):
        self.build()
        r = self.http.post("/v1/payments", json={"order_id": "x' OR 1=1", "amount": 1000}, headers=HEADERS)
        self.assertEqual(r.status_code, 400)

    def test_success_returns_202_pending(self):
        self.build()
        r = self.http.post("/v1/payments", json=BODY, headers=HEADERS)
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.get_json()["status"], "PENDING")

    def test_same_key_does_not_call_partner_twice(self):
        self.build()
        first = self.http.post("/v1/payments", json=BODY, headers=HEADERS).get_json()
        second = self.http.post("/v1/payments", json=BODY, headers=HEADERS).get_json()
        self.assertEqual(first["payment_id"], second["payment_id"])
        self.assertEqual(self.client_fake.calls, 1)

    def test_same_key_different_body_conflict(self):
        self.build()
        self.http.post("/v1/payments", json=BODY, headers=HEADERS)
        r = self.http.post("/v1/payments", json={"order_id": "ORD-1", "amount": 99999}, headers=HEADERS)
        self.assertEqual(r.status_code, 409)

    def test_partner_down_returns_503_with_friendly_message(self):
        self.build("down")
        r = self.http.post("/v1/payments", json=BODY, headers=HEADERS)
        self.assertEqual(r.status_code, 503)
        self.assertIn("sibuk", r.get_json()["error"]["message"])

    def test_failed_payment_can_be_retried_with_same_key(self):
        self.build("down")
        self.http.post("/v1/payments", json=BODY, headers=HEADERS)
        self.client_fake.behavior = "ok"
        r = self.http.post("/v1/payments", json=BODY, headers=HEADERS)
        self.assertEqual(r.status_code, 202)

    def test_webhook_invalid_signature_rejected_and_status_unchanged(self):
        self.build()
        pid = self.http.post("/v1/payments", json=BODY, headers=HEADERS).get_json()["payment_id"]
        body = json.dumps({"payment_id": pid, "status": "SUCCESS"}).encode()
        r = self.http.post("/v1/payments/webhook", data=body,
                           headers={"X-Signature": "palsu", "X-Timestamp": "1", "Content-Type": "application/json"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.repo.get(pid)["status"], "PENDING")

    def test_webhook_valid_signature_updates_status(self):
        self.build()
        pid = self.http.post("/v1/payments", json=BODY, headers=HEADERS).get_json()["payment_id"]
        body = json.dumps({"payment_id": pid, "status": "SUCCESS"}).encode()
        r = self.http.post("/v1/payments/webhook", data=body, headers=sign(body))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.http.get(f"/v1/payments/{pid}").get_json()["status"], "SUCCESS")

    def test_duplicate_webhook_does_not_flip_final_status(self):
        self.build()
        pid = self.http.post("/v1/payments", json=BODY, headers=HEADERS).get_json()["payment_id"]
        ok = json.dumps({"payment_id": pid, "status": "SUCCESS"}).encode()
        bad = json.dumps({"payment_id": pid, "status": "FAILED"}).encode()
        self.http.post("/v1/payments/webhook", data=ok, headers=sign(ok))
        self.http.post("/v1/payments/webhook", data=bad, headers=sign(bad))
        self.assertEqual(self.repo.get(pid)["status"], "SUCCESS")

    def test_error_response_does_not_leak_internal_details(self):
        self.build()
        r = self.http.get("/v1/payments/tidak-ada")
        self.assertEqual(r.status_code, 404)
        text = r.get_data(as_text=True)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("unit-test", text)

    def test_security_headers_present(self):
        self.build()
        r = self.http.get("/health")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")

    def test_openapi_documents_every_route(self):
        """Dokumentasi API harus sinkron dengan route yang ada."""
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML tidak terpasang")
        self.build()
        with open(os.path.join(os.path.dirname(__file__), "..", "openapi.yaml")) as f:
            documented = set(yaml.safe_load(f)["paths"].keys())
        app = self.http.application
        routes = {re.sub(r"<(\w+)>", r"{\1}", r.rule) for r in app.url_map.iter_rules()
                  if r.endpoint != "static"}
        self.assertEqual(routes, documented)


if __name__ == "__main__":
    unittest.main()
