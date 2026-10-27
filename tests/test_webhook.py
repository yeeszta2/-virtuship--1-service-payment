import hashlib
import hmac
import time
import unittest

from src.webhook import verify_webhook_signature

SECRET = "s3cr3t"
BODY = b'{"payment_id":"p1","status":"SUCCESS"}'


def good_signature(ts):
    return hmac.new(SECRET.encode(), ts.encode() + b"." + BODY, hashlib.sha256).hexdigest()


class WebhookSignatureTest(unittest.TestCase):
    def test_valid_signature(self):
        ts = str(int(time.time()))
        self.assertTrue(verify_webhook_signature(BODY, good_signature(ts), ts, SECRET))

    def test_tampered_body_rejected(self):
        ts = str(int(time.time()))
        self.assertFalse(verify_webhook_signature(BODY + b" ", good_signature(ts), ts, SECRET))

    def test_wrong_secret_rejected(self):
        ts = str(int(time.time()))
        self.assertFalse(verify_webhook_signature(BODY, good_signature(ts), ts, "other"))

    def test_old_timestamp_rejected(self):
        ts = str(int(time.time()) - 1000)
        self.assertFalse(verify_webhook_signature(BODY, good_signature(ts), ts, SECRET))

    def test_invalid_timestamp_or_missing_signature_rejected(self):
        self.assertFalse(verify_webhook_signature(BODY, "abc", "bukan-angka", SECRET))
        self.assertFalse(verify_webhook_signature(BODY, "", str(int(time.time())), SECRET))
        self.assertFalse(verify_webhook_signature(BODY, None, str(int(time.time())), SECRET))


if __name__ == "__main__":
    unittest.main()
