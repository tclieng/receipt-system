# syntax=docker/dockerfile:1.6
# Dockerfile for receipt-system on Render.com
# Super simple diagnostic version: set -ex prints every command, exits on first failure

FROM python:3.11-slim

ARG CACHEBUST=2026-07-03-r4

# Use set -ex so we see exactly which command fails
RUN set -ex \
    && echo "OS info:" \
    && cat /etc/os-release \
    && echo "Trying apt-get update..." \
    && apt-get update \
    && echo "Trying apt-get install..." \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-msa \
        tesseract-ocr-chi_sim \
    && echo "apt-get install done, verifying..." \
    && tesseract --version \
    && which tesseract \
    && echo "TESSERACT OK" \
    && echo "$CACHEBUST" > /opt/tesseract-marker.txt

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

ENV PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"
ENV TESSERACT_PATH=/usr/bin/tesseract
ENV PORT=8000
EXPOSE 8000

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
