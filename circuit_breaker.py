"""Circuit Breaker sederhana untuk melindungi aplikasi dari mitra yang gagal berulang"""
import threading
import time


class CircuitOpenError(Exception):
    """Dilempar saat sirkuit terbuka dan permintaan baru tidak diteruskan."""


class CircuitBreaker:
    """Memutus panggilan ke mitra sementara waktu jika gagal berulang.

    Keadaan:
        closed: normal, semua panggilan diteruskan.
        open: panggilan langsung ditolak sampai ``reset_seconds`` berlalu.
        half_open: satu panggilan percobaan diizinkan; sukses menutup sirkuit,
            gagal membukanya lagi.
    """

    def __init__(self, failure_threshold: int = 5, reset_seconds: float = 30.0,
                 clock=time.monotonic):
        self._failure_threshold = failure_threshold
        self._reset_seconds = reset_seconds
        self._clock = clock  # dapat diganti saat pengujian
        self._lock = threading.Lock()
        self._state = "closed"
        self._failures = 0
        self._opened_at = 0.0
        self._trial_in_progress = False

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def before_call(self) -> None:
        """Memeriksa apakah panggilan boleh diteruskan.

        Raises:
            CircuitOpenError: jika sirkuit terbuka atau percobaan sedang berjalan.
        """
        with self._lock:
            if self._state == "open":
                if self._clock() - self._opened_at < self._reset_seconds:
                    raise CircuitOpenError("Sirkuit terbuka")
                self._state = "half_open"
            if self._state == "half_open":
                if self._trial_in_progress:
                    raise CircuitOpenError("Percobaan pemulihan sedang berjalan")
                self._trial_in_progress = True

    def record_success(self) -> None:
        """Mencatat panggilan sukses dan menutup sirkuit."""
        with self._lock:
            self._state = "closed"
            self._failures = 0
            self._trial_in_progress = False

    def record_failure(self) -> None:
        """Mencatat kegagalan; membuka sirkuit jika melewati ambang."""
        with self._lock:
            self._failures += 1
            self._trial_in_progress = False
            if self._state == "half_open" or self._failures >= self._failure_threshold:
                self._state = "open"
                self._opened_at = self._clock()
