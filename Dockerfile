# syntax=docker/dockerfile:1.6
# Dockerfile for receipt-system on Render.com
#
# Why Docker instead of build.sh?
# Render's native Python env runs the build as a non-root user, so
# `apt-get install` fails with "Could not open lock file /var/lib/dpkg/lock-frontend".
# Docker builds run as root, so Tesseract installs cleanly.

FROM python:3.11-slim

# Force a fresh layer every time so Render can't reuse a stale tesseract-less image.
# Bump this on every deploy that touches the Tesseract install.
ARG CACHEBUST=2026-07-03-r2

# Install Tesseract OCR + language packs (English + Bahasa Malaysia + Simplified Chinese)
# Belt-and-suspenders: install + verify binary exists + write a marker file
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-msa \
        tesseract-ocr-chi_sim \
        findutils \
    && rm -rf /var/lib/apt/lists/* \
    && tesseract --version \
    && which tesseract \
    && dpkg -L tesseract-ocr | grep -E 'bin/.*tesseract$|tessdata' | head -20 \
    && echo "$CACHEBUST" > /opt/tesseract-marker.txt \
    && echo "Tesseract installed OK at /opt/tesseract-marker.txt"

WORKDIR /app

# Install Python dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Verify tesseract is reachable from Python before shipping
RUN python -c "import pytesseract; print('Build-time Tesseract:', pytesseract.get_tesseract_version())"

# Copy application code
COPY . .

# Ensure /usr/bin (where Debian puts tesseract) is on PATH at runtime.
# Some Render Docker base images strip /usr/bin from PATH; this re-asserts it.
ENV PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"
ENV TESSERACT_PATH=/usr/bin/tesseract

# Render sets $PORT at runtime; provide a sensible default for local testing
ENV PORT=8000
EXPOSE 8000

# Single worker, gthread for I/O concurrency, 5-min timeout for OCR
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
