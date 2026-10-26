"""Akses database transaksi. Semua query memakai parameter (anti SQL Injection)."""
import sqlite3
from contextlib import closing
from typing import Optional

FINAL_STATUSES = ("SUCCESS", "FAILED")

SCHEMA = """
CREATE TABLE IF NOT EXISTS payments (
    payment_id      TEXT PRIMARY KEY,
    order_id        TEXT NOT NULL,
    amount          INTEGER NOT NULL CHECK (amount > 0),
    status          TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED')),
    failure_code    TEXT,
    gateway_ref     TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_payments_order ON payments (order_id);
"""


class PaymentRepository:
    """Penyimpanan transaksi pembayaran (SQLite untuk contoh; skema portabel ke RDBMS lain)."""

    def __init__(self, database_path: str):
        self._path = database_path
        self.init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.executescript(SCHEMA)

    def create_pending(self, payment_id: str, order_id: str, amount: int,
                       idempotency_key: str) -> None:
        """Menyimpan transaksi baru berstatus PENDING.

        Raises:
            sqlite3.IntegrityError: jika idempotency_key sudah dipakai.
        """
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO payments (payment_id, order_id, amount, idempotency_key) "
                "VALUES (?, ?, ?, ?)",
                (payment_id, order_id, amount, idempotency_key),
            )

    def find_by_idempotency_key(self, key: str) -> Optional[dict]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT payment_id, order_id, amount, status FROM payments "
                "WHERE idempotency_key = ?", (key,)).fetchone()
        return dict(row) if row else None

    def get(self, payment_id: str) -> Optional[dict]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT payment_id, order_id, amount, status, failure_code, created_at "
                "FROM payments WHERE payment_id = ?", (payment_id,)).fetchone()
        return dict(row) if row else None

    def set_gateway_ref(self, payment_id: str, gateway_ref: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE payments SET gateway_ref = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE payment_id = ?", (gateway_ref, payment_id))

    def reset_to_pending(self, payment_id: str) -> None:
        """Mengizinkan percobaan ulang untuk transaksi FAILED dengan kunci yang sama."""
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE payments SET status = 'PENDING', failure_code = NULL, "
                "updated_at = CURRENT_TIMESTAMP WHERE payment_id = ? AND status = 'FAILED'",
                (payment_id,))

    def update_status(self, payment_id: str, status: str, failure_code: str = None) -> bool:
        """Mengubah status dari PENDING ke status akhir.

        Status yang sudah final tidak ditimpa (aman terhadap webhook ganda).

        Returns:
            True jika status berubah, False jika tidak ada perubahan.
        """
        if status not in FINAL_STATUSES:
            raise ValueError("Status akhir tidak valid")
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "UPDATE payments SET status = ?, failure_code = ?, "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE payment_id = ? AND status = 'PENDING'",
                (status, failure_code, payment_id))
            return cur.rowcount > 0
