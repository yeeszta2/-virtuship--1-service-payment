"""Verifikasi keaslian webhook dari mitra."""
import hashlib
import hmac
import time


def verify_webhook_signature(payload: bytes, signature: str, timestamp: str,
                             secret: str, tolerance_seconds: int = 300) -> bool:
    """Memastikan webhook pembayaran benar-benar berasal dari mitra.

    Args:
        payload: isi mentah (raw body) request webhook.
        signature: tanda tangan HMAC-SHA256 dari header X-Signature.
        timestamp: waktu kirim (detik, epoch) dari header X-Timestamp.
        secret: kunci rahasia bersama dengan mitra (dari secret manager).
        tolerance_seconds: batas usia pesan yang masih diterima.

    Returns:
        True jika signature cocok dan pesan belum kedaluwarsa.
    """
    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError):
        return False
    # Tolak pesan lama agar pesan yang disadap tidak bisa dikirim ulang (replay)
    if abs(time.time() - sent_at) > tolerance_seconds:
        return False
    signed_content = timestamp.encode() + b"." + payload
    expected = hmac.new(secret.encode(), signed_content, hashlib.sha256).hexdigest()
    # compare_digest: perbandingan waktu-konstan, tidak membocorkan kecocokan
    # sebagian lewat perbedaan waktu respons
    return hmac.compare_digest(expected, signature or "")
