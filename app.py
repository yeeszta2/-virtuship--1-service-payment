"""Microservice transaksi: integrasi dengan Payment Gateway pihak ketiga"""
import json
import logging
import re
import sqlite3
import uuid

from flask import Flask, jsonify, request

from .config import Settings, load_settings
from .circuit_breaker import CircuitBreaker
from .payment_client import (PaymentGatewayClient, PaymentGatewayRejected,
                             PaymentGatewayUnavailable)
from .repository import PaymentRepository
from .webhook import verify_webhook_signature

ORDER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_AMOUNT = 100_000_000

log = logging.getLogger("payment-service")


def _error(code: str, message: str, http_status: int):
    """Format error seragam; tidak memuat detail internal."""
    return jsonify({"error": {"code": code, "message": message}}), http_status


def _payment_body(record: dict) -> dict:
    return {"payment_id": record["payment_id"], "order_id": record["order_id"],
            "amount": record["amount"], "status": record["status"]}


def create_app(settings: Settings = None, client: PaymentGatewayClient = None,
               repo: PaymentRepository = None) -> Flask:
    """Membuat aplikasi Flask. Dependensi dapat disuntik agar mudah diuji."""
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024  # batasi ukuran request

    settings = settings or load_settings()
    repo = repo or PaymentRepository(settings.database_path)
    client = client or PaymentGatewayClient(
        settings.gateway_base_url, settings.gateway_api_key,
        settings.gateway_timeout_seconds,
        CircuitBreaker(settings.breaker_failure_threshold, settings.breaker_reset_seconds))

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/v1/payments")
    def create_payment():
        key = request.headers.get("Idempotency-Key", "")
        if not IDEMPOTENCY_PATTERN.match(key):
            return _error("INVALID_REQUEST", "Header Idempotency-Key wajib dan valid.", 400)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return _error("INVALID_REQUEST", "Body harus berupa JSON object.", 400)
        order_id, amount = data.get("order_id"), data.get("amount")
        if not isinstance(order_id, str) or not ORDER_ID_PATTERN.match(order_id):
            return _error("INVALID_REQUEST", "order_id tidak valid.", 400)
        if (not isinstance(amount, int) or isinstance(amount, bool)
                or not 1 <= amount <= MAX_AMOUNT):
            return _error("INVALID_REQUEST", "amount harus bilangan bulat positif.", 400)

        existing = repo.find_by_idempotency_key(key)
        if existing is None:
            payment_id = str(uuid.uuid4())
            try:
                repo.create_pending(payment_id, order_id, amount, key)
            except sqlite3.IntegrityError:  # permintaan kembar yang masuk bersamaan
                existing = repo.find_by_idempotency_key(key)
        if existing is not None:
            if existing["order_id"] != order_id or existing["amount"] != amount:
                return _error("DUPLICATE_REQUEST",
                              "Idempotency-Key sudah dipakai dengan isi berbeda.", 409)
            if existing["status"] == "SUCCESS":
                return jsonify(_payment_body(existing)), 200
            if existing["status"] == "PENDING":
                return jsonify(_payment_body(existing)), 202
            repo.reset_to_pending(existing["payment_id"])  # FAILED: boleh dicoba lagi
            payment_id = existing["payment_id"]

        try:
            result = client.create_payment(order_id, amount, key)
        except PaymentGatewayUnavailable:
            repo.update_status(payment_id, "FAILED", "GATEWAY_UNAVAILABLE")
            return _error("GATEWAY_UNAVAILABLE",
                          "Sistem sedang sibuk, silakan coba lagi sebentar.", 503)
        except PaymentGatewayRejected:
            repo.update_status(payment_id, "FAILED", "GATEWAY_REJECTED")
            return _error("GATEWAY_REJECTED", "Permintaan pembayaran ditolak.", 422)

        ref = result.get("reference") if isinstance(result, dict) else None
        if isinstance(ref, str):
            repo.set_gateway_ref(payment_id, ref[:64])
        return jsonify(_payment_body(repo.get(payment_id))), 202

    @app.get("/v1/payments/<payment_id>")
    def get_payment(payment_id):
        record = repo.get(payment_id)
        if record is None:
            return _error("NOT_FOUND", "Transaksi tidak ditemukan.", 404)
        return jsonify(_payment_body(record))

    @app.post("/v1/payments/webhook")
    def payment_webhook():
        payload = request.get_data()
        signature = request.headers.get("X-Signature", "")
        timestamp = request.headers.get("X-Timestamp", "")
        if not verify_webhook_signature(payload, signature, timestamp,
                                        settings.webhook_secret):
            return _error("INVALID_SIGNATURE", "Signature tidak valid.", 401)
        try:
            data = json.loads(payload)
        except ValueError:
            return _error("INVALID_REQUEST", "Body bukan JSON yang valid.", 400)
        if not isinstance(data, dict):
            return _error("INVALID_REQUEST", "Body harus berupa JSON object.", 400)
        payment_id, status = data.get("payment_id"), data.get("status")
        if not isinstance(payment_id, str) or status not in ("SUCCESS", "FAILED"):
            return _error("INVALID_REQUEST", "payment_id atau status tidak valid.", 400)
        if repo.get(payment_id) is None:
            return _error("NOT_FOUND", "Transaksi tidak ditemukan.", 404)
        # Saldo/status hanya berubah di sini, setelah konfirmasi terverifikasi.
        repo.update_status(payment_id, status, None if status == "SUCCESS" else "PARTNER_FAILED")
        return jsonify({"received": True}), 200

    @app.errorhandler(404)
    def not_found(_):
        return _error("NOT_FOUND", "Endpoint tidak ditemukan.", 404)

    @app.errorhandler(405)
    def method_not_allowed(_):
        return _error("METHOD_NOT_ALLOWED", "Metode tidak diizinkan.", 405)

    @app.errorhandler(413)
    def too_large(_):
        return _error("INVALID_REQUEST", "Ukuran request terlalu besar.", 413)

    @app.errorhandler(Exception)
    def unexpected(exc):
        log.error("Kesalahan tak terduga: %s", type(exc).__name__)  # tanpa isi request
        return _error("INTERNAL_ERROR", "Terjadi kesalahan pada sistem.", 500)

    return app
