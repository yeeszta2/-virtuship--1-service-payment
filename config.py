"""Konfigurasi layanan

Seluruh nilai (termasuk rahasia) dibaca dari environment variable, tidak ada
yang ditulis langsung di kode (no hardcoded secret)
"""
import os
from dataclasses import dataclass


def _require(name: str) -> str:
    """Mengambil environment variable wajib.

    Raises:
        RuntimeError: jika variabel belum diatur (fail fast, agar layanan
        tidak berjalan dengan konfigurasi kosong). Nilainya tidak pernah
        dimasukkan ke pesan error.
    """
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} belum diatur")
    return value


@dataclass(frozen=True)
class Settings:
    """Kumpulan konfigurasi yang tidak dapat diubah saat layanan berjalan."""

    gateway_base_url: str
    gateway_api_key: str
    webhook_secret: str
    database_path: str
    gateway_timeout_seconds: float
    breaker_failure_threshold: int
    breaker_reset_seconds: float


def load_settings() -> Settings:
    """Membaca konfigurasi dari environment.

    Koneksi ke Payment Gateway wajib HTTPS, kecuali APP_ENV=local untuk
    pengembangan di laptop.
    """
    base_url = _require("PAYMENT_API_BASE_URL").rstrip("/")
    if not base_url.startswith("https://") and os.environ.get("APP_ENV") != "local":
        raise RuntimeError("PAYMENT_API_BASE_URL harus memakai HTTPS")
    return Settings(
        gateway_base_url=base_url,
        gateway_api_key=_require("PAYMENT_API_KEY"),
        webhook_secret=_require("WEBHOOK_SECRET"),
        database_path=os.environ.get("DATABASE_PATH", "/tmp/payments.db"),
        gateway_timeout_seconds=float(os.environ.get("PAYMENT_TIMEOUT_SECONDS", "3")),
        breaker_failure_threshold=int(os.environ.get("BREAKER_FAILURE_THRESHOLD", "5")),
        breaker_reset_seconds=float(os.environ.get("BREAKER_RESET_SECONDS", "30")),
    )
