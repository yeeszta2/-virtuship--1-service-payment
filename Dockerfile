# ---- Stage 1: build (pasang dependensi) ----
FROM python:3.12-slim AS builder
WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

# ---- Stage 2: runtime (ramping, tanpa tool build) ----
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=builder /install /usr/local
COPY src/ ./src/
USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "src.app:create_app()"]
