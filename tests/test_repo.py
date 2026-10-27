import os
import sqlite3
import tempfile
import unittest

from src.repository import PaymentRepository


class RepositoryTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.repo = PaymentRepository(self.path)

    def tearDown(self):
        os.remove(self.path)

    def test_sql_injection_payload_is_stored_as_plain_text(self):
        evil = "x' OR '1'='1"
        self.repo.create_pending("p1", "ORD-1", 1000, evil)
        self.assertIsNone(self.repo.find_by_idempotency_key("zzz"))
        found = self.repo.find_by_idempotency_key(evil)      # dicari persis, bukan sebagai SQL
        self.assertEqual(found["payment_id"], "p1")
        self.repo.create_pending("p2", "ORD-2", 2000, "key-2")
        self.assertIsNone(self.repo.find_by_idempotency_key("x' OR '1'='1' --"))

    def test_table_survives_drop_attempt_in_input(self):
        self.repo.create_pending("p1", "ORD-1'; DROP TABLE payments;--", 1000, "k1")
        self.assertEqual(self.repo.get("p1")["order_id"], "ORD-1'; DROP TABLE payments;--")

    def test_idempotency_key_is_unique(self):
        self.repo.create_pending("p1", "ORD-1", 1000, "same")
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.create_pending("p2", "ORD-2", 1000, "same")

    def test_final_status_is_not_overwritten(self):
        self.repo.create_pending("p1", "ORD-1", 1000, "k1")
        self.assertTrue(self.repo.update_status("p1", "SUCCESS"))
        self.assertFalse(self.repo.update_status("p1", "FAILED", "X"))
        self.assertEqual(self.repo.get("p1")["status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
