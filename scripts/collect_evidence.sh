#!/usr/bin/env bash
cd "$(dirname "$0")/.." || exit 1
mkdir -p evidence
OUT="evidence/evidence_$(date +%Y%m%d_%H%M%S).txt"
[ -f .env ] || { echo "Buat dulu: cp .env.example .env  (isi nilai DUMMY)"; exit 1; }

sec() { printf '\n==================== GAMBAR %s: %s ====================\n' "$1" "$2" | tee -a "$OUT"; }
cmd() {
  printf '\n$ %s\n' "$1" | tee -a "$OUT"
  bash -c "set -o pipefail; $1" 2>&1 | tee -a "$OUT"
  echo "[exit code: ${PIPESTATUS[0]}]" | tee -a "$OUT"
}
DOCKER_OK=0; docker info >/dev/null 2>&1 && DOCKER_OK=1
dsec() { sec "$1" "$2"; if [ $DOCKER_OK -eq 0 ]; then echo "[DILEWATI] Docker tidak berjalan/tidak bisa diakses (coba sudo atau grup docker)" | tee -a "$OUT"; return 1; fi; }
{ echo "Bukti dikumpulkan: $(date)"; echo "Folder: $PWD"; } | tee "$OUT"

sec 1 "Versi tools"
cmd "python --version && git --version && docker --version && docker compose version"
cmd "grep PRETTY_NAME /etc/os-release"
cmd "bandit --version | head -2; pip-audit --version"
sec 2 "Struktur folder"
cmd "find . \( -path ./.venv -o -path ./.git -o -path ./evidence -o -name __pycache__ \) -prune -o -type f -print | sort"
sec 3 "Unit test"
cmd "python -m unittest discover -s tests -v 2>&1 | tail -15"

if dsec 4 "docker build (tanpa cache)"; then
  cmd "docker build --no-cache --progress=plain -t payment-service:1.0 . 2>&1 | tail -25"
  sec 5 "Ukuran image, user non-root, versi Python"
  cmd "docker images payment-service:1.0"
  cmd "docker run --rm --entrypoint id payment-service:1.0"
  cmd "docker run --rm --entrypoint python payment-service:1.0 --version"
  sec 6 "Kontainer berjalan dan /health"
  cmd "docker rm -f payment-svc >/dev/null 2>&1; docker run -d --name payment-svc -p 8080:8080 --env-file .env payment-service:1.0"
  echo "(menunggu 35 detik agar healthcheck selesai...)"; sleep 35
  cmd "docker ps --filter name=payment-svc"
  cmd "curl -si -m 15 http://localhost:8080/health"
  sec 7 "Uji alur pembayaran dan webhook"
  cmd "curl -si -m 15 -X POST http://localhost:8080/v1/payments -H 'Content-Type: application/json' -d '{\"order_id\":\"ORD-1\",\"amount\":50000}'"
  cmd "curl -si -m 15 -X POST http://localhost:8080/v1/payments -H 'Content-Type: application/json' -H 'Idempotency-Key: demo-001' -d '{\"order_id\":\"ORD-1\",\"amount\":50000}'"
  cmd "curl -si -m 15 -X POST http://localhost:8080/v1/payments/webhook -H 'X-Signature: palsu' -H \"X-Timestamp: \$(date +%s)\" -d '{\"payment_id\":\"x\",\"status\":\"SUCCESS\"}'"
  cmd "set -a; . ./.env; set +a; TS=\$(date +%s); BODY='{\"payment_id\":\"x\",\"status\":\"SUCCESS\"}'; SIG=\$(printf '%s.%s' \"\$TS\" \"\$BODY\" | openssl dgst -sha256 -hmac \"\$WEBHOOK_SECRET\" | awk '{print \$NF}'); curl -si -m 15 -X POST http://localhost:8080/v1/payments/webhook -H \"X-Signature: \$SIG\" -H \"X-Timestamp: \$TS\" -d \"\$BODY\""
  docker rm -f payment-svc >/dev/null 2>&1
fi

sec 8 "SAST Bandit"
cmd "bandit -r src 2>&1 | tail -30"
sec 9 "SCA pip-audit"
cmd "pip-audit -r requirements.txt"
if dsec 10 "Secret scan gitleaks"; then
  cmd "docker run --rm -v \"\$PWD:/repo\" ghcr.io/gitleaks/gitleaks:latest detect --source /repo --no-git --no-banner"
fi
if dsec 11 "Image scan Trivy"; then
  cmd "docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache aquasec/trivy:latest image payment-service:1.0 2>&1 | head -30"
  cmd "docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache aquasec/trivy:latest image --severity HIGH,CRITICAL --exit-code 1 payment-service:1.0 >/dev/null 2>&1; echo \"exit code trivy: \$?\""
fi

if [ "${1:-}" = "--demo" ]; then
  sec "12-13" "Demo SAST (uji validasi pemindai, BUKAN temuan kode proyek)"
  mkdir -p /tmp/sast-demo
  cat > /tmp/sast-demo/vuln_example.py <<'PY'
import sqlite3

def find_payment(conn: sqlite3.Connection, order_id: str):
    # SENGAJA RENTAN (contoh uji pemindai): query digabung dari input pengguna
    query = "SELECT * FROM payments WHERE order_id = '%s'" % order_id
    return conn.execute(query).fetchall()
PY
  cmd "bandit /tmp/sast-demo/vuln_example.py"
  cat > /tmp/sast-demo/vuln_example.py <<'PY'
import sqlite3

def find_payment(conn: sqlite3.Connection, order_id: str):
    # Parameterized query: nilai dikirim terpisah dari teks SQL
    return conn.execute("SELECT * FROM payments WHERE order_id = ?", (order_id,)).fetchall()
PY
  cmd "bandit /tmp/sast-demo/vuln_example.py"
fi

sec 15-16 "Riwayat commit dan isi repositori (pengganti screenshot GitHub)"
if [ -d .git ]; then cmd "git log --oneline"; cmd "git status -sb"; cmd "git remote -v"; cmd "git ls-files"; else echo "[DILEWATI] belum ada repo git (jalankan bash commit_steps.sh dulu, lalu ulangi bagian ini)" | tee -a "$OUT"; fi

if dsec 18 "Docker Compose"; then
  cmd "docker rm -f payment-svc >/dev/null 2>&1; docker compose up --build -d"
  echo "(menunggu 35 detik...)"; sleep 35
  cmd "docker compose ps"
  cmd "curl -si -m 15 http://localhost:8080/health"
  cmd "docker compose down"
fi

sec 19 "Bukti manajemen rahasia (nilai .env disamarkan)"
cmd "git ls-files 2>/dev/null | grep -E '(^|/)\.env' || echo '(belum ada repo git atau tidak ada berkas .env terlacak)'"
cmd "git check-ignore -v .env || echo '.env belum cocok aturan .gitignore'"
if [ $DOCKER_OK -eq 1 ]; then cmd "docker run --rm --entrypoint env payment-service:1.0 | grep -E 'PAYMENT_API_KEY|WEBHOOK_SECRET' || echo 'OK: tidak ada rahasia di dalam image'"; fi
cmd "sed 's/=.*/=***/' .env"

printf '\nSELESAI. Kirim berkas: %s\n' "$OUT"
