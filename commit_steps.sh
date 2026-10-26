#!/usr/bin/env bash
# Membuat riwayat commit bertahap memakai identitas git ANDA (git config user.name / user.email)
# Sebelum tiap commit yang menyentuh kode, jalankan ./scripts/security_scan.sh dan perbaiki temuan High/Critical
set -e
git init -q -b main
git config user.name >/dev/null || { echo "Atur dulu: git config user.name 'Nama Anda'"; exit 1; }

c() { git add "${@:2}"; git commit -q -m "$1"; echo "commit: $1"; }

c "chore: scaffold proyek (gitignore, dockerignore, env contoh, dependensi)" .gitignore .dockerignore .env.example requirements.txt requirements-dev.txt reports/.gitkeep src/__init__.py tests/__init__.py
c "feat(config): baca konfigurasi dan rahasia dari environment (fail fast, wajib HTTPS)" src/config.py tests/test_config.py
c "feat(gateway): klien Payment Gateway dengan timeout dan circuit breaker" src/circuit_breaker.py src/payment_client.py tests/test_circuit_breaker.py tests/test_payment_client.py
c "feat(db): repository transaksi dengan parameterized query" src/repository.py tests/test_repository.py
c "feat(webhook): verifikasi signature HMAC dan timestamp" src/webhook.py tests/test_webhook.py
c "feat(api): endpoint pembayaran, webhook, idempotency, dan error handling" src/app.py tests/helpers.py tests/test_api.py
c "build(docker): Dockerfile multi-stage, non-root, healthcheck" Dockerfile
c "docs(api): openapi.yaml sinkron dengan route" openapi.yaml
c "ci(security): skrip dan workflow SAST, SCA, secret, dan image scan" scripts/security_scan.sh .github/workflows/security.yml
c "build(compose): compose.yaml untuk menjalankan lokal" compose.yaml
c "docs: README dan panduan commit" README.md commit_steps.sh
git log --oneline
