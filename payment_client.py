"""Klien untuk memanggil API Payment Gateway mitra"""
import requests

from .circuit_breaker import CircuitBreaker, CircuitOpenError


class PaymentGatewayUnavailable(Exception):
    """Mitra tidak dapat dijangkau (timeout, koneksi gagal, error 5xx, atau sirkuit terbuka)."""


class PaymentGatewayRejected(Exception):
    """Mitra menolak permintaan (error 4xx), misalnya data tidak valid."""


class PaymentGatewayClient:
    """Memanggil Payment Gateway dengan timeout dan Circuit Breaker.

    Tujuan: gangguan di sisi mitra tidak membuat aplikasi kita menunggu tanpa
    batas dan tidak menjalar ke pengguna lain.
    """

    def __init__(self, base_url: str, api_key: str, timeout_seconds: float = 3.0,
                 breaker: CircuitBreaker = None, session=None):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._breaker = breaker or CircuitBreaker()
        self._session = session or requests.Session()

    def create_payment(self, order_id: str, amount: int, idempotency_key: str) -> dict:
        """Membuat permintaan pembayaran di mitra.

        Args:
            order_id: ID pesanan di sistem kita.
            amount: nominal dalam rupiah (bilangan bulat positif).
            idempotency_key: kunci agar permintaan ulang tidak membuat transaksi ganda.

        Returns:
            Respons JSON mitra (berisi minimal referensi transaksi mitra).

        Raises:
            PaymentGatewayUnavailable: mitra tidak tersedia atau sirkuit terbuka.
            PaymentGatewayRejected: mitra menolak permintaan (4xx).
        """
        try:
            self._breaker.before_call()
        except CircuitOpenError as exc:
            raise PaymentGatewayUnavailable("Sirkuit terbuka") from exc

        try:
            response = self._session.post(
                f"{self._base_url}/payments",
                json={"order_id": order_id, "amount": amount},
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Idempotency-Key": idempotency_key,
                },
                timeout=(self._timeout, self._timeout),
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            self._breaker.record_failure()
            raise PaymentGatewayUnavailable("Timeout atau koneksi gagal") from exc

        if response.status_code >= 500:
            self._breaker.record_failure()
            raise PaymentGatewayUnavailable(f"Mitra error {response.status_code}")

        # Mitra merespons (walau menolak), artinya jalur komunikasi sehat.
        self._breaker.record_success()
        if response.status_code >= 400:
            raise PaymentGatewayRejected(f"Mitra menolak ({response.status_code})")
        try:
            return response.json()
        except ValueError as exc:
            raise PaymentGatewayUnavailable("Respons mitra tidak valid") from exc
