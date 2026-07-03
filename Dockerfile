# syntax=docker/dockerfile:1.6
# Dockerfile for receipt-system on Render.com
#
# Runs as root inside the build container, so apt-get install works.

FROM python:3.11-slim

# Force fresh layers every time so Render can't reuse a broken image.
# Bump on every deploy that touches the Tesseract install.
ARG CACHEBUST=2026-07-03-r3

# Diagnostic: log the environment so build logs show OS, DNS, etc.
RUN echo "=== BUILD DIAG: $(cat /etc/os-release | grep PRETTY_NAME) ===" \
    && echo "=== BUILD DIAG: $(uname -a) ===" \
    && cat /etc/resolv.conf \
    && echo "=== BUILD DIAG: testing DNS ===" \
    && getent hosts deb.debian.org || echo "DNS LOOKUP FAILED for deb.debian.org" \
    && echo "=== BUILD DIAG: testing HTTP to deb.debian.org ===" \
    && (curl -sI --max-time 10 https://deb.debian.org/ | head -3 || echo "HTTP FAILED to deb.debian.org") \
    && echo "=== BUILD DIAG: apt sources list ===" \
    && cat /etc/apt/sources.list /etc/apt/sources.list.d/* 2>/dev/null

# Split update and install so we see which step fails.
# Retry 3 times in case of transient network issues.
RUN for i in 1 2 3; do \
        echo "=== apt-get update attempt $i ===" \
        && apt-get update 2>&1 | tail -5 \
        && break \
        || (echo "apt-get update failed attempt $i, sleeping..." && sleep 5); \
    done

RUN for i in 1 2 3; do \
        echo "=== apt-get install attempt $i ===" \
        && apt-get install -y --no-install-recommends \
            --fix-missing \
            tesseract-ocr \
            tesseract-ocr-eng \
            tesseract-ocr-msa \
            tesseract-ocr-chi_sim \
            findutils \
            curl \
            ca-certificates \
            2>&1 | tail -20 \
        && break \
        || (echo "apt-get install failed attempt $i, sleeping..." && sleep 5); \
    done

# Clean up apt lists (smaller image)
RUN rm -rf /var/lib/apt/lists/*

# Verify tesseract is actually installed and accessible
RUN echo "=== TESSERACT VERIFICATION ===" \
    && tesseract --version 2>&1 || (echo "TESSERACT --version FAILED" && exit 1) \
    && which tesseract || (echo "WHICH TESSERACT FAILED" && exit 1) \
    && echo "=== TESSERACT FILES ===" \
    && dpkg -L tesseract-ocr | grep -E 'bin/.*tesseract$|tessdata' | head -10 \
    && echo "=== TESSERACT LANGS ===" \
    && ls /usr/share/tesseract-ocr/*/tessdata/ 2>/dev/null | head -20

# Mark the build as successful
RUN echo "$CACHEBUST" > /opt/tesseract-marker.txt \
    && echo "Tesseract installed OK at /opt/tesseract-marker.txt"

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Verify pytesseract can find tesseract at build time
RUN python -c "import pytesseract; print('Build-time Tesseract:', pytesseract.get_tesseract_version())"

# Copy application code
COPY . .

# Ensure /usr/bin is on PATH at runtime
ENV PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"
ENV TESSERACT_PATH=/usr/bin/tesseract
ENV PORT=8000
EXPOSE 8000

# gunicorn with 1 worker (single OCR process), gthread for I/O concurrency
CMD gunicorn web.app:app \
    --bind 0.0.0.0:$PORT \
    --worker-class gthread \
    --workers 1 \
    --threads 2 \
    --timeout 300 \
    --graceful-timeout 60 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile -
