# syntax=docker/dockerfile:1.6
# Dockerfile for receipt-system on Render.com
#
# Why Docker instead of build.sh?
# Render's native Python env runs the build as a non-root user, so
# `apt-get install` fails with "Could not open lock file /var/lib/dpkg/lock-frontend".
# Docker builds run as root, so tesseract installs cleanly.

FROM python:3.11-slim

# Install Tesseract OCR + language packs (English + Bahasa Malaysia + Simplified Chinese)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-msa \
        tesseract-ocr-chi_sim \
    && rm -rf /var/lib/apt/lists/* \
    && tesseract --version

WORKDIR /app

# Install Python dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Sanity check
RUN python -c "import pytesseract; print('Tesseract:', pytesseract.get_tesseract_version())"

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
