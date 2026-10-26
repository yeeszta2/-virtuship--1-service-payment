#!/usr/bin/env bash
# Menjalankan pemindaian keamanan (SAST, SCA, secret, image) dan menyimpan laporan di reports/
# Jalankan SEBELUM push. Jika ada temuan High/Critical: perbaiki, lalu jalankan ulang sampai bersih
set -u
cd "$(dirname "$0")/.."
mkdir -p reports
status=0
run() {  # run <nama alat> seperti perintah/direct
  local name="$1"; shift
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[SKIP] $name: alat '$1' belum terpasang"; status=2; return
  fi
  echo "[RUN ] $name"
  if "$@"; then echo "[ OK ] $name"; else echo "[FAIL] $name (cek reports/)"; status=1; fi
}
run "Unit test"        python -m unittest discover -s tests
run "SAST (Bandit)"    bandit -r src -ll -f txt -o reports/bandit.txt
run "SCA (pip-audit)"  pip-audit -r requirements.txt -f json -o reports/pip-audit.json
run "Secret (gitleaks)" gitleaks detect --source . --no-banner --report-path reports/gitleaks.json
if [ "${1:-}" = "--image" ]; then
  run "Image (Trivy)"  trivy image --severity HIGH,CRITICAL --exit-code 1 payment-service:1.0
fi
echo "Selesai. Kode status: $status (0=bersih, 1=ada temuan, 2=ada alat belum terpasang)"
exit $status
