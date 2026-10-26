# payment-service

Microservice transaksi untuk integrasi API Pembayaran pihak ketiga (Telco-Health Connect).

## Menjalankan di laptop
1. `cp .env.example .env` lalu isi `PAYMENT_API_KEY` dan `WEBHOOK_SECRET` (jangan di-commit).
2. `docker build -t payment-service:1.0 .`
3. `docker run --rm -p 8080:8080 --env-file .env payment-service:1.0`
4. Cek: `curl http://localhost:8080/health`

## Pengujian dan keamanan
- Unit test: `python -m unittest discover -s tests`
- Pemindaian keamanan: `./scripts/security_scan.sh` (tambahkan `--image` setelah build image)
- Laporan tersimpan di `reports/` (tidak di-commit)

## Konsistensi lingkungan
Image yang sama dipakai di laptop, staging, dan cloud. Perbedaan hanya pada environment variable;
di cloud nilainya berasal dari secret manager.

## Struktur
- `src/config.py` konfigurasi dari environment (fail fast)
- `src/payment_client.py` + `src/circuit_breaker.py` komunikasi ke mitra (timeout, circuit breaker)
- `src/repository.py` akses database (parameterized query)
- `src/webhook.py` verifikasi signature webhook
- `src/app.py` endpoint dan penanganan error
- `openapi.yaml` dokumentasi API (diuji agar sinkron dengan route)

## Batasan yang diketahui
- Autentikasi pengguna (JWT) diasumsikan ditangani API Gateway; layanan ini hanya boleh menerima trafik dari gateway.
- Database SQLite dipakai untuk contoh; ganti dengan RDBMS produksi dan sesuaikan migrasi.
